# -*- coding: utf-8 -*-

"""A blueprint for uploading BEL documents."""

import logging

from flask import flash, redirect, render_template, url_for
from flask_security import current_user, login_required, roles_required

from bel_commons.celery_worker import run_debug_task
from ..forms import ParserForm
from ..utils import SecurityConfigurableBlueprint as Blueprint

__all__ = [
    'uploading_blueprint',
]

logger = logging.getLogger(__name__)

# Even though we use the SecurityConfigurableBlueprint, all of the endpoints here are locked down anyway
uploading_blueprint = Blueprint('parser', __name__)


@uploading_blueprint.route('/run-debug-celery')
@roles_required('admin')
def run_debug():
    """Run the debug task."""
    task = run_debug_task.delay()
    logger.info('Parse task from %s', task.id)
    flash(f'Queued Celery debug task: {task.id}.')
    return redirect(url_for('.view_parser'))


@uploading_blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def view_parser():
    """Render the form for asynchronous parsing."""
    form = ParserForm()

    if not form.validate_on_submit():
        return render_template('parser.html', form=form, current_user=current_user)

    form.send_parse_task()

    return redirect(url_for('ui.view_current_user_activity'))
