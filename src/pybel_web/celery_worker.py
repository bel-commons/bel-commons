# -*- coding: utf-8 -*-

import hashlib
import logging
import os

import requests.exceptions
from celery.utils.log import get_task_logger
from flask_mail import Message
from six import StringIO
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import from_lines, from_url, to_bytes
from pybel.constants import METADATA_DESCRIPTION, METADATA_CONTACT, METADATA_LICENSES
from pybel.manager import build_manager
from pybel.manager.models import Network
from pybel.parser.parse_exceptions import InconsistentDefinitionError
from pybel_tools.constants import BMS_BASE
from pybel_tools.ioutils import convert_directory
from pybel_tools.mutation import add_canonical_names, fix_pubmed_citations
from .application import create_application, create_celery
from .constants import CHARLIE_EMAIL, DANIEL_EMAIL
from .constants import integrity_message
from .models import Report, User
from .utils import run_experiment

app, mail = create_application(get_mail=True)
celery = create_celery(app)

log = get_task_logger(__name__)

dumb_belief_stuff = {
    METADATA_DESCRIPTION: {'Document description'},
    METADATA_CONTACT: {'your@email.com'},
    METADATA_LICENSES: {'Document license'}
}


def parse_folder(connection, folder, **kwargs):
    manager = build_manager(connection)
    convert_directory(
        folder,
        connection=manager,
        upload=True,
        infer_central_dogma=True,
        enrich_citations=True,
        enrich_genes=True,
        enrich_go=False,
        **kwargs
    )


def do_mail(current_user_email, subject, body):
    if 'mail' not in app.extensions:
        return

    with app.app_context():
        mail.send(Message(
            subject=subject,
            recipients=[current_user_email],
            body=body,
            sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
        ))


def do_okay_mail(current_user_email, graph):
    do_mail(
        current_user_email,
        subject='Parsing complete',
        body='{} is done parsing. Check the network list page.'.format(graph)
    )


@celery.task(name='parse-aetionomy')
def parse_aetionomy(connection):
    """Converts the Aetionomy folder in the BMS"""
    folder = os.path.join(os.environ[BMS_BASE], 'aetionomy')
    parse_folder(connection, 'aetionomy')


@celery.task(name='parse-selventa')
def parse_selventa(connection):
    """Converts the Selventa folder in the BMS"""
    folder = os.path.join(os.environ[BMS_BASE], 'selventa')
    parse_folder(connection, folder, citation_clearing=False)


@celery.task(name='parse-bel4imocede')
def parse_bel4imocede(connection):
    """Converts the BEL4IMOCEDE folder in the BMS"""
    folder = os.path.join(os.environ[BMS_BASE], 'BEL4IMOCEDE')
    parse_folder(connection, folder)


@celery.task(name='parse-ptsd')
def parse_ptsd(connection):
    """Converts the CVBIO PTSD folder in the BMS"""
    folder = os.path.join(os.environ[BMS_BASE], 'cvbio', 'PTSD')
    parse_folder(connection, folder)


@celery.task(name='parse-tbi')
def parse_tbi(connection):
    """Converts the CVBIO TBI folder in the BMS"""
    folder = os.path.join(os.environ[BMS_BASE], 'cvbio', 'TBI')
    parse_folder(connection, folder)


@celery.task(name='parse-bms')
def parse_selventa(connection):
    """Converts the entire BMS"""
    parse_folder(connection, os.environ[BMS_BASE])


@celery.task(name='parse-url')
def parse_by_url(connection, url):
    """Parses a graph at the given URL resource"""
    # FIXME add proper exception handling and feedback

    manager = build_manager(connection)

    try:
        graph = from_url(url, manager=manager)
    except:
        return 'Parsing failed'

    try:
        network = manager.insert_graph(graph)
    except:
        manager.session.rollback()
        return 'Error parsing'

    return network.id


@celery.task(name='pybelparser')
def async_parser(lines, connection, current_user_id, current_user_email, public, allow_nested=False,
                 citation_clearing=False, store_parts=False):
    """Asynchronously parses a BEL script and sends email feedback"""
    log.info('Starting parse task')
    manager = build_manager(connection)

    try:
        graph = from_lines(
            lines,
            manager=manager,
            allow_nested=allow_nested,
            citation_clearing=citation_clearing
        )
        add_canonical_names(graph)
        fix_pubmed_citations(graph)

    except requests.exceptions.ConnectionError:
        message = 'Connection to resource could not be established.'
        log.exception(message)

        with app.app_context():
            mail.send(Message(
                subject='Parsing Failed',
                recipients=[current_user_email],
                body=message,
                sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
            ))

        return message

    except InconsistentDefinitionError as e:
        message = 'Parsing failed because {} was redefined on line {}.'.format(e.definition, e.line_number)
        log.exception(message)
        with app.app_context():
            mail.send(Message(
                subject='Parsing Failed',
                recipients=[current_user_email],
                body=message,
                sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
            ))

        return message

    except Exception as e:
        message = 'Parsing failed from a general error: {}'.format(e)
        log.exception(message)

        with app.app_context():
            mail.send(Message(
                subject='Parsing Failed',
                recipients=[current_user_email],
                body=message,
                sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
            ))

        return message

    problem = {
        k: v
        for k, v in graph.document.items()
        if k in dumb_belief_stuff and v in dumb_belief_stuff[k]
    }

    if problem:
        message = 'Your document was rejected because it has "default" metadata: {}'.format(problem)

        with app.app_context():
            mail.send(Message(
                subject='Document Rejected',
                recipients=[current_user_email],
                body=message,
                sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
            ))

        return message

    network = manager.session.query(Network).filter(Network.name == graph.name,
                                                    Network.version == graph.version).one_or_none()

    if network is not None:
        message = integrity_message.format(graph.name, graph.version)

        if network.report.user_id == current_user_id:  # This user is being a fool
            log.warning('%s %s', current_user_email, message)
            manager.session.rollback()

            with app.app_context():
                mail.send(Message(
                    subject='Upload Failed',
                    recipients=[current_user_email],
                    body=message,
                    sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
                ))

            return message

        if hashlib.sha1(network.blob).hexdigest() != hashlib.sha1(to_bytes(network)):
            with app.app_context():
                mail.send(Message(
                    subject='Upload Failed',
                    recipients=[current_user_email],
                    body=message,
                    sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
                ))

                mail.send(Message(
                    subject='Possible attempted Espionage',
                    recipients=[CHARLIE_EMAIL, DANIEL_EMAIL],
                    body='The following user ({} {}) may have attempted espionage of network: {}'.format(
                        current_user_id,
                        current_user_email,
                        network
                    ),
                    sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
                ))
            return message

        # Grant rights to this user
        user = manager.session.query(User).get(current_user_id)
        network.users.append(user)
        manager.session.commit()

        return 'Granted rights for {} to {}'.format(network, user)

    try:
        network = manager.insert_graph(graph, store_parts=store_parts)

    except IntegrityError:
        message = integrity_message.format(graph.name, graph.version)
        log.warning('%s %s', current_user_email, message)
        manager.session.rollback()

        with app.app_context():
            mail.send(Message(
                subject='Upload Failed',
                recipients=[current_user_email],
                body=message,
                sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
            ))

        return message

    except OperationalError:
        manager.session.rollback()

        message = 'Database is locked. Unable to upload.'
        log.exception(message)

        return message

    except Exception as e:
        manager.session.rollback()

        message = "Error storing in database: {}".format(e)
        log.exception(message)

        with app.app_context():
            mail.send(Message(
                subject='Upload Failed',
                recipients=[current_user_email],
                body=message,
                sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
            ))

        return message

    log.info('done storing [%d]', network.id)

    try:
        report = Report(
            network=network,
            user_id=current_user_id,
            number_nodes=graph.number_of_nodes(),
            number_edges=graph.number_of_edges(),
            number_warnings=len(graph.warnings),
            public=public,
        )
        manager.session.add(report)
        manager.session.commit()

    except IntegrityError:
        manager.session.rollback()

        message = 'Problem with reporting service.'
        log.exception(message)

        return message

    except OperationalError:
        manager.session.rollback()

        log.exception('Problem with reporting service')

    do_okay_mail(current_user_email, graph)

    return network.id


@celery.task(name='run-cmpa')
def run_cmpa(connection, network_id, lines, filename, description, gene_column, data_column, permutations, sep):
    log.info('Starting analysis task')
    manager = build_manager(connection)

    network = manager.session.query(Network).get(network_id)

    experiment = run_experiment(
        manager,
        file=StringIO('\n'.join(lines)),
        filename=filename,
        description=description,
        gene_column=gene_column,
        data_column=data_column,
        permutations=permutations,
        network=network,
        sep=sep,
    )
    return experiment.id


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Sets up the periodic tasks to be run asynchronously by Celery"""
    recipient = app.config.get('PYBEL_WEB_REPORT_RECIPIENT')
    log.warning('Recipient value: %s', recipient)


if __name__ == '__main__':
    logging.basicConfig(level=20)
    logging.getLogger('pybel.parser').setLevel(50)
    log.setLevel(20)
