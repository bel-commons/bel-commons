# -*- coding: utf-8 -*-

import codecs
import logging
import pickle
import time
from operator import itemgetter

import flask
import pandas
from flask import current_app, redirect, url_for, render_template, Blueprint
from flask_login import login_required, current_user
from werkzeug.local import LocalProxy

from pybel.constants import GENE, PYBEL_CONNECTION
from pybel.manager.models import Network
from pybel_tools.analysis import npa
from pybel_tools.filters import remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from .application import create_celery
from .forms import DifferentialGeneExpressionForm
from .models import Experiment
from .utils import get_current_manager, get_current_api

log = logging.getLogger(__name__)

analysis_blueprint = Blueprint('analysis', __name__)
manager = LocalProxy(get_current_manager)
api = LocalProxy(get_current_api)

LABEL = 'dgxp'


@analysis_blueprint.route('/analysis/')
@analysis_blueprint.route('/analysis/<network_id>')
def view_analyses(network_id=None):
    """Views a list of all analyses, with optional filter by network id"""
    experiment_query = manager.session.query(Experiment)

    if network_id is not None:
        experiment_query = experiment_query.filter(Experiment.network_id == network_id)

    experiments = experiment_query.all()
    return render_template('analysis_list.html', experiments=experiments, current_user=current_user)


@analysis_blueprint.route('/analysis/results/<int:analysis_id>')
def view_analysis_results(analysis_id):
    """View the results of a given analysis"""
    experiment = manager.session.query(Experiment).get(analysis_id)
    experiment_data = pickle.loads(experiment.result)

    data = [
        (k, v)
        for k, v in experiment_data.items()
        if v[0]
    ]

    return render_template(
        'analysis_results.html',
        experiment=experiment,
        columns=npa.RESULT_LABELS,
        data=sorted(data, key=itemgetter(1)),
        current_user=current_user
    )


@analysis_blueprint.route('/asyncanalysis/upload/<int:network_id>', methods=('GET', 'POST'))
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
        form.permutations.data
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


@analysis_blueprint.route('/analysis/upload/<int:network_id>', methods=('GET', 'POST'))
@login_required
def view_analysis_uploader(network_id):
    """Views the results of analysis on a given graph"""
    form = DifferentialGeneExpressionForm()

    if not form.validate_on_submit():
        name, = manager.session.query(Network.name).filter(Network.id == network_id).one()
        return render_template('analyze_dgx.html', form=form, network_name=name)

    log.info(
        'analyzing %s: %s with CMPA (%d trials)',
        form.file.data.filename,
        form.description.data,
        form.permutations.data
    )

    t = time.time()

    df = pandas.read_csv(form.file.data)

    gene_column = form.gene_symbol_column.data
    data_column = form.log_fold_change_column.data

    if gene_column not in df.columns:
        raise ValueError('{} not a column in document'.format(gene_column))

    if data_column not in df.columns:
        raise ValueError('{} not a column in document'.format(data_column))

    df = df.loc[df[gene_column].notnull(), [gene_column, data_column]]

    data = {k: v for _, k, v in df.itertuples()}

    network = manager.get_network_by_id(network_id)
    graph = network.as_bel()

    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = npa.calculate_average_npa_on_subgraphs(candidate_mechanisms, LABEL, runs=form.permutations.data)

    log.info('done running CMPA in %.2fs', time.time() - t)

    experiment = Experiment(
        description=form.description.data,
        source_name=form.file.data.filename,
        source=pickle.dumps(df),
        result=pickle.dumps(scores),
        permutations=form.permutations.data,
        user=current_user,
    )
    experiment.network = network

    manager.session.add(experiment)
    manager.session.commit()

    return redirect(url_for('analysis.view_analyses'))
