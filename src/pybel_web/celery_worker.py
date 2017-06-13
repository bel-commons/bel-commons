# -*- coding: utf-8 -*-

import logging
import os

import requests.exceptions
from celery.utils.log import get_task_logger
from flask_mail import Message
from six import StringIO
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import from_lines
from pybel.manager import build_manager
from pybel.parser.parse_exceptions import InconsistentDefinitionError
from pybel_tools.constants import BMS_BASE
from pybel_tools.ioutils import convert_recursive
from pybel_tools.mutation import add_canonical_names, fix_pubmed_citations
from .application import create_application, create_celery
from .constants import integrity_message
from .models import Report
from .utils import run_experiment

app, mail = create_application(get_mail=True)
celery = create_celery(app)

log = get_task_logger(__name__)


def parse_folder(connection, folder, **kwargs):
    manager = build_manager(connection)
    convert_recursive(
        os.path.join(os.environ[BMS_BASE], folder),
        connection=manager,
        upload=True,
        infer_central_dogma=True,
        enrich_citations=True,
        enrich_genes=True,
        enrich_go=True,
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
    parse_folder(connection, 'aetionomy')


@celery.task(name='parse-selventa')
def parse_selventa(connection):
    """Converts the Selventa folder in the BMS"""
    parse_folder(connection, 'selventa', citation_clearing=False)


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
    except requests.exceptions.ConnectionError as e:
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

    try:
        network = manager.insert_graph(graph, store_parts=store_parts)
    except IntegrityError:
        message = integrity_message.format(graph.name, graph.version)
        log.exception(message)
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
        message = 'Database is locked. Unable to upload.'
        return message
    except Exception as e:
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
        message = 'Problem with reporting service.'
        log.exception(message)
        manager.session.rollback()
        return message

    do_okay_mail(current_user_email, graph)

    return network.id


@celery.task(name='run-cmpa')
def run_cmpa(connection, network_id, lines, filename, description, gene_column, data_column, permutations, sep):
    log.info('Starting analysis task')
    manager = build_manager(connection)
    experiment = run_experiment(
        file=StringIO('\n'.join(lines)),
        filename=filename,
        description=description,
        gene_column=gene_column,
        data_column=data_column,
        permutations=permutations,
        manager=manager,
        network_id=network_id,
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
