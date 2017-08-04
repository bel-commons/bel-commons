# -*- coding: utf-8 -*-

import codecs
import logging
import pickle
import time
from operator import itemgetter

import flask
import pandas
from flask import current_app, redirect, url_for, render_template, Blueprint, abort
from flask_login import login_required, current_user

from pybel.constants import GENE, PYBEL_CONNECTION
from pybel.manager.models import Network
from pybel_tools.analysis.cmpa import RESULT_LABELS
from pybel_tools.analysis.cmpa import calculate_average_scores_on_subgraphs as calculate_average_cmpa_on_subgraphs
from pybel_tools.filters import remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from .celery_utils import create_celery
from .forms import DifferentialGeneExpressionForm
from .models import Experiment, Query
from .utils import manager, safe_get_query, get_network_ids_with_permission_helper, api

log = logging.getLogger(__name__)

analysis_blueprint = Blueprint('analysis', __name__)

LABEL = 'dgxp'


@analysis_blueprint.route('/analysis/')
@analysis_blueprint.route('/network/<int:query_id>/analysis/')
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


@analysis_blueprint.route('/network/<int:network_id>/analysis/async-upload', methods=('GET', 'POST'))
@login_required
def view_async_analysis_uploader(network_id):
    """Renders the asynchronous analysis page"""
    form = DifferentialGeneExpressionForm()

    if not form.validate_on_submit():
        name, = manager.session.query(Network.name).filter(Network.id == network_id).one()
        return render_template('analyze_dgx.html', form=form, network_name=name)

    log.info(
        'analyzing %s: %s with CMPA (%d trials)',
        form.file.data.filename,
        form.description.data,
        form.permutations.data,
    )

    celery = create_celery(current_app)

    lines = codecs.iterdecode(form.file.data.stream, 'utf-8')
    lines = list(lines)

    task = celery.send_task('run-cmpa', args=(
        current_app.config.get(PYBEL_CONNECTION),
        network_id,
        lines,
        form.file.data.filename,
        form.description.data,
        form.gene_symbol_column.data,
        form.log_fold_change_column.data,
        form.permutations.data,
        form.separator.data,
    ))
    flask.flash('Queued CMPA analysis: {}'.format(task))

    return redirect(url_for('analysis.view_analyses'))


def calculate_scores(graph, data, runs):
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_cmpa_on_subgraphs(candidate_mechanisms, LABEL, runs=runs)

    return scores


def make_experiment(graph, form):
    t = time.time()

    df = pandas.read_csv(form.file.data)

    gene_column = form.gene_symbol_column.data
    data_column = form.log_fold_change_column.data

    if gene_column not in df.columns:
        raise ValueError('{} not a column in document'.format(gene_column))

    if data_column not in df.columns:
        raise ValueError('{} not a column in document'.format(data_column))

    data = {
        k: v
        for _, k, v in df.loc[df[gene_column].notnull(), [gene_column, data_column]].itertuples()
    }

    runs = form.permutations.data
    scores = calculate_scores(graph, data, runs)

    log.info('done running CMPA in %.2fs', time.time() - t)

    experiment = Experiment(
        description=form.description.data,
        source_name=form.file.data.filename,
        source=pickle.dumps(df),
        result=pickle.dumps(scores),
        permutations=form.permutations.data,
        user=current_user,
    )

    return experiment


@analysis_blueprint.route('/network/<int:network_id>/analysis/upload/', methods=('GET', 'POST'))
@login_required
def view_analysis_uploader(network_id):
    """Views the results of analysis on a given graph"""
    if network_id not in get_network_ids_with_permission_helper(current_user, api):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    query = Query.from_query_args(manager, current_user, network_id)
    manager.session.add(query)
    manager.session.commit()

    return redirect(url_for('analysis.view_query_analysis_uploader', query_id=query.id))


@analysis_blueprint.route('/query/<int:query_id>/analysis/upload', methods=('GET', 'POST'))
@login_required
def view_query_analysis_uploader(query_id):
    """Views the results of analysis on a given graph"""
    query = safe_get_query(query_id)
    graph = query.run(manager)

    form = DifferentialGeneExpressionForm()

    if not form.validate_on_submit():
        return render_template('analyze_dgx.html', form=form, network_name='Query {}'.format(query_id))

    log.info(
        'analyzing %s: %s with CMPA (%d trials)',
        form.file.data.filename,
        form.description.data,
        form.permutations.data,
    )

    experiment = make_experiment(graph, form)
    experiment.query = query

    manager.session.add(experiment)
    manager.session.commit()

    return redirect(url_for('analysis.view_analyses'))
