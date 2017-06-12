# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import codecs
import logging

from flask import render_template, current_app, Blueprint, flash
from flask_login import current_user, login_required

from pybel.constants import PYBEL_CONNECTION
from .application import create_celery
from .constants import reporting_log
from .forms import ParserForm

log = logging.getLogger(__name__)

parser_async_blueprint = Blueprint('parser', __name__)


@parser_async_blueprint.route('/parser', methods=['GET', 'POST'])
@login_required
def view_parser():
    """Renders the form for asynchronous parsing"""
    form = ParserForm(save_network=True)

    if not form.validate_on_submit():
        flash('Using asynchronous parser service. This service is currently in beta.', category='warning')
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
