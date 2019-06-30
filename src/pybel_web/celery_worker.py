# -*- coding: utf-8 -*-

"""Runs the Celery worker for BEL Commons.

Use: :code:`python3 -m celery -A pybel_web.celery_worker.celery worker` while also laughing at how ridiculously
redundant this nomenclature is.
"""

import hashlib
import logging
import os
import random
from typing import Dict

import requests.exceptions
import time
from bel_resources.exc import ResourceError
from celery.app.task import Task
from celery.utils.log import get_task_logger
from flask import render_template
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import BELGraph, Manager, from_json, from_lines, to_bytes
from pybel.constants import METADATA_CONTACT, METADATA_DESCRIPTION, METADATA_LICENSES
from pybel.manager.citation_utils import enrich_pubmed_citations
from pybel.parser.exc import InconsistentDefinitionError
from pybel.struct.mutation import enrich_protein_and_rna_origins
from pybel_tools.assembler.html.assembler import get_network_summary_dict
from .application import create_application
from .constants import MAIL_DEFAULT_SENDER, integrity_message
from .core.celery import PyBELCelery
from .manager import WebManager
from .manager_utils import fill_out_report, insert_graph, run_heat_diffusion_helper
from .models import Report, User

celery_logger = get_task_logger(__name__)
log = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
logging.getLogger('pybel.parser').setLevel(logging.CRITICAL)

celery_logger.setLevel(logging.DEBUG)
log.setLevel(logging.DEBUG)

app = create_application()
mail = app.extensions.get('mail')
celery = PyBELCelery.get_celery(app)

DEFAULT_METADATA = {
    METADATA_DESCRIPTION: {'Document description'},
    METADATA_CONTACT: {'your@email.com'},
    METADATA_LICENSES: {'Document license'},
}


@celery.task(name='debug-task')
def run_debug_task() -> int:
    """Run the debug task that sleeps for a trivial amount of time."""
    celery_logger.info('running celery debug task')
    log.info('running celery debug task')
    time.sleep(random.randint(6, 10))
    return 6 + 2


@celery.task(bind=True, name='summarize-bel', ignore_result=True)
def summarize_bel(task: Task, connection: str, report_id: int):
    """Parse a BEL script asynchronously and email feedback.

    :param task: The task that's being run. Automatically bound.
    :param connection: A connection to build the manager
    :param report_id: A report to parse
    """
    manager = WebManager(connection=connection)

    t = time.time()
    report = manager.get_report_by_id(report_id)  # FIXME race condition with database?
    source_name = report.source_name

    def make_mail(subject: str, body: str) -> None:
        """Send a mail with the given subject and body."""
        if mail:
            with app.app_context():
                mail.send_message(
                    subject=subject,
                    recipients=[report.user.email],
                    body=body,
                    sender=app.config[MAIL_DEFAULT_SENDER],
                )

    def finish_parsing(subject: str, body: str) -> str:
        """Send a message and finish parsing.

        :param str subject:
        :param str body:
        :return: The body
        :rtype: str
        """
        make_mail(subject, body)
        report.message = body
        manager.session.commit()
        return body

    try:
        graph = parse_graph(report=report, manager=manager, task=task)

    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError):
        message = 'Connection to resource could not be established.'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    except InconsistentDefinitionError as e:
        message = f'Parsing failed for {source_name} because {e.definition} was redefined on line {e.line_number}.'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    except Exception as e:
        message = f'Parsing failed for {source_name} from a general error: {e}'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    time_difference = time.time() - t

    send_summary_mail(graph, report, time_difference)

    report.time = time_difference
    report.completed = True
    manager.session.add(report)
    manager.session.commit()

    celery_logger.info('finished in %.2f seconds', time.time() - t)

    manager.session.close()

    return 0


@celery.task(bind=True, name='upload-bel')
def upload_bel(task: Task, connection: str, report_id: int, enrich_citations: bool = False):
    """Parse a BEL script asynchronously and send email feedback.

    :param task: The task that's being run. Automatically bound.
    :param connection: The connection string
    :param report_id: Report identifier
    :param enrich_citations:
    """
    if not task.request.called_directly:
        task.update_state(state='STARTED')

    manager = WebManager(connection=connection)

    t = time.time()
    report = manager.get_report_by_id(report_id)

    report_id = report.id
    source_name = report.source_name

    celery_logger.info(f'Starting parse task for {source_name} (report {report_id})')

    def make_mail(subject: str, body: str) -> None:
        """Send a mail with the given subject and body."""
        if not mail:
            return

        with app.app_context():
            mail.send_message(
                subject=subject,
                recipients=[report.user.email],
                body=body,
                sender=app.config[MAIL_DEFAULT_SENDER],
            )

    def finish_parsing(subject: str, body: str) -> str:
        make_mail(subject, body)
        report.message = body
        manager.session.commit()
        return body

    celery_logger.info('parsing graph')

    try:
        graph = parse_graph(report=report, manager=manager, task=task)

    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        message = f'Connection to resource could not be established: {e}'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    except InconsistentDefinitionError as e:
        message = f'Parsing failed for {source_name} because {e.definition} was redefined on line {e.line_number}.'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    except Exception as e:
        message = f'Parsing failed for {source_name} from a general error: {e}'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    if not graph.name:
        message = f'Parsing failed for {source_name} because SET DOCUMENT Name was missing.'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    if not graph.version:
        message = f'Parsing failed for {source_name} because SET DOCUMENT Version was missing.'
        return finish_parsing(f'Parsing Failed for {source_name}', message)

    problem = {
        key: value
        for key, value in graph.document.items()
        if key in DEFAULT_METADATA and value in DEFAULT_METADATA[key]
    }

    if problem:
        message = f'{source_name} was rejected because it has "default" metadata: {problem}'
        return finish_parsing(f'Rejected {source_name}', message)

    send_summary_mail(graph, report, time.time() - t)

    network = manager.get_network_by_name_version(graph.name, graph.version)

    if network is not None:
        message = integrity_message.format(graph.name, graph.version)

        if network.report.user == report.user:  # This user is being a fool
            return finish_parsing(f'Uploading Failed for {source_name}', message)

        if hashlib.sha1(network.blob).hexdigest() != hashlib.sha1(to_bytes(graph)).hexdigest():
            recipients = [
                user.email
                for user in manager.session.query(User.email).filter(User.is_admin).all()
            ]
            if recipients:
                with app.app_context():
                    app.extensions['mail'].send_message(
                        subject='Possible attempted Espionage',
                        recipients=recipients,
                        body=f'User ({report.user.id} {report.user.email}) may have attempted espionage of {network}',
                        sender=app.config[MAIL_DEFAULT_SENDER],
                    )

            return finish_parsing(f'Upload Failed for {source_name}', message)

        # Grant rights to this user
        network.users.append(report.user)
        manager.session.commit()

        message = f'Granted rights for {network} to {report.user} after parsing {source_name}'
        return finish_parsing(f'Granted Rights from {source_name}', message)

    if report.infer_origin:
        enrich_protein_and_rna_origins(graph)

    if enrich_citations:
        try:
            enrich_pubmed_citations(manager, graph)  # FIXME send this as a follow-up task

        except (IntegrityError, OperationalError):  # just skip this if there's a problem
            manager.session.rollback()
            celery_logger.exception('problem with database while fixing citations')

        except Exception:
            celery_logger.exception('problem fixing citations')

    upload_failed_text = f'Upload Failed for {source_name}'

    try:
        celery_logger.info(f'inserting {graph} with {manager.engine.url}')
        network = manager.insert_graph(graph)

    except IntegrityError as e:
        manager.session.rollback()
        celery_logger.exception('Integrity error')
        return finish_parsing(upload_failed_text, str(e))

    except OperationalError:
        manager.session.rollback()
        message = 'Database is locked. Unable to upload.'
        return finish_parsing(upload_failed_text, message)

    except Exception as e:
        manager.session.rollback()
        return finish_parsing(upload_failed_text, str(e))

    celery_logger.info(f'done storing [{network.id}]. starting to make report.')

    try:
        fill_out_report(graph=graph, network=network, report=report)
        report.time = time.time() - t

        manager.session.add(report)
        manager.session.commit()

        celery_logger.info('report #%d complete [%d]', report.id, network.id)
        make_mail(f'Uploaded succeeded for {graph} ({source_name})',
                  f'{source_name} ({graph}) is done parsing. Check the network list page.')

        return {
            'network_id': network.id,
        }
    except Exception as e:
        manager.session.rollback()
        make_mail(f'Report unsuccessful for {source_name}', str(e))
        celery_logger.exception('Problem filling out report')
        return -1
    finally:
        manager.session.close()


@celery.task(name='run-heat-diffusion')
def run_heat_diffusion(connection: str, experiment_id: int) -> int:
    """Run the heat diffusion workflow.

    :param connection: A connection to build the manager
    :param experiment_id:
    """
    manager = WebManager(connection=connection)
    experiment = manager.get_experiment_by_id(experiment_id)

    query_id = experiment.query_id
    source_name = experiment.source_name
    email = experiment.user.email

    run_heat_diffusion_helper(manager, experiment)

    try:
        manager.session.add(experiment)
        manager.session.commit()
    except Exception:
        manager.session.rollback()
        return -1
    finally:
        manager.session.close()

    message = f'Experiment {experiment_id} on query {query_id} with {source_name} has completed.'

    if mail is not None:
        with app.app_context():
            mail.send_message(
                subject=f'Heat Diffusion Workflow [{experiment_id}] is Complete',
                recipients=[email],
                body=message,
                sender=app.config[MAIL_DEFAULT_SENDER],
            )

    return experiment_id


@celery.task(name='upload-json')
def upload_json(connection: str, user_id: int, payload: Dict, public: bool = False):
    """Receive and process a JSON serialized BEL graph.

    :param connection: A connection to build the manager
    :param user_id: the ID of the user to associate with the graph
    :param payload: JSON dictionary for :func:`pybel.from_json`
    :param public: Should the network be made public?
    """
    manager = WebManager(connection=connection)
    user = manager.get_user_by_id(user_id)

    try:
        graph = from_json(payload)
    except Exception:
        celery_logger.exception('unable to parse JSON')
        return -1

    try:
        insert_graph(manager, graph, user, public=public)
    except Exception:
        celery_logger.exception('unable to insert graph')
        manager.session.rollback()
        return -2

    return 0


def send_summary_mail(graph: BELGraph, report: Report, time_difference: float):
    """Send a mail with a summary.

    :param graph:
    :param report:
    :param time_difference: The time difference to log
    """
    with app.app_context():
        html = render_template(
            'email_report.html',
            graph=graph,
            report=report,
            time=time_difference,
            **get_network_summary_dict(graph),
        )

        if mail is not None:
            mail.send_message(
                subject=f'Parsing Report for {graph}',
                recipients=[report.user.email],
                body=f'Below is the parsing report for {graph}, completed in {time_difference:.2f} seconds.',
                html=html,
                sender=app.config[MAIL_DEFAULT_SENDER],
            )
        else:
            path = os.path.join(os.path.expanduser('~'), 'Downloads', f'report_{report.id}.html')

            try:
                with open(path, 'w') as file:
                    print(html, file=file)
                celery_logger.info(f'HTML printed to file at: {path}')
            except FileNotFoundError:
                celery_logger.info('no file printed.')


def iterate_report_lines_in_task(report: Report, task: Task):
    """Iterate through the lines in a :class:`Report` while keeping a celery :class:`Task` informed of progress."""
    lines = report.get_lines()
    len_lines = len(lines)
    for i, line in enumerate(lines, start=1):
        if not task.request.called_directly:
            task.update_state(state='PROGRESS', meta={
                'task': 'parsing',
                'current_line_number': i,
                'current_line': line,
                'total_lines': len_lines,
            })
        yield line


def parse_graph(report: Report, manager: Manager, task: Task) -> BELGraph:
    """Parse a graph from a report while keeping a celery :class:`Task` informed of progress."""
    return from_lines(
        iterate_report_lines_in_task(report, task),
        manager=manager,
        allow_nested=report.allow_nested,
        citation_clearing=report.citation_clearing,
    )
