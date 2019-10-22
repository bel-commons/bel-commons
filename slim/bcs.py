# -*- coding: utf-8 -*-

"""BEL Commons Slim.

Run the celery worker with:

``python -m celery worker -A bcs.celery_app -l INFO -E``

- ``-E`` means monitor events.

Run the WSGI server with:

``python bcs.py``
"""

from __future__ import annotations

import hashlib
import logging
import time

import requests.exceptions
from bel_resources.exc import ResourceError
from celery import Celery
from celery.app.task import Task
from celery.utils.log import get_task_logger
from flask import Blueprint, Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from sqlalchemy.exc import IntegrityError, OperationalError
from wtforms.fields import SubmitField
from wtforms.validators import DataRequired

import bel_commons
import pybel
import pybel_tools
from bel_commons.application import PyBELSQLAlchemy, bootstrap
from bel_commons.celery_utils import parse_graph
from bel_commons.config import BELCommonsConfig
from bel_commons.constants import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from bel_commons.core.celery import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from bel_commons.manager_utils import fill_out_report
from bel_commons.models import Report
from pybel.constants import get_cache_connection
from pybel.io.new_jgif import to_jgif
from pybel.parser.exc import InconsistentDefinitionError

logger = logging.getLogger('bel_commons.slim')
celery_logger = get_task_logger('bel_commons.slim')

bel_commons_config = BELCommonsConfig.load()

flask_app = Flask('bcs')
flask_app.config.update(bel_commons_config.to_dict())

# Set SQLAlchemy defaults
flask_app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)
flask_app.config.setdefault(SQLALCHEMY_DATABASE_URI, get_cache_connection())
logger.info(f'database: {flask_app.config.get(SQLALCHEMY_DATABASE_URI)}')

# Set Celery defaults
flask_app.config.setdefault(CELERY_RESULT_BACKEND, f'db+{flask_app.config[SQLALCHEMY_DATABASE_URI]}')

UPLOAD_URL = 'UPLOAD_URL'

##########
# CELERY #
##########

celery_app = Celery(
    flask_app.import_name,
    broker=flask_app.config[CELERY_BROKER_URL],
    backend=flask_app.config[CELERY_RESULT_BACKEND],
)

logger.info(f'celery_app={celery_app}')

celery_app.conf.update(flask_app.config)

bootstrap.init_app(flask_app)

db = PyBELSQLAlchemy(flask_app)
manager = db.manager


@celery_app.task(bind=True)  # noqa: C901
def parse(task: Task, report_id: int):
    """Parse a BEL script asynchronously and send email feedback."""
    if not task.request.called_directly:
        task.update_state(state='STARTED')

    t = time.time()
    report = manager.get_report_by_id(report_id)

    report_id, source_name = report.id, report.source_name

    celery_logger.info(f'Starting parse task for {source_name} (report {report_id})')

    def finish_parsing(body: str) -> str:
        report.message = body
        manager.session.commit()
        return body

    celery_logger.info('parsing graph')

    try:
        graph = parse_graph(report=report, manager=manager, task=task)
    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        message = f'Parsing Failed for {source_name}. Connection to resource could not be established: {e}'
        return finish_parsing(message)
    except InconsistentDefinitionError as e:
        message = f'Parsing Failed for {source_name} because {e.definition} was redefined on line {e.line_number}'
        return finish_parsing(message)
    except Exception as e:
        message = f'Parsing Failed for {source_name} from a general error: {e}'
        return finish_parsing(message)

    if not graph.name:
        return finish_parsing(f'Parsing Failed for {source_name} because SET DOCUMENT Name was missing.')
    if not graph.version:
        return finish_parsing(f'Parsing Failed for {source_name} because SET DOCUMENT Version was missing.')

    # TODO split into second task
    try:
        celery_logger.info(f'inserting {graph} with {manager.engine.url}')
        network = manager.insert_graph(graph)

    except IntegrityError as e:
        manager.session.rollback()
        return finish_parsing(f'Upload Failed for {source_name}: {e}')

    except OperationalError:
        manager.session.rollback()
        return finish_parsing(f'Upload Failed for {source_name} because database is locked')

    except Exception as e:
        manager.session.rollback()
        return finish_parsing(f'Upload Failed for {source_name}: {e}')

    celery_logger.info(f'done storing [network_id={network.id}]. starting to make report.')

    try:
        fill_out_report(graph=graph, network=network, report=report)
        report.time = time.time() - t

        manager.session.add(report)
        manager.session.commit()

        celery_logger.info(f'report #{report.id} complete [{network.id}]')

        return {
            'network_id': network.id,
        }
    except Exception as e:
        manager.session.rollback()
        celery_logger.exception(f'Problem filling out report: {e}')
        return -1
    finally:
        manager.session.close()


class UploadForm(FlaskForm):
    """Builds an upload form with wtf-forms."""

    file = FileField('My BEL script', validators=[
        DataRequired(),
        FileAllowed(['bel'], 'Only files with the *.bel extension are allowed')
    ])

    submit = SubmitField('Upload')

    def _get_report(self) -> Report:
        """Get an initial report for the data in this form."""
        source_bytes = self.file.data.stream.read()
        source_sha512 = hashlib.sha512(source_bytes).hexdigest()
        return Report(
            source_name=self.file.data.filename,
            source=source_bytes,
            source_hash=source_sha512,
            encoding='utf-8',
            public=True,
            allow_nested=True,
            citation_clearing=True,
            infer_origin=True,
        )

    def send_parse_task(self):
        """Send the form's file to get parsed."""
        report = self._get_report()
        manager.session.add(report)

        try:
            manager.session.commit()
        except Exception:
            manager.session.rollback()
            flash('Unable to upload BEL document')
        else:
            report_id, report_name = report.id, report.source_name
            logger.debug(f'Got report {report_id}: {report_name}')

            manager.session.close()

            time.sleep(2)  # half hearted attempt to not get a race condition

            task = parse.apply_async(args=[report_id])

            logger.info(f'Parse task={task.id} for report={report_id}')
            flash(f'Queued parsing task {report_id} for {report_name}.')


def get_running_tasks():
    """Get running tasks in Celery."""
    i = celery_app.control.inspect()
    # TODO


ui = Blueprint('ui', __name__)


@ui.route('/', methods=['GET', 'POST'])
def view_home():
    """Render the home page."""
    form = UploadForm()

    if form.validate_on_submit():  # No upload data to send.
        form.send_parse_task()

    return render_template(
        'index.html',
        form=form,
        networks=manager.list_networks(),
        pybel_version=pybel.get_version(),
        pybel_tools_version=pybel_tools.get_version(),
        bel_commons_version=bel_commons.get_version(),
    )


@ui.route('/network/<int:network_id>', methods=['GET'])
def view_network(network_id: int):
    """Render a network page."""
    network = manager.get_network_by_id(network_id)
    graph = network.as_bel()
    report: Report = network.report
    context = report.get_calculations()

    return render_template(
        'network.html',
        graph=graph,
        network=network,
        context=context,
        chart_1_data=context.prepare_c3_for_function_count(),
        chart_2_data=context.prepare_c3_for_relation_count(),
        chart_3_data=context.prepare_c3_for_error_count(),
        chart_4_data=context.prepare_c3_for_transformations(),
        number_transformations=sum(context.modifications_count.values()),
        chart_5_data=context.prepare_c3_for_variants(),
        number_variants=sum(context.variants_count.values()),
        chart_6_data=context.prepare_c3_for_namespace_count(),
        number_namespaces=len(context.namespaces_count),
        chart_7_data=context.prepare_c3_for_hub_data(),
        chart_9_data=context.prepare_c3_for_pathology_count(),
        chart_10_data=context.prepare_c3_for_citation_years(),
    )


@ui.route('/network/<int:network_id>.jgif', methods=['GET'])
def download(network_id: int):
    """Render a network page."""
    data = to_jgif(manager.get_graph_by_id(network_id))
    return jsonify(data)


@ui.route('/network/<int:network_id>/upload', methods=['GET'])
def upload(network_id: int):
    """Upload the JGIF for the graph."""
    payload = to_jgif(manager.get_graph_by_id(network_id))

    external_upload_url = flask_app.config.get(UPLOAD_URL)
    if external_upload_url is not None:
        response = requests.post(external_upload_url, json=payload)
    else:
        logger.info('Debugging receive endpoint')
        response = requests.post('http://localhost:5000/receive', json=payload)

    flash(f'Response: {response}/{response.json()}')
    return redirect(url_for('.view_home'))


if UPLOAD_URL not in flask_app.config:
    @ui.route('/receive', methods=['POST'])
    def receive():
        """Mock the receiver endpoint for JGIF."""
        payload = request.get_json()
        if payload is None:
            return abort(500, 'No data received.')

        metadata = payload.get('metadata')
        if metadata is None:
            return abort(500, 'Invalid payload, missing "metadata" key')

        logger.info(f'Received network {metadata}.\nNot doing anything.')
        return jsonify(metadata)

flask_app.register_blueprint(ui)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.setLevel(logging.INFO)
    flask_app.run(debug=True)
