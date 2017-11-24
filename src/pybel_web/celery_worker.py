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
from six.moves.cPickle import dumps, loads
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import from_json, from_url, to_bel_path, to_bytes
from pybel.constants import METADATA_CONTACT, METADATA_DESCRIPTION, METADATA_LICENSES
from pybel.manager.cache_manager import EdgeAddError
from pybel.manager.citation_utils import enrich_pubmed_citations
from pybel.manager.models import Network
from pybel.parser.parse_exceptions import InconsistentDefinitionError
from pybel.struct import union
from pybel_tools.mutation import add_canonical_names, add_identifiers, infer_central_dogma
from pybel_tools.utils import enable_cool_mode
from pybel_web.application import create_application
from pybel_web.celery_utils import create_celery
from pybel_web.constants import CHARLIE_EMAIL, DANIEL_EMAIL, integrity_message, merged_document_folder
from pybel_web.models import Experiment, Project, Report, User
from pybel_web.utils import calculate_scores, fill_out_report, make_graph_summary, manager

log = get_task_logger(__name__)

logging.basicConfig(level=logging.DEBUG)
enable_cool_mode()  # turn off warnings for compilation
log.setLevel(logging.DEBUG)

app = create_application()
celery = create_celery(app)

log.info('created celery worker')
log.info('using connection: %s', app.config['PYBEL_CONNECTION'])

dumb_belief_stuff = {
    METADATA_DESCRIPTION: {'Document description'},
    METADATA_CONTACT: {'your@email.com'},
    METADATA_LICENSES: {'Document license'}
}

pbw_sender = ("PyBEL Web", 'pybel@scai.fraunhofer.de')


@celery.task(name='parse-url')
def parse_by_url(url):
    """Parses a graph at the given URL resource"""
    # FIXME add proper exception handling and feedback
    try:
        graph = from_url(url, manager=manager)
    except:
        return 'Parsing failed for {}. '.format(url)

    try:
        network = manager.insert_graph(graph, store_parts=app.config.get("PYBEL_USE_EDGE_STORE""", True))
        return network.id
    except:
        manager.session.rollback()
        return 'Inserting failed for {}'.format(url)
    finally:
        manager.session.close()


@celery.task(name='pybelparser')
def async_parser(report_id):
    """Asynchronously parses a BEL script and sends email feedback

    :param int report_id: Report identifier
    """
    t = time.time()

    report = manager.session.query(Report).get(report_id)

    if report is None:
        raise ValueError('Report {} not found'.format(report_id))

    report_id = report.id
    source_name = report.source_name

    log.info('Starting parse task for %s (report %s)', source_name, report_id)

    def make_mail(subject, body):
        if 'mail' not in app.extensions:
            return

        with app.app_context():
            app.extensions['mail'].send_message(
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

    try:
        log.info('parsing graph')
        graph = report.parse_graph(manager=manager)

    except requests.exceptions.ConnectionError:
        message = 'Connection to resource could not be established.'
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

    network = manager.session.query(Network).filter(Network.name == graph.name,
                                                    Network.version == graph.version).one_or_none()

    if network is not None:
        message = integrity_message.format(graph.name, graph.version)

        if network.report.user == report.user:  # This user is being a fool
            return finish_parsing('Uploading Failed for {}'.format(source_name), message)

        if hashlib.sha1(network.blob).hexdigest() != hashlib.sha1(to_bytes(graph)).hexdigest():
            with app.app_context():
                app.extensions['mail'].send_message(
                    subject='Possible attempted Espionage',
                    recipients=[CHARLIE_EMAIL, DANIEL_EMAIL],
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

    try:
        log.info('enriching graph')
        add_canonical_names(graph)

        add_identifiers(graph)

        if report.infer_origin:
            infer_central_dogma(graph)

        enrich_pubmed_citations(graph, manager=manager)

    except (IntegrityError, OperationalError):
        manager.session.rollback()
        log.exception('problem with database while fixing citations')

    except:
        log.exception('problem fixing citations')

    upload_failed_text = 'Upload Failed for {}'.format(source_name)

    try:
        log.info('inserting %s with %s', graph, manager.engine.url)
        #logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        network = manager.insert_graph(graph, store_parts=app.config.get("PYBEL_USE_EDGE_STORE", True))

    except IntegrityError:
        manager.session.rollback()
        message = integrity_message.format(graph.name, graph.version)
        return finish_parsing(upload_failed_text, message)

    except OperationalError:
        manager.session.rollback()
        message = 'Database is locked. Unable to upload.'
        return finish_parsing(upload_failed_text, message)

    except EdgeAddError as e:
        manager.session.rollback()
        message = "Error storing in database: {}.\n\nPayload: {}".format(e, json.dumps(e.data, indent=2))
        return finish_parsing(upload_failed_text, message)

    except Exception as e:
        manager.session.rollback()
        message = "Error storing in database: {}".format(e)
        return finish_parsing(upload_failed_text, message)

    log.info('done storing [%d]. starting to make report.', network.id)

    graph_summary = make_graph_summary(graph)

    try:
        fill_out_report(network, report, graph_summary)
        report.time = time.time() - t

        manager.session.add(report)
        manager.session.commit()

        log.info('report #%d complete [%d]', report.id, network.id)
        make_mail('Successfully uploaded {} ({})'.format(source_name, graph),
                  '{} ({}) is done parsing. Check the network list page.'.format(source_name, graph))

        return network.id

    except Exception as e:
        manager.session.rollback()
        make_mail('Report unsuccessful for {}'.format(source_name), str(e))
        log.exception('Problem filling out report')
        return -1

    finally:
        manager.session.close()


@celery.task(name='merge-project')
def merge_project(user_id, project_id):
    """Merges the graphs in a project and does stuff

    :param int user_id: The database identifier of the user
    :param int project_id: The database identifier of the project
    """
    t = time.time()

    user = manager.session.query(User).get(user_id)
    project = manager.session.query(Project).get(project_id)

    graphs = [network.as_bel() for network in project.networks]

    graph = union(graphs)

    graph.name = hashlib.sha1(to_bytes(graph)).hexdigest()
    graph.version = '1.0.0'

    path = os.path.join(merged_document_folder, '{}.bel'.format(graph.name))

    url_link = '{}/download/bel/{}'.format(app.config['PYBEL_MERGE_SERVER_PREFIX'], graph.name)

    if os.path.exists(path):
        log.warning('Already merged in: %s', path)
        log.warning('Download from: %s', url_link)
    else:
        to_bel_path(graph, path)
        log.info('Merge took %.2f seconds to %s', time.time() - t, path)

    if 'mail' not in app.extensions:
        log.warning('Download from: %s', url_link)
        return

    app.extensions['mail'].send_message(
        subject='Merged BEL Project BEL Resources: {} '.format(project.name),
        recipients=[user.email],
        body='The BEL documents from {} were merged. '
             'The resulting BEL script is attached and '
             'given the serial number {}. Download from: {}'.format(project.name, graph.name, url_link),
        sender=pbw_sender
    )

    return 1


@celery.task(name='run-cmpa')
def run_cmpa(experiment_id):
    """Runs the CMPA analysis

    :param int experiment_id:
    """
    log.info('starting experiment %s', experiment_id)

    experiment = manager.session.query(Experiment).get(experiment_id)

    query_id = experiment.query_id
    source_name = experiment.source_name
    email = experiment.user.email

    log.info('executing query')
    graph = experiment.query.run(manager)

    df = loads(experiment.source)

    gene_column = experiment.gene_column
    data_column = experiment.data_column

    df_cols = [gene_column, data_column]

    data = {
        gene: value
        for _, gene, value in df.loc[df[gene_column].notnull(), df_cols].itertuples()
    }

    log.info('calculating scores')
    scores = calculate_scores(graph, data, experiment.permutations)

    experiment.result = dumps(scores)
    experiment.completed = True

    try:
        manager.session.add(experiment)
        manager.session.commit()
    except:
        manager.session.rollback()
        return -1
    finally:
        manager.session.close()

    message = 'Experiment {} on query {} with {} has completed'.format(
        experiment_id,
        query_id,
        source_name
    )

    if 'mail' in app.extensions:
        with app.app_context():
            app.extensions['mail'].send_message(
                subject='CMPA Analysis complete',
                recipients=[email],
                body=message,
                sender=pbw_sender,
            )

    return experiment_id


@celery.task(name='receive-network')
def async_recieve(payload):
    """Receives a JSON serialized BEL graph"""
    try:
        graph = from_json(payload)
    except:
        return -1

    try:
        manager.insert_graph(graph, store_parts=app.config.get("PYBEL_USE_EDGE_STORE", True))
    except IntegrityError:
        manager.session.rollback()
        return -1
    except:
        log.exception('Upload error')
        manager.session.rollback()
        return -1

    return 0
