# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import codecs
import logging
import time

import requests
from flask import (
    redirect,
    url_for,
    current_app,
    render_template,
    Blueprint,
    flash
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from pybel import from_lines
from pybel.parser.parse_exceptions import InconsistentDefinitionError
from pybel_tools.mutation.metadata import add_canonical_names
from .constants import integrity_message
from .forms import ParserForm
from .utils import (
    log_graph,
    add_network_reporting,
    manager,
)

log = logging.getLogger(__name__)

parser_sync_blueprint = Blueprint('parser', __name__)


@parser_sync_blueprint.route('/parser', methods=['GET', 'POST'])
@login_required
def view_parser():
    """An upload form for a BEL script"""
    form = ParserForm()

    if not form.validate_on_submit():
        return render_template('parser.html', form=form, current_user=current_user)

    log.info('Running on %s', form.file.data.filename)

    t = time.time()

    # Decode the file with the given decoding (utf-8 is default)
    lines = codecs.iterdecode(form.file.data.stream, form.encoding.data)

    try:
        graph = from_lines(
            lines,
            manager=manager,
            allow_nested=form.allow_nested.data,
            citation_clearing=(not form.citation_clearing.data)
        )
        add_canonical_names(graph)
    except requests.exceptions.ConnectionError as e:
        message = "Resource doesn't exist."
        flash(message, category='error')
        return redirect(url_for('view_parser'))
    except InconsistentDefinitionError as e:
        log.error('%s was defined multiple times', e.definition)
        flash('{} was defined multiple times.'.format(e.definition), category='error')
        return redirect(url_for('view_parser'))
    except Exception as e:
        log.exception('parser error')
        flash('Compilation error: {}'.format(e))
        return redirect(url_for('view_parser'))

    try:
        network = manager.insert_graph(graph, store_parts=current_app.config.get('PYBEL_USE_EDGE_STORE', True))
    except IntegrityError:
        log_graph(graph, current_user, preparsed=False, failed=True)
        log.exception('integrity error')
        flash(integrity_message.format(graph.name, graph.version), category='error')
        manager.session.rollback()
        return redirect(url_for('view_parser'))
    except Exception as e:
        log_graph(graph, current_user, preparsed=False, failed=True)
        log.exception('general storage error')
        flash("Error storing in database: {}".format(e), category='error')
        return redirect(url_for('view_parser'))

    log.info('done storing %s [%d]', form.file.data.filename, network.id)

    try:
        add_network_reporting(
            manager,
            network,
            current_user,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            len(graph.warnings),
            preparsed=False,
            public=form.public.data
        )
    except IntegrityError:
        log.exception('integrity error')
        flash('problem with reporting service', category='warning')
        manager.session.rollback()
    except Exception as e:
        manager.session.rollback()
        raise e

    return redirect(url_for('view_summary', network_id=network.id))
