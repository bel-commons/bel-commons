# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import codecs
import logging

from flask import render_template, current_app, Blueprint, flash
from flask_security import current_user, login_required

from pybel.constants import PYBEL_CONNECTION
from .celery_utils import create_celery
from .constants import reporting_log
from .forms import ParserForm, ParseUrlForm

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

    lines = codecs.iterdecode(form.file.data.stream, form.encoding.data)
    lines = list(lines)

    celery = create_celery(current_app)
    task = celery.send_task('pybelparser', args=(
        lines,
        current_app.config.get(PYBEL_CONNECTION),
        current_user.id,
        current_user.email,
        form.public.data,
    ))

    reporting_log.info('Parse task from %s: %s', current_user, task.id)
    flash('Queued parsing task {}.'.format(task))

    return render_template('parser_status.html', task=task)


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
    task = celery.send_task('parse-url', args=[current_app.config.get(PYBEL_CONNECTION), form.url.data])
    flash('Queued parsing task {}.'.format(task))

    return render_template('parser_status.html', task=task)
