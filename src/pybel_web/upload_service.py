# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import logging

from flask import (
    flash,
    redirect,
    url_for,
    render_template,
    Blueprint,
    request,
)
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError, OperationalError

from pybel import from_bytes
from pybel.io.io_exceptions import ImportVersionWarning
from pybel.manager.models import Network
from .constants import integrity_message
from .forms import UploadForm
from .utils import add_network_reporting, manager

log = logging.getLogger(__name__)

upload_blueprint = Blueprint('upload', __name__)


@upload_blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def view_upload():
    """An upload form for a BEL script"""
    form = UploadForm()

    if not form.validate_on_submit():
        return render_template('upload.html', form=form, current_user=current_user)

    log.warning('Request: %s, %s', request.data, request.files)

    log.info('uploading %s', form.file.data.filename)

    try:
        graph_bytes = form.file.data.read()
        graph = from_bytes(graph_bytes)
    except (ImportVersionWarning, ImportError) as e:
        flash(str(e), category='error')
        return redirect(url_for('upload.view_upload'))
    except Exception as e:
        message = 'The given file was not able to be unpickled [{}]'.format(str(e))
        log.exception('unpickle error')
        flash(message, category='error')
        return redirect(url_for('upload.view_upload'))

    network = manager.session.query(Network).filter(Network.name == graph.name,
                                                    Network.version == graph.version).one_or_none()

    if network:
        flash('This network has already been uploaded. If you have made changes, consider bumping the version',
              category='warning')
        return redirect(url_for('view_summary', network_id=network.id))

    try:
        network = manager.insert_graph(graph)
    except IntegrityError:
        flash(integrity_message.format(graph.name, graph.version), category='error')
        manager.session.rollback()
        return redirect(url_for('upload.view_upload'))
    except (OperationalError, Exception) as e:
        log.exception('upload error')
        flash("Error storing in database [{}]".format(e), category='error')
        manager.session.rollback()
        return redirect(url_for('upload.view_upload'))

    log.info('done uploading %s [%d]', form.file.data.filename, network.id)

    try:
        add_network_reporting(
            manager,
            network,
            current_user,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            len(graph.warnings),
            preparsed=True,
            public=form.public.data
        )
    except IntegrityError:
        message = 'integrity error while adding reporting'
        flash(message, category='warning')
        manager.session.rollback()
    except (OperationalError, Exception) as e:
        log.exception('error uploading report')
        flash("Error storing report in database [{}]".format(e), category='error')
        manager.session.rollback()

    return redirect(url_for('view_summary', network_id=network.id))
