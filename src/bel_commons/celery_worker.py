# -*- coding: utf-8 -*-

"""Holds the Celery worker for BEL Commons.

Use: :code:`python3 -m celery worker -A bel_commons.wsgi.celery_app` to run such that it runs with
the web application's configuration.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from typing import Dict, Mapping, Optional

import requests.exceptions
from celery import Celery
from celery.app.task import Task
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from flask import Blueprint, current_app, jsonify, render_template
from sqlalchemy.exc import IntegrityError, OperationalError

from bel_commons.celery_utils import parse_graph
from bel_commons.constants import MAIL_DEFAULT_SENDER
from bel_commons.manager import WebManager
from bel_commons.manager_utils import fill_out_report, insert_graph, run_heat_diffusion_helper
from bel_commons.models import Report
from bel_resources.exc import ResourceError
from pybel import BELGraph, from_nodelink
from pybel.manager.citation_utils import enrich_pubmed_citations
from pybel.parser.exc import InconsistentDefinitionError
from pybel.struct.mutation import enrich_protein_and_rna_origins
from pybel_tools.summary import BELGraphSummary

__all__ = [
    'celery_app',
    'celery_blueprint',
    'celery_logger',
]

celery_logger = get_task_logger(__name__)
logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
logging.getLogger('pybel.parser').setLevel(logging.CRITICAL)

celery_logger.setLevel(logging.DEBUG)
logger.setLevel(logging.DEBUG)

celery_app = Celery(__name__)
celery_blueprint = Blueprint('task', __name__, url_prefix='/api')


@celery_blueprint.route('/task/<uuid>', methods=['GET'])
def check(uuid: str):
    """Check the given task.

    :param uuid: The task's UUID as a string
    ---
    parameters:
      - name: uuid
        in: path
        description: The task's UUID as a string
        required: true
        type: string
    responses:
      200:
        description: JSON describing the state of the task

    """
    task = AsyncResult(uuid, app=celery_app)

    return jsonify(
        task_id=task.task_id,
        status=task.status,
        result=task.result,
    )


@celery_app.task(name='debug-task')
def run_debug_task() -> int:
    """Run the debug task that sleeps for a trivial amount of time."""
    celery_logger.info('running celery debug task')
    logger.info('running celery debug task')
    time.sleep(random.randint(6, 10))
    return 6 + 2


@celery_app.task(bind=True)  # noqa: C901
def parse(
    task: Task,
    source_name: str,
    contents: str,
    parse_kwargs: Optional[Mapping[str, bool]] = None,
    user_id: Optional[int] = None,
    enrich_citations: bool = True,
):
    """Parse a BEL document and store in the database."""
    from .core import manager

    if not task.request.called_directly:
        task.update_state(state='STARTED')

    t = time.time()

    _encoding = 'utf-8'
    source_bytes = contents.encode(_encoding)

    if parse_kwargs is None:
        parse_kwargs = {}

    parse_kwargs.setdefault('public', True)
    parse_kwargs.setdefault('citation_clearing', True)
    parse_kwargs.setdefault('infer_origin', True)
    parse_kwargs.setdefault('identifier_validation', True)

    report = Report(
        user_id=user_id,
        source_name=source_name,
        source=source_bytes,
        source_hash=hashlib.sha512(source_bytes).hexdigest(),
        encoding=_encoding,
        **parse_kwargs,
    )
    manager.session.add(report)

    try:
        graph = parse_graph(
            report=report,
            manager=manager,
            task=task,
        )
    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        message = f'Parsing Failed for {source_name}. Connection to resource could not be established: {e}'
        return finish_parsing(manager.session, report, 'Parsing Failed.', message)
    except InconsistentDefinitionError as e:
        message = f'Parsing Failed for {source_name} because {e.definition} was redefined on line {e.line_number}'
        return finish_parsing(manager.session, report, 'Parsing Failed.', message)
    except Exception as e:
        message = f'Parsing Failed for {source_name} from a general error: {e}'
        return finish_parsing(manager.session, report, 'Parsing Failed.', message)

    # Integrity checking
    if not graph.name:
        return finish_parsing(
            manager.session, report,
            'Parsing Failed.', f'Parsing Failed for {source_name} because SET DOCUMENT Name was missing.',
        )
    if not graph.version:
        return finish_parsing(
            manager.session, report,
            'Parsing Failed.', f'Parsing Failed for {source_name} because SET DOCUMENT Version was missing.',
        )

    # Enrichment
    enrich_pubmed_citations(manager, graph)  # this makes a commit so we need to store the identifier
    report_id = report.id

    if report.infer_origin:
        enrich_protein_and_rna_origins(graph)

    send_graph_summary_mail(graph, report, time.time() - t)

    # TODO split into second task
    celery_logger.info(f'inserting {graph} with {manager.engine.url}')
    try:
        network = manager.insert_graph(graph)
    except IntegrityError as e:
        manager.session.rollback()
        return finish_parsing(
            manager.session, report,
            'Upload Failed.', f'Upload Failed for {source_name}: {e}',
        )
    except OperationalError:
        manager.session.rollback()
        return finish_parsing(
            manager.session, report,
            'Upload Failed.', f'Upload Failed for {source_name} because database is locked',
        )
    except Exception as e:
        manager.session.rollback()
        return finish_parsing(
            manager.session, report,
            'Upload Failed.', f'Upload Failed for {source_name}: {e}',
        )

    # save in a variable because these get thrown away after commit
    network_id = network.id

    celery_logger.info(f'Stored network={network_id}.')

    celery_logger.info(f'Filling report={report_id} for network={network_id}')

    fill_out_report(graph=graph, network=network, report=report)
    report.time = time.time() - t

    celery_logger.info(f'Committing report={report_id} for network={network_id}')
    try:
        manager.session.commit()
    except Exception as e:
        manager.session.rollback()
        message = f'Problem filling out report={report_id} for {source_name}: {e}'
        make_mail(report, 'Filling out report failed', message)
        celery_logger.exception(message)
        return -1
    else:
        make_mail(report, 'Parsing succeeded', f'Parsing succeeded for {source_name}')
        return dict(network_id=network_id, report_id=report_id)
    finally:
        manager.session.close()


@celery_app.task(name='run-heat-diffusion')
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

    with current_app.app_context():
        mail = current_app.extensions.get('mail')
        if mail is not None:
            mail.send_message(
                subject=f'Heat Diffusion Workflow [{experiment_id}] is Complete',
                recipients=[email],
                body=message,
                sender=current_app.config[MAIL_DEFAULT_SENDER],
            )

    return experiment_id


@celery_app.task(name='upload-json')
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
        graph = from_nodelink(payload)
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


def finish_parsing(session, report: Report, subject: str, body: str) -> str:
    """Add the message to the report and commit the current session."""
    make_mail(report, subject, body)
    report.message = body
    session.commit()
    return body


def make_mail(report: Report, subject: str, body: str) -> None:
    """Send a mail with the given subject and body."""
    with current_app.app_context():
        mail = current_app.extensions.get('mail')
        if mail is not None:
            mail.send_message(
                subject=subject,
                recipients=[report.user.email],
                body=body,
                sender=current_app.config[MAIL_DEFAULT_SENDER],
            )


def send_graph_summary_mail(graph: BELGraph, report: Report, time_difference: float) -> None:
    """Send a mail with a summary.

    :param graph:
    :param report:
    :param time_difference: The time difference to log
    """
    with current_app.app_context():
        mail = current_app.extensions.get('mail')
        write_reports = current_app.config['WRITE_REPORTS']
        if not mail and not write_reports:
            return

        html = render_template(
            'email_report.html',
            graph=graph,
            report=report,
            time=time_difference,
            summary=BELGraphSummary.from_graph(graph),
        )

        if mail is not None:
            mail.send_message(
                subject=f'Parsing Report for {graph}',
                recipients=[report.user.email],
                body=f'Below is the parsing report for {graph}, completed in {time_difference:.2f} seconds.',
                html=html,
                sender=current_app.config[MAIL_DEFAULT_SENDER],
            )
        elif current_app.config['WRITE_REPORTS']:
            path = os.path.join(os.path.expanduser('~'), 'Downloads', f'report_{report.id}.html')

            try:
                with open(path, 'w') as file:
                    print(html, file=file)
                celery_logger.info(f'HTML printed to file at: {path}')
            except FileNotFoundError:
                celery_logger.info('no file printed.')
