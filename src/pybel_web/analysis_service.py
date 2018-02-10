# -*- coding: utf-8 -*-

import csv
import json
import logging
import pickle
import time
from collections import defaultdict
from io import StringIO
from operator import itemgetter

import flask
import pandas as pd
from flask import Blueprint, abort, current_app, make_response, redirect, render_template, url_for
from flask_security import current_user, login_required

from pybel_tools.analysis.cmpa import RESULT_LABELS
from .forms import DifferentialGeneExpressionForm
from .models import Experiment, Omics, Query
from .utils import get_network_ids_with_permission_helper, manager, safe_get_query

log = logging.getLogger(__name__)

analysis_blueprint = Blueprint('analysis', __name__)


@analysis_blueprint.route('/analysis/')
@analysis_blueprint.route('/query/<int:query_id>/analysis/')
@login_required
def view_analyses(query_id=None):
    """Views a list of all analyses, with optional filter by network id"""
    experiment_query = manager.session.query(Experiment)

    if query_id is not None:
        experiment_query = experiment_query.filter(Experiment.query_id == query_id)

    return render_template(
        'analysis_list.html',
        experiments=experiment_query.all(),
        current_user=current_user
    )


def safe_get_experiment(manager_, experiment_id):
    """Safely gets an experiment

    :param pybel.manager.Manager manager_:
    :param int experiment_id:
    :rtype: Experiment
    :raises: werkzeug.exceptions.HTTPException
    """
    experiment = manager_.session.query(Experiment).get(experiment_id)

    if experiment is None:
        abort(404, 'Experiment {} does not exist'.format(experiment_id))

    if not current_user.is_admin and (current_user != experiment.user):
        abort(403, 'You do not have rights to drop this experiment')

    return experiment


@analysis_blueprint.route('/analysis/<int:experiment_id>/results/')
@login_required
def view_analysis_results(experiment_id):
    """View the results of a given analysis

    :param int experiment_id: The identifier of the experiment whose results to view
    """
    experiment = safe_get_experiment(manager, experiment_id)

    data = experiment.get_data_list()

    return render_template(
        'analysis_results.html',
        experiment=experiment,
        columns=RESULT_LABELS,
        data=sorted(data, key=itemgetter(1)),
        d3_data=json.dumps([v[3] for _, v in data]),
        current_user=current_user,
    )


@analysis_blueprint.route('/query/<int:query_id>/analysis/upload', methods=('GET', 'POST'))
@login_required
def view_query_analysis_uploader(query_id):
    """Renders the asynchronous analysis page

    :param int query_id: The identifier of the query to upload against
    """
    query = safe_get_query(query_id)

    form = DifferentialGeneExpressionForm()

    if not form.validate_on_submit():
        return render_template('analyze_dgx.html', form=form, query=query)

    t = time.time()

    log.info(
        'analyzing %s with CMPA (%d trials)',
        form.file.data.filename,
        form.permutations.data,
    )

    df = pd.read_csv(form.file.data)

    gene_column = form.gene_symbol_column.data
    data_column = form.log_fold_change_column.data

    if gene_column not in df.columns:
        raise ValueError('{} not a column in document'.format(gene_column))

    if data_column not in df.columns:
        raise ValueError('{} not a column in document'.format(data_column))

    omics = Omics(
        description=form.description.data,
        source_name=form.file.data.filename,
        source=pickle.dumps(df),
        gene_column=gene_column,
        data_column=data_column,
        user=current_user,
    )

    experiment = Experiment(
        user=current_user,
        query=query,
        permutations=form.permutations.data,
        omics=omics
    )

    manager.session.add(experiment)
    manager.session.commit()

    log.debug('stored data for analysis in %.2f seconds', time.time() - t)

    task = current_app.celery.send_task('run-cmpa', args=[
        current_app.config['SQLALCHEMY_DATABASE_URI'],
        experiment.id
    ])

    flask.flash('Queued Experiment {} with task {}'.format(experiment.id, task))
    return redirect(url_for('ui.home'))


@analysis_blueprint.route('/network/<int:network_id>/analysis/upload/', methods=('GET', 'POST'))
@login_required
def view_network_analysis_uploader(network_id):
    """Views the results of analysis on a given graph

    :param int network_id: The identifier ot the network to query against
    """
    if network_id not in get_network_ids_with_permission_helper(current_user, manager):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    query = Query.from_query_args(manager, [network_id], current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect(url_for('.view_query_analysis_uploader', query_id=query.id))


def help_compare(experiments):
    """Help build the analysis comparison page

    :param iter[Experiment] experiments:
    :return: flask.Response
    """
    x_label = []
    xd = {}
    entries = defaultdict(list)

    for experiment in experiments:
        if experiment.result is None:
            continue
        x_label.append(experiment.description)
        xd[experiment.id] = experiment.description
        for entry, values in sorted(experiment.get_data_list()):
            entries[entry].append(values[3])

    chart_data = [
        [entry] + values
        for entry, values in entries.items()
    ]

    return render_template(
        'analysis_compare.html',
        x_label=x_label,
        xd=xd,
        chart_data=chart_data
    )


@analysis_blueprint.route('/analysis/comparison/<list:experiment_ids>')
@login_required
def view_results_comparison(experiment_ids):
    """Different data analyses on same query

    :param list[int] experiment_ids: The identifiers of experiments to compare
    """
    experiments = [safe_get_experiment(manager, experiment_id) for experiment_id in experiment_ids]
    return help_compare(experiments)


@analysis_blueprint.route('/analysis/comparison/query/<int:query_id>')
@login_required
def view_results_comparison_by_query(query_id):
    """Different data analyses on same query

    :param int query_id: The query identifier whose related experiments to compare
    """
    query = safe_get_query(query_id)
    return help_compare(query.experiments)


def help_make_experiment_comparison_response(experiments, attachment_name=None):
    x_label = []
    entries = defaultdict(list)

    for experiment in experiments:
        if not experiment.result:
            continue

        x_label.append('[{}] {}'.format(experiment.id, experiment.description))

        for entry, values in sorted(experiment.get_data_list()):
            entries[entry].append(values[3])

    chart_data = [['Type', 'Namespace', 'Name'] + x_label] + [
        list(entry) + values
        for entry, values in entries.items()
    ]

    si = StringIO()
    cw = csv.writer(si)
    cw.writerows(chart_data)
    output = make_response(si.getvalue())

    if attachment_name:
        output.headers["Content-Disposition"] = "attachment; filename={}".format(attachment_name)

    output.headers["Content-type"] = "text/csv"
    return output


@analysis_blueprint.route('/analysis/comparison/<list:experiment_ids>.csv')
@login_required
def view_results_comparison_csv(experiment_ids):
    """Different data analyses on same query"""
    experiments = [safe_get_experiment(manager, experiment_id) for experiment_id in experiment_ids]
    return help_make_experiment_comparison_response(experiments)


@analysis_blueprint.route('/query/<int:query_id>/analyses.csv')
@login_required
def view_results_comparison_query_csv(query_id):
    """Returns all data analyses on same query as a CSV"""
    query = safe_get_query(query_id)

    return help_make_experiment_comparison_response(
        query.experiments,
        attachment_name='{}_analyses.csv'.format(query_id)
    )
