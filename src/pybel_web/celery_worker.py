# -*- coding: utf-8 -*-

"""
Run the celery worker with:

:code:`python3 -m celery -A pybel_web.celery_worker.celery worker`

While also laughing at how ridiculously redundant this nomenclature is.
"""

import hashlib
import json
import logging
import os
import time

import requests.exceptions
from celery.utils.log import get_task_logger
from flask import render_template
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import from_cbn_jgif, from_json, to_bel_path, to_bytes, to_database
from pybel.constants import METADATA_CONTACT, METADATA_DESCRIPTION, METADATA_LICENSES
from pybel.manager import Manager
from pybel.manager.citation_utils import enrich_pubmed_citations
from pybel.manager.models import Network
from pybel.parser.exc import InconsistentDefinitionError
from pybel.resources.exc import ResourceError
from pybel.struct import strip_annotations
from pybel_tools.mutation import add_canonical_names, add_identifiers, infer_central_dogma
from pybel_tools.utils import enable_cool_mode
from pybel_web.application import create_application
from pybel_web.celery_utils import create_celery
from pybel_web.constants import get_admin_email, integrity_message, merged_document_folder
from pybel_web.manager_utils import fill_out_report, insert_graph, make_graph_summary, run_cmpa_helper
from pybel_web.models import Experiment, Project, User
from pybel_web.utils import get_network_summary_dict, safe_get_report

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


@celery.task(name='debug-task')
def run_debug_task():
    """Runts a debug task"""
    celery_logger.info('running celery debug task')
    log.info('running celery debug task')
    return 6 + 2


@celery.task(name='summarize-bel')
def summarize_bel(connection, report_id):
    """Asynchronously parses a BEL script and emails feedback

    :param str connection: A connection to build the manager
    :param int report_id: A report to parse
    """
    manager = Manager(connection=connection)

    t = time.time()
    report = safe_get_report(manager, report_id)
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
        """Sends a message and finishes parsing

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

    send_summary_mail(graph, report, time_difference)

    report.time = time_difference
    report.completed = True
    manager.session.add(report)
    manager.session.commit()

    celery_logger.info('finished in %.2f seconds', time.time() - t)

    manager.session.close()

    return 0


@celery.task(name='upload-bel')
def upload_bel(connection, report_id, enrich_citations=False):
    """Asynchronously parses a BEL script and sends email feedback

    :param str connection: The connection string
    :param int report_id: Report identifier
    """
    manager = Manager(connection=connection)

    t = time.time()
    report = safe_get_report(manager, report_id)

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

    network_filter = and_(Network.name == graph.name, Network.version == graph.version)
    network = manager.session.query(Network).filter(network_filter).one_or_none()

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
        infer_central_dogma(graph)

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
    manager = Manager(connection=connection)

    t = time.time()

    user = manager.session.query(User).get(user_id)
    project = manager.session.query(Project).get(project_id)
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


@celery.task(name='run-cmpa')
def run_cmpa(connection, experiment_id):
    """Runs the CMPA analysis

    :param str connection: A connection to build the manager
    :param int experiment_id:
    """
    manager = Manager(connection=connection)
    experiment = manager.session.query(Experiment).get(experiment_id)

    query_id = experiment.query_id
    source_name = experiment.source_name
    email = experiment.user.email

    run_cmpa_helper(manager, experiment)

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
        source_name
    )

    if mail is not None:
        with app.app_context():
            mail.send_message(
                subject='CMPA Analysis complete',
                recipients=[email],
                body=message,
                sender=pbw_sender,
            )

    return experiment_id


@celery.task(name='upload-json')
def upload_json(connection, username, payload):
    """Receives a JSON serialized BEL graph

    :param str connection: A connection to build the manager
    :param str username: the email of the user to associate with the graph
    :param payload: JSON dictionary for :func:`pybel.from_json`
    """
    manager = Manager(connection=connection)

    user = manager.session.query(User).filter(User.email == username).one()

    try:
        graph = from_json(payload)
    except Exception:
        return -1

    try:
        insert_graph(manager, graph, user)
    except Exception:
        celery_logger.exception('Upload error')
        manager.session.rollback()
        return -1

    return 0


@celery.task(name='upload-cbn')
def upload_cbn(connection, dir_path):
    """Uploads CBN data to edge store

    :param str connection: A connection to build the manager
    :param str dir_path: Directory full of CBN JGIF files
    """
    manager = Manager(connection=connection)

    t = time.time()

    for jfg_path in os.listdir(dir_path):
        path = os.path.join(dir_path, jfg_path)

        celery_logger.info('opening %s', path)

        with open(path) as f:
            cbn_jgif_dict = json.load(f)
            graph = from_cbn_jgif(cbn_jgif_dict)

            strip_annotations(graph)
            enrich_pubmed_citations(manager, graph)
            to_database(graph, connection=manager)

    celery_logger.info('done in %.2f', time.time() - t)

    return 0


def send_summary_mail(graph, report, t):
    """Sends a mail with a summary

    :param pybel.BELGraph graph:
    :param Report report:
    :param float t:
    """
    with app.app_context():
        html = render_template(
            'email_report.html',
            graph=graph,
            report=report,
            time=t,
            **get_network_summary_dict(graph)
        )

        if mail is not None:
            mail.send_message(
                subject='Parsing Report for {}'.format(graph),
                recipients=[report.user.email],
                body='Below is the parsing report for {}, completed in {:.2f} seconds.'.format(graph, t),
                html=html,
                sender=pbw_sender,
            )
        else:
            path = os.path.join(os.path.expanduser('~'), 'Downloads', 'report_{}.html'.format(report.id))

            with open(path, 'w') as file:
                print(html, file=file)

            celery_logger.info('HTML printed to file at: %s', path)
