# -*- coding: utf-8 -*-

import logging
import pickle
import time
from operator import itemgetter

import flask
import pandas
from flask import current_app, redirect, url_for, render_template, Blueprint, abort
from flask_login import login_required, current_user

from pybel.constants import PYBEL_CONNECTION
from pybel_tools.analysis.cmpa import RESULT_LABELS
from .celery_utils import create_celery
from .forms import DifferentialGeneExpressionForm
from .models import Experiment, Query
from .utils import manager, safe_get_query, get_network_ids_with_permission_helper, api, next_or_jsonify

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


@analysis_blueprint.route('/analysis/<int:analysis_id>/results/')
@login_required
def view_analysis_results(analysis_id):
    """View the results of a given analysis"""
    experiment = manager.session.query(Experiment).get(analysis_id)

    # TODO check if user has rights to this experiment

    experiment_data = pickle.loads(experiment.result)

    data = [
        (k, v)
        for k, v in experiment_data.items()
        if v[0]
    ]

    return render_template(
        'analysis_results.html',
        experiment=experiment,
        columns=RESULT_LABELS,
        data=sorted(data, key=itemgetter(1)),
        current_user=current_user,
    )


@analysis_blueprint.route('/query/<query_id>/analysis/upload', methods=('GET', 'POST'))
@login_required
def view_query_analysis_uploader(query_id):
    """Renders the asynchronous analysis page"""
    query = safe_get_query(query_id)

    form = DifferentialGeneExpressionForm()

    if not form.validate_on_submit():
        return render_template('analyze_dgx.html', form=form, network_name='Query {}'.format(query_id))

    t = time.time()

    log.info(
        'analyzing %s with CMPA (%d trials)',
        form.file.data.filename,
        form.permutations.data,
    )

    df = pandas.read_csv(form.file.data)

    gene_column = form.gene_symbol_column.data
    data_column = form.log_fold_change_column.data

    if gene_column not in df.columns:
        raise ValueError('{} not a column in document'.format(gene_column))

    if data_column not in df.columns:
        raise ValueError('{} not a column in document'.format(data_column))

    experiment = Experiment(
        description=form.description.data,
        source_name=form.file.data.filename,
        source=pickle.dumps(df),
        gene_column=gene_column,
        data_column=data_column,
        permutations=form.permutations.data,
        user=current_user,
        query=query,
    )

    manager.session.add(experiment)
    manager.session.commit()

    log.info('stored data for analysis in %.2f seconds', time.time() - t)

    celery = create_celery(current_app)

    log.info('created celery')

    task = celery.send_task('run-cmpa', args=(
        current_app.config.get(PYBEL_CONNECTION),
        experiment.id,
    ))

    log.info('sent task %s', task)

    flask.flash('Queued Experiment {} with task {}'.format(experiment.id, task))
    return redirect(url_for('home'))


@analysis_blueprint.route('/network/<int:network_id>/analysis/upload/', methods=('GET', 'POST'))
@login_required
def view_network_analysis_uploader(network_id):
    """Views the results of analysis on a given graph"""
    if network_id not in get_network_ids_with_permission_helper(current_user, api):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    query = Query.from_query_args(manager, current_user, network_id)
    manager.session.add(query)
    manager.session.commit()

    return redirect(url_for('.view_query_analysis_uploader', query_id=query.id))
