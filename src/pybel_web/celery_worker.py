# -*- coding: utf-8 -*-

"""Runs the Celery worker for BEL Commons.

Use: :code:`python3 -m celery -A pybel_web.celery_worker.celery worker` while also laughing at how ridiculously
redundant this nomenclature is.
"""

import hashlib
import logging
import os

import requests.exceptions
import time
from celery.utils.log import get_task_logger
from flask import render_template
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import from_json, to_bel_path, to_bytes
from pybel.constants import HASH, METADATA_CONTACT, METADATA_DESCRIPTION, METADATA_LICENSES
from pybel.manager.citation_utils import enrich_pubmed_citations
from pybel.parser.exc import InconsistentDefinitionError
from pybel.resources.exc import ResourceError
from pybel.struct.mutation import enrich_protein_and_rna_origins
from pybel.tokens import node_to_tuple
from pybel_tools.mutation import add_canonical_names
from pybel_tools.utils import enable_cool_mode
from pybel_web.application import create_application
from pybel_web.celery_utils import create_celery
from pybel_web.constants import get_admin_email, integrity_message, merged_document_folder
from pybel_web.manager import WebManager
from pybel_web.manager_utils import (
    fill_out_report, get_network_summary_dict, insert_graph, make_graph_summary, run_heat_diffusion_helper,
)

celery_logger = get_task_logger(__name__)
log = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)
enable_cool_mode()  # turn off warnings for compilation
celery_logger.setLevel(logging.DEBUG)
log.setLevel(logging.DEBUG)

app = create_application()
mail = app.extensions.get('mail')
celery = create_celery(app)

dumb_belief_stuff = {
    METADATA_DESCRIPTION: {'Document description'},
    METADATA_CONTACT: {'your@email.com'},
    METADATA_LICENSES: {'Document license'}
}

pbw_sender = ("BEL Commons", 'bel-commons@scai.fraunhofer.de')


def add_identifiers(graph):  # FIXME this function shouldn't have to exist.
    """Adds stable node and edge identifiers to the graph, in-place using the PyBEL
    node and edge hashes as a hexadecimal str.

    :param pybel.BELGraph graph: A BEL Graph
    """
    for node, data in graph.iter_node_data_pairs():
        if HASH in data:
            continue

        canonical_node_tuple = node_to_tuple(data)
        canonical_node_hash = graph.hash_node(canonical_node_tuple)
        graph.node[node][HASH] = canonical_node_hash


@celery.task(name='debug-task')
def run_debug_task():
    """Run the debug task."""
    celery_logger.info('running celery debug task')
    log.info('running celery debug task')
    return 6 + 2


@celery.task(name='summarize-bel')
def summarize_bel(connection, report_id):
    """Parse a BEL script asynchronously and email feedback.

    :param str connection: A connection to build the manager
    :param int report_id: A report to parse
    """
    manager = WebManager(connection=connection)

    t = time.time()
    report = manager.get_report_by_id(report_id)
    source_name = report.source_name

    def make_mail(subject, body):
        if not mail:
            return

        with app.app_context():
            mail.send_message(
                subject=subject,
                recipients=[report.user.email],
                body=body,
                sender=pbw_sender,
            )

    def finish_parsing(subject, body):
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
        graph = report.parse_graph(manager=manager)

    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError):
        message = 'Connection to resource could not be established.'
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    except InconsistentDefinitionError as e:
        message = 'Parsing failed for {} because {} was redefined on line {}.'.format(source_name, e.definition,
                                                                                      e.line_number)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    except Exception as e:
        message = 'Parsing failed for {} from a general error: {}'.format(source_name, e)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    time_difference = time.time() - t

    send_summary_mail(manager, graph, report, time_difference)

    report.time = time_difference
    report.completed = True
    manager.session.add(report)
    manager.session.commit()

    celery_logger.info('finished in %.2f seconds', time.time() - t)

    manager.session.close()

    return 0


@celery.task(name='upload-bel')
def upload_bel(connection, report_id, enrich_citations=False):
    """Parse a BEL script asynchronously and send email feedback.

    :param str connection: The connection string
    :param int report_id: Report identifier
    """
    manager = WebManager(connection=connection)

    t = time.time()
    report = manager.get_report_by_id(report_id)

    report_id = report.id
    source_name = report.source_name

    celery_logger.info('Starting parse task for %s (report %s)', source_name, report_id)

    def make_mail(subject, body):
        if not mail:
            return

        with app.app_context():
            mail.send_message(
                subject=subject,
                recipients=[report.user.email],
                body=body,
                sender=pbw_sender,
            )

    def finish_parsing(subject, body):
        make_mail(subject, body)
        report.message = body
        manager.session.commit()
        return body

    celery_logger.info('parsing graph')

    try:
        graph = report.parse_graph(manager=manager)

    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        message = 'Connection to resource could not be established: {}'.format(e)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    except InconsistentDefinitionError as e:
        message = 'Parsing failed for {} because {} was redefined on line {}.'.format(source_name, e.definition,
                                                                                      e.line_number)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    except Exception as e:
        message = 'Parsing failed for {} from a general error: {}'.format(source_name, e)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    if not graph.name:
        message = 'Parsing failed for {} because SET DOCUMENT Name was missing.'.format(source_name)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    if not graph.version:
        message = 'Parsing failed for {} because SET DOCUMENT Version was missing.'.format(source_name)
        return finish_parsing('Parsing Failed for {}'.format(source_name), message)

    problem = {
        k: v
        for k, v in graph.document.items()
        if k in dumb_belief_stuff and v in dumb_belief_stuff[k]
    }

    if problem:
        message = '{} was rejected because it has "default" metadata: {}'.format(source_name, problem)
        return finish_parsing('Rejected {}'.format(source_name), message)

    send_summary_mail(graph, report, time.time() - t)

    network = manager.get_network_by_name_version(graph.name, graph.version)

    if network is not None:
        message = integrity_message.format(graph.name, graph.version)

        if network.report.user == report.user:  # This user is being a fool
            return finish_parsing('Uploading Failed for {}'.format(source_name), message)

        if hashlib.sha1(network.blob).hexdigest() != hashlib.sha1(to_bytes(graph)).hexdigest():
            with app.app_context():
                app.extensions['mail'].send_message(
                    subject='Possible attempted Espionage',
                    recipients=[get_admin_email()],
                    body='The following user ({} {}) may have attempted espionage of network: {}'.format(
                        report.user.id,
                        report.user.email,
                        network
                    ),
                    sender=pbw_sender,
                )

            return finish_parsing('Upload Failed for {}'.format(source_name), message)

        # Grant rights to this user
        network.users.append(report.user)
        manager.session.commit()

        message = 'Granted rights for {} to {} after parsing {}'.format(network, report.user, source_name)
        return finish_parsing('Granted Rights from {}'.format(source_name), message)

    celery_logger.info('enriching graph')
    add_canonical_names(graph)
    add_identifiers(graph)

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

    upload_failed_text = 'Upload Failed for {}'.format(source_name)

    try:
        celery_logger.info('inserting %s with %s', graph, manager.engine.url)
        network = manager.insert_graph(graph, store_parts=app.config.get("PYBEL_USE_EDGE_STORE", True))

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

    celery_logger.info('done storing [%d]. starting to make report.', network.id)

    graph_summary = make_graph_summary(graph)

    try:
        fill_out_report(network, report, graph_summary)
        report.time = time.time() - t

        manager.session.add(report)
        manager.session.commit()

        celery_logger.info('report #%d complete [%d]', report.id, network.id)
        make_mail('Uploaded succeeded for {} ({})'.format(graph, source_name),
                  '{} ({}) is done parsing. Check the network list page.'.format(source_name, graph))

        return network.id

    except Exception as e:
        manager.session.rollback()
        make_mail('Report unsuccessful for {}'.format(source_name), str(e))
        celery_logger.exception('Problem filling out report')
        return -1

    finally:
        manager.session.close()


@celery.task(name='merge-project')
def merge_project(connection, user_id, project_id):
    """Merges the graphs in a project and does stuff

    :param str connection: A connection to build the manager
    :param int user_id: The database identifier of the user
    :param int project_id: The database identifier of the project
    """
    manager = WebManager(connection=connection)

    t = time.time()

    user = manager.get_user_by_id(user_id)
    project = manager.get_project_by_id(project_id)
    graph = project.as_bel()

    graph.name = hashlib.sha1(to_bytes(graph)).hexdigest()
    graph.version = '1.0.0'

    path = os.path.join(merged_document_folder, '{}.bel'.format(graph.name))

    url_link = '{}/download/bel/{}'.format(app.config['PYBEL_MERGE_SERVER_PREFIX'], graph.name)

    if os.path.exists(path):
        celery_logger.warning('Already merged in: %s', path)
        celery_logger.warning('Download from: %s', url_link)
    else:
        to_bel_path(graph, path)
        celery_logger.info('Merge took %.2f seconds to %s', time.time() - t, path)

    celery_logger.info('Download from: %s', url_link)

    if mail is not None:
        mail.send_message(
            subject='Merged BEL Project BEL Resources: {} '.format(project.name),
            recipients=[user.email],
            body='The BEL documents from {} were merged. '
                 'The resulting BEL script is attached and '
                 'given the serial number {}. Download from: {}'.format(project.name, graph.name, url_link),
            sender=pbw_sender
        )

    return 1


@celery.task(name='run-heat-diffusion')
def run_heat_diffusion(connection, experiment_id):
    """Runs the heat diffusion workflow.

    :param str connection: A connection to build the manager
    :param int experiment_id:
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

    message = 'Experiment {} on query {} with {} has completed'.format(
        experiment_id,
        query_id,
        source_name,
    )

    if mail is not None:
        with app.app_context():
            mail.send_message(
                subject='Heat Diffusion Workflow [{}] is Complete'.format(experiment_id),
                recipients=[email],
                body=message,
                sender=pbw_sender,
            )

    return experiment_id


@celery.task(name='upload-json')
def upload_json(connection, user_id, payload):
    """Receives a JSON serialized BEL graph

    :param str connection: A connection to build the manager
    :param int user_id: the ID of the user to associate with the graph
    :param payload: JSON dictionary for :func:`pybel.from_json`
    """
    manager = WebManager(connection=connection)
    user = manager.get_user_by_id(user_id)

    try:
        graph = from_json(payload)
    except Exception:
        celery_logger.exception('unable to parse JSON')
        return -1

    try:
        insert_graph(manager, graph, user)
    except Exception:
        celery_logger.exception('unable to insert graph')
        manager.session.rollback()
        return -2

    return 0


def send_summary_mail(graph, report, time_difference):
    """Send a mail with a summary.

    :param pybel.BELGraph graph:
    :param Report report:
    :param float time_difference: The time difference to log
    """
    with app.app_context():
        html = render_template(
            'email_report.html',
            graph=graph,
            report=report,
            time=time_difference,
            **get_network_summary_dict(graph)
        )

        if mail is not None:
            mail.send_message(
                subject='Parsing Report for {}'.format(graph),
                recipients=[report.user.email],
                body='Below is the parsing report for {}, completed in {:.2f} seconds.'.format(graph, time_difference),
                html=html,
                sender=pbw_sender,
            )
        else:
            path = os.path.join(os.path.expanduser('~'), 'Downloads', 'report_{}.html'.format(report.id))

            try:
                with open(path, 'w') as file:
                    print(html, file=file)
                celery_logger.info('HTML printed to file at: %s', path)
            except FileNotFoundError:
                celery_logger.info('no file printed.')
