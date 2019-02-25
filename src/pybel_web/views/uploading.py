# -*- coding: utf-8 -*-

"""A blueprint for uploading BEL documents."""

import hashlib
import logging
import time

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_security import current_user, login_required, roles_required

from pybel_web.forms import ParserForm
from pybel_web.models import Report
from pybel_web.proxies import celery, manager

__all__ = [
    'uploading_blueprint',
]

log = logging.getLogger(__name__)

uploading_blueprint = Blueprint('parser', __name__)


@uploading_blueprint.route('/run-debug-celery')
@roles_required('admin')
def run_debug():
    """Run the debug task."""
    task = celery.send_task('debug-task')
    log.info('Parse task from %s', task.id)
    flash('Queued Celery debug task: {}.'.format(task.id))
    return redirect(url_for('.view_parser'))


@uploading_blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def view_parser():
    """Render the form for asynchronous parsing."""
    form = ParserForm(
        public=(not current_user.email.contains('@scai.fraunhofer.de')),
    )

    if not form.validate_on_submit():
        return render_template('parser.html', form=form, current_user=current_user)

    source_bytes = form.file.data.stream.read()
    source_sha512 = hashlib.sha512(source_bytes).hexdigest()

    # check if another one has the same hash + settings

    report = Report(
        user=current_user,
        source_name=form.file.data.filename,
        source=source_bytes,
        source_hash=source_sha512,
        encoding=form.encoding.data,
        public=form.public.data,
        allow_nested=form.allow_nested.data,
        citation_clearing=(not form.disable_citation_clearing.data),
        infer_origin=form.infer_origin.data,
    )

    manager.session.add(report)

    try:
        manager.session.commit()
    except Exception:
        manager.session.rollback()
        flash('Unable to upload BEL document')
        return redirect(url_for('.view_parser'))

    report_id, report_name = report.id, report.source_name
    current_user_str = str(current_user)
    manager.session.close()

    time.sleep(2)  # half hearted attempt to not get a race condition

    connection = current_app.config['SQLALCHEMY_DATABASE_URI']
    if form.feedback.data:
        task = celery.send_task('summarize-bel', args=[connection, report_id])
        log.info('Email summary task from %s: report=%s/task=%s', current_user_str, report_id, task.id)
        flash('Queued email summary task {} for {}.'.format(report_id, report_name))
    else:
        task = celery.send_task('upload-bel', args=[connection, report_id])
        log.info('Parse task from %s: report=%s/task=%s', current_user_str, report_id, task.id)
        flash('Queued parsing task {} for {}.'.format(report_id, report_name))

    return redirect(url_for('ui.view_current_user_activity'))
