# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import logging

from flask import render_template, current_app, Blueprint, flash, redirect, url_for
from flask_security import current_user, login_required

from pybel.constants import PYBEL_CONNECTION
from .celery_utils import create_celery
from .constants import reporting_log
from .forms import ParserForm, ParseUrlForm
from .models import Report
from .utils import manager

log = logging.getLogger(__name__)

parser_async_blueprint = Blueprint('parser', __name__)


@parser_async_blueprint.route('/parser', methods=['GET', 'POST'])
@login_required
def view_parser():
    """Renders the form for asynchronous parsing"""
    form = ParserForm(
        public=(not current_user.has_role('scai')),
    )

    if not form.validate_on_submit():
        return render_template('parser.html', form=form, current_user=current_user)

    report = Report(
        user=current_user,
        source_name=form.file.data.filename,
        source=form.file.data.stream.read(),
        encoding=form.encoding.data,
        public=form.public.data,
        allow_nested=form.allow_nested.data,
        citation_clearing=form.citation_clearing.data,
    )

    manager.session.add(report)
    manager.session.commit()

    celery = create_celery(current_app)
    task = celery.send_task('pybelparser', args=(
        current_app.config.get(PYBEL_CONNECTION),
        report.id
    ))

    reporting_log.info('Parse task from %s: %s', current_user, task.id)
    flash('Queued parsing task {} for {}.'.format(report.id, report.source_name))

    return redirect(url_for('view_current_user_activity'))


@parser_async_blueprint.route('/parse_url', methods=('GET', 'POST'))
def view_url_parser():
    """Renders a form for parsing by URL"""
    form = ParseUrlForm()

    if not form.validate_on_submit():
        return render_template(
            'generic_form.html',
            form=form,
            current_user=current_user,
            page_title='Upload by URL',
            page_header='Upload by URL',
        )

    celery = create_celery(current_app)
    task = celery.send_task('parse-url', args=[
        current_app.config.get(PYBEL_CONNECTION),
        form.url.data
    ])

    reporting_log.info('Parse URL task from %s: %s', current_user, task.id)
    flash('Queued parsing task {} for {}.'.format(task.id, form.url.data))

    return redirect(url_for('view_current_user_activity'))
