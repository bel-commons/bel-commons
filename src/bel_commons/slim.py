# -*- coding: utf-8 -*-

"""BEL Commons Slim.

Run with ``python -m bel_commons.slim``
"""

from __future__ import annotations

import hashlib
import logging
import time

import requests.exceptions
from celery import Celery
from celery.app.task import Task
from celery.utils.log import get_task_logger
from flask import Flask, flash, render_template
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
from bel_resources.exc import ResourceError
from pybel.constants import get_cache_connection
from pybel.parser.exc import InconsistentDefinitionError

logger = logging.getLogger(__name__)
celery_logger = get_task_logger(__name__)

bel_commons_config = BELCommonsConfig.load()

app = Flask(__name__)
app.config.update(bel_commons_config.to_dict())

# Set SQLAlchemy defaults
app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)
app.config.setdefault(SQLALCHEMY_DATABASE_URI, get_cache_connection())
logger.info(f'database: {app.config.get(SQLALCHEMY_DATABASE_URI)}')

##########
# CELERY #
##########

backend = app.config.get(CELERY_RESULT_BACKEND)
if backend is None:
    backend = f'db+{app.config[SQLALCHEMY_DATABASE_URI]}'

celery = Celery(
    app.import_name,
    broker=app.config[CELERY_BROKER_URL],
    backend=backend,
)

celery.conf.update(app.config)

bootstrap.init_app(app)

db = PyBELSQLAlchemy(app)
manager = db.manager


@celery.task(bind=True)  # noqa: C901
def upload_bel(task: Task, report_id: int):
    """Parse a BEL script asynchronously and send email feedback."""
    if not task.request.called_directly:
        task.update_state(state='STARTED')

    t = time.time()
    report = manager.get_report_by_id(report_id)

    report_id = report.id
    source_name = report.source_name

    celery_logger.info(f'Starting parse task for {source_name} (report {report_id})')

    def finish_parsing(body: str) -> str:
        report.message = body
        manager.session.commit()
        return body

    celery_logger.info('parsing graph')

    try:
        graph = parse_graph(report=report, manager=manager, task=task)
    except (ResourceError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        return finish_parsing(
            f'Parsing Failed for {source_name}. Connection to resource could not be established: {e}',
        )
    except InconsistentDefinitionError as e:
        return finish_parsing(
            f'Parsing Failed for {source_name} because {e.definition} was redefined on line {e.line_number}',
        )
    except Exception as e:
        return finish_parsing(
            f'Parsing Failed for {source_name} from a general error: {e}',
        )

    if not graph.name:
        return finish_parsing(f'Parsing Failed for {source_name} because SET DOCUMENT Name was missing.')
    if not graph.version:
        return finish_parsing(f'Parsing Failed for {source_name} because SET DOCUMENT Version was missing.')

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
    except Exception:
        manager.session.rollback()
        celery_logger.exception('Problem filling out report')
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

    def get_report(self) -> Report:
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


@app.route('/')
def view_home():
    """Render the home page."""
    form = UploadForm()

    if not form.validate_on_submit():  # No upload data to send.
        return render_template(
            'slim/index.html',
            form=form,
            networks=manager.list_networks(),
            pybel_version=pybel.get_version(),
            pybel_tools_version=pybel_tools.get_version(),
            bel_commons_version=bel_commons.get_version(),
        )

    report = form.get_report()
    manager.session.add(report)

    try:
        manager.session.commit()
    except Exception:
        manager.session.rollback()
        flash('Unable to upload BEL document')
    else:
        report_id, report_name = report.id, report.source_name
        manager.session.close()

        time.sleep(2)  # half hearted attempt to not get a race condition

        connection = app.config[SQLALCHEMY_DATABASE_URI]
        task = celery.send_task('upload-bel', args=[connection, report_id])
        logger.info(f'Parse task={task.id} for report={report_id}')
        flash(f'Queued parsing task {report_id} for {report_name}.')

    return render_template(
        'slim/index.html',
        networks=manager.list_networks(),
        pybel_version=pybel.get_version(),
        pybel_tools_version=pybel_tools.get_version(),
        bel_commons_version=bel_commons.get_version(),
    )


@app.route('/network/<int:network_id>')
def view_network(network_id: int):
    """Render a network page."""
    network = manager.get_network_by_id(network_id)
    report: Report = network.report
    context = report.get_calculations()

    return render_template(
        'slim/network.html',
        network=network,
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


if __name__ == '__main__':
    app.run(debug=True)
