# -*- coding: utf-8 -*-

"""This module helps make summary pages."""

import datetime
import logging
from collections import Counter, OrderedDict

from flask import Blueprint, render_template, request
from flask_security import roles_required

from ..core.models import Query
from ..core.proxies import manager
from ..models import EdgeComment, EdgeVote, Experiment, Report

__all__ = [
    'reporting_blueprint',
]

log = logging.getLogger(__name__)

reporting_blueprint = Blueprint('reporting', __name__, url_prefix='/reporting')


def _get_timeseries_from_models(models, y_axis_name, x_axis_name='x'):
    date_counter = Counter(created.strftime('%Y-%m-%d') for created, in models)

    if not date_counter:
        return

    x_list, y_list = zip(*date_counter.most_common())

    return [
        [x_axis_name] + list(x_list),
        [y_axis_name] + list(y_list),
    ]


def _get_timeseries(model, name, interval=None):
    models = manager.session.query(model.created)
    if interval is not None:
        models = models.filter(model.created > interval)
    return _get_timeseries_from_models(models, name)


def _get_vote_timeseries(name, interval=None):
    models = manager.session.query(EdgeVote.changed)
    if interval is not None:
        models = models.filter(EdgeVote.changed > interval)
    return _get_timeseries_from_models(models, name)


@reporting_blueprint.route('/')
@roles_required('admin')
def view_report():
    """This view gives an overview of the user actions in the last 7 days"""
    interval = request.args.get('days', type=int)
    if interval is not None:
        interval = datetime.datetime.now() - datetime.timedelta(days=interval)

    network_data = _get_timeseries(Report, 'Network Uploads', interval)
    query_data = _get_timeseries(Query, 'Queries', interval)
    experiment_data = _get_timeseries(Experiment, 'Experiments', interval)
    vote_data = _get_vote_timeseries('Votes', interval)
    comment_data = _get_timeseries(EdgeComment, 'Comments', interval)

    charts = OrderedDict([
        ('network-chart', network_data),
        ('query-chart', query_data),
        ('experiment-chart', experiment_data),
        ('vote-chart', vote_data),
        ('comment-chart', comment_data),
    ])

    return render_template(
        'reporting/report.html',
        charts=charts
    )


@reporting_blueprint.route('/network', methods=['GET'])
@roles_required('admin')
def view_networks():
    """Shows the uploading reporting"""
    return render_template('reporting/networks.html',
                           reports=manager.session.query(Report).order_by(Report.created.desc()).all())
