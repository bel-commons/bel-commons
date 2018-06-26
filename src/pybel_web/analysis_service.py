# -*- coding: utf-8 -*-

import json
import logging
import time
from io import StringIO
from operator import itemgetter

import flask
import numpy as np
import pandas.errors
from flask import Blueprint, current_app, make_response, redirect, render_template, request, url_for
from flask_security import current_user, login_required, roles_required

from pybel_tools.analysis.heat import RESULT_LABELS
from .analysis_utils import get_dataframe_from_experiments
from .forms import DifferentialGeneExpressionForm
from .manager_utils import create_omic, next_or_jsonify
from .models import Experiment, Omic, Query
from .proxies import manager

log = logging.getLogger(__name__)

experiment_blueprint = Blueprint('analysis', __name__, url_prefix='/experiment')


@experiment_blueprint.route('/omic/')
def view_omics():
    """Views a list of all omics data sets"""
    query = manager.session.query(Omic)

    if not (current_user.is_authenticated and current_user.is_admin):
        query = query.filter(Omic.public)

    query = query.order_by(Omic.created.desc())

    return render_template('omic/omics.html', omics=query.all(), current_user=current_user)


@experiment_blueprint.route('/omic/<int:omic_id>')
def view_omic(omic_id):
    """Views an Omic model"""
    omic = manager.get_omic_by_id(omic_id)

    data = omic.get_source_dict()
    values = list(data.values())

    return render_template(
        'omic/omic.html',
        omic=omic,
        current_user=current_user,
        count=len(values),
        mean=np.mean(values),
        median=np.median(values),
        std=np.std(values),
        minimum=np.min(values),
        maximum=np.max(values)
    )


@experiment_blueprint.route('/omics/drop')
@roles_required('admin')
def drop_omics():
    """Drop all Omic models"""
    manager.session.query(Omic).delete()
    manager.session.commit()
    return next_or_jsonify('Dropped all Omic models')


@experiment_blueprint.route('/')
@experiment_blueprint.route('/from_query/<int:query_id>')
@experiment_blueprint.route('/from_omic/<int:omic_id>')
def view_experiments(query_id=None, omic_id=None):
    """Views a list of all analyses, with optional filter by network id"""
    experiment_query = manager.session.query(Experiment)

    if query_id is not None:
        experiment_query = experiment_query.filter(Experiment.query_id == query_id)

    if omic_id is not None:
        experiment_query = experiment_query.filter(Experiment.omic_id == omic_id)

    return render_template(
        'experiment/experiments.html',
        experiments=experiment_query.order_by(Experiment.created.desc()).all(),
        current_user=current_user
    )


@experiment_blueprint.route('/drop')
@roles_required('admin')
def drop_experiments():
    """Drops all Experiment models"""
    manager.session.query(Experiment).delete()
    manager.session.commit()
    return next_or_jsonify('Dropped all Experiment models')


@experiment_blueprint.route('/<int:experiment_id>')
def view_experiment(experiment_id):
    """View the results of a given analysis

    :param int experiment_id: The identifier of the experiment whose results to view
    """
    experiment = manager.safe_get_experiment(user=current_user, experiment_id=experiment_id)

    data = experiment.get_data_list()

    return render_template(
        'experiment/experiment.html',
        experiment=experiment,
        columns=RESULT_LABELS,
        data=sorted(data, key=itemgetter(1)),
        d3_data=json.dumps([v[3] for _, v in data]),
        current_user=current_user,
    )


@experiment_blueprint.route('/<int:experiment_id>/drop')
@roles_required('admin')
def drop_experiment(experiment_id):
    """Drops an Experiment model"""
    manager.session.query(Experiment).get(experiment_id).delete()
    manager.session.commit()
    return next_or_jsonify('Dropped Experiment {}'.format(experiment_id))


@experiment_blueprint.route('/from_query/<int:query_id>/upload', methods=('GET', 'POST'))
@login_required
def view_query_uploader(query_id):
    """Renders the asynchronous analysis page

    :param int query_id: The identifier of the query to upload against
    """
    query = manager.safe_get_query(user=current_user, query_id=query_id)

    form = DifferentialGeneExpressionForm()

    if not form.validate_on_submit():
        return render_template('experiment/analyze_dgx.html', form=form, query=query)

    t = time.time()

    log.info(
        'running heat diffusion workflow on %s with %d trials',
        form.file.data.filename,
        form.permutations.data,
    )

    try:
        omic = create_omic(
            data=form.file.data,
            gene_column=form.gene_symbol_column.data,
            data_column=form.log_fold_change_column.data,
            source_name=form.file.data.filename,
            description=form.description.data,
            sep=form.separator.data,
            public=form.omics_public.data,
            user=current_user
        )
    except pandas.errors.ParserError:
        flask.flash('Malformed differential gene expression file. Check it is formatted consistently.',
                    category='warning')
        log.exception('Malformed differential gene expression file.')
        return redirect(url_for('.view_query_uploader', query_id=query_id))

    experiment = Experiment(
        user=current_user,
        query=query,
        permutations=form.permutations.data,
        public=form.results_public.data,
        omic=omic,
    )

    manager.session.add(experiment)
    manager.session.commit()

    log.debug('stored data for analysis in %.2f seconds', time.time() - t)

    task = current_app.celery.send_task('run-heat-diffusion', args=[
        current_app.config['SQLALCHEMY_DATABASE_URI'],
        experiment.id
    ])

    flask.flash('Queued Experiment {} with task {}. You can now upload another experiment for Query {}'.format(
        experiment.id, task, query_id)
    )
    return redirect(url_for('.view_query_uploader', query_id=query_id))


@experiment_blueprint.route('/from_network/<int:network_id>/upload/', methods=('GET', 'POST'))
@login_required
def view_network_uploader(network_id):
    """View the uploader for a network.

    :param int network_id: The identifier ot the network to query against
    """
    network = manager.safe_get_network(user=current_user, network_id=network_id)
    query = Query.from_network(network=network, user=current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect(url_for('.view_query_uploader', query_id=query.id))


@experiment_blueprint.route('/comparison/<list:experiment_ids>.tsv')
def download_experiment_comparison(experiment_ids):
    """Different data analyses on same query

    :param list[int] experiment_ids: The identifiers of experiments to compare
    :return: flask.Response
    """
    log.info('working on experiments: %s', experiment_ids)

    clusters = request.args.get('clusters', type=int)
    normalize = request.args.get('normalize', type=int, default=0)
    seed = request.args.get('seed', type=int)

    experiments = manager.safe_get_experiments(user=current_user, experiment_ids=experiment_ids)
    df = get_dataframe_from_experiments(experiments, normalize=normalize, clusters=clusters, seed=seed)

    si = StringIO()
    df.to_csv(si, index=False, sep='\t')
    output = make_response(si.getvalue())
    output.headers["Content-type"] = "text/tab-separated-values"
    return output


def render_experiment_comparison(experiments):
    """
    :param list[pybel_web.models.Experiment] experiments:
    :return:
    """
    experiments = list(experiments)
    experiment_ids = [experiment.id for experiment in experiments]

    return render_template(
        'experiment/experiments_compare.html',
        experiment_ids=experiment_ids,
        experiments=experiments,
        normalize=request.args.get('normalize', type=int, default=0),
        clusters=request.args.get('clusters', type=int),
        seed=request.args.get('seed', type=int),
    )


@experiment_blueprint.route('/comparison/<list:experiment_ids>')
def view_experiment_comparison(experiment_ids):
    """Different data analyses on same query

    :param list[int] experiment_ids: The identifiers of experiments to compare
    """
    experiments = manager.safe_get_experiments(user=current_user, experiment_ids=experiment_ids)
    return render_experiment_comparison(experiments)


@experiment_blueprint.route('/comparison/query/<int:query_id>')
def view_query_experiment_comparison(query_id):
    """Different data analyses on same query

    :param int query_id: The query identifier whose related experiments to compare
    """
    query = manager.safe_get_query(user=current_user, query_id=query_id)
    return render_experiment_comparison(query.experiments)
