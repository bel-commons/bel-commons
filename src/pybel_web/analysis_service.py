# -*- coding: utf-8 -*-

import json
import logging
import time
from collections import defaultdict
from io import StringIO
from operator import itemgetter

import flask
import numpy as np
import pandas as pd
import pandas.errors
from flask import Blueprint, abort, current_app, make_response, redirect, render_template, request, url_for
from flask_security import current_user, login_required, roles_required
from sklearn.cluster import KMeans

from pybel_tools.analysis.ucmpa import RESULT_LABELS
from .content import safe_get_query
from .forms import DifferentialGeneExpressionForm
from .manager_utils import create_omic, next_or_jsonify, safe_get_experiment
from .models import Experiment, Omic, Query
from .utils import get_network_ids_with_permission_helper, manager, user_datastore

log = logging.getLogger(__name__)

experiment_blueprint = Blueprint('analysis', __name__, url_prefix='/experiment')


@experiment_blueprint.route('/omic/')
def view_omics():
    """Views a list of all omics data sets"""
    query = manager.session.query(Omic).filter(Omic.public).order_by(Omic.created.desc())
    return render_template('omic/omics.html', omics=query.all(), current_user=current_user)


@experiment_blueprint.route('/omic/<int:omic_id>')
def view_omic(omic_id):
    """Views an Omic model"""
    omic = manager.session.query(Omic).get(omic_id)

    data = omic.get_source_dict()
    values = list(data.values())
    count = len(values)
    std = np.std(values)
    mean = np.mean(values)
    median = np.median(values)
    mini = np.min(values)
    maxi = np.max(values)
    return render_template('omic/omic.html', omic=omic, current_user=current_user, count=count, mean=mean,
                           median=median,
                           std=std, minimum=mini, maximum=maxi)


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
    experiment = safe_get_experiment(manager, experiment_id, current_user)

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
        omic=omic
    )

    manager.session.add(experiment)
    manager.session.commit()

    log.debug('stored data for analysis in %.2f seconds', time.time() - t)

    task = current_app.celery.send_task('run-cmpa', args=[
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
    """Views the results of analysis on a given graph

    :param int network_id: The identifier ot the network to query against
    """
    if network_id not in get_network_ids_with_permission_helper(user=current_user, manager=manager,
                                                                user_datastore=user_datastore):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    query = Query.from_query_args(manager, [network_id], current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect(url_for('.view_query_uploader', query_id=query.id))


def get_dataframe_from_experiments(experiments, *, normalize=None, clusters=None, seed=None):
    """Builds a Pandas DataFrame from the list of experiments

    :param iter[Experiment] experiments: Experiments to work on
    :param bool normalize:
    :param Optional[int] clusters: Number of clusters to use in k-means
    :param Optional[int] seed: Random number seed
    :rtype: pandas.DataFrame
    """
    x_label = ['Type', 'Namespace', 'Name']

    entries = defaultdict(list)

    for experiment in experiments:
        if experiment.result is None:
            continue

        x_label.append('[{}] {}'.format(experiment.id, experiment.source_name))

        for (func, namespace, name), values in sorted(experiment.get_data_list()):
            median_value = values[3]
            entries[func, namespace, name].append(median_value)

    result = [
        list(entry) + list(values)
        for entry, values in entries.items()
    ]

    df = pd.DataFrame(result, columns=x_label)
    df = df.fillna(0).round(4)

    data_columns = x_label[3:]

    if normalize:
        df[data_columns] = df[data_columns].apply(lambda x: (x - np.min(x)) / (np.max(x) - np.min(x)))

    if clusters is not None:
        log.info('using %d-means clustering', clusters)
        log.info('using seed: %s', seed)
        km = KMeans(n_clusters=clusters, random_state=seed)
        km.fit(df[data_columns])
        df['Group'] = km.labels_ + 1
        df = df.sort_values('Group')

    return df


def safe_get_experiments(experiment_ids):
    """Safely gets a list of experiments

    :param list[int] experiment_ids:
    :rtype: list[Experiment]
    """
    return [
        safe_get_experiment(manager, experiment_id, current_user)
        for experiment_id in experiment_ids
    ]


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

    experiments = safe_get_experiments(experiment_ids)
    df = get_dataframe_from_experiments(experiments, normalize=normalize, clusters=clusters, seed=seed)

    si = StringIO()
    df.to_csv(si, index=False, sep='\t')
    output = make_response(si.getvalue())
    output.headers["Content-type"] = "text/tab-separated-values"
    return output


def render_experiment_comparison(experiment_ids, experiments):
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
    experiments = safe_get_experiments(experiment_ids)
    return render_experiment_comparison(experiment_ids, experiments)


@experiment_blueprint.route('/comparison/query/<int:query_id>')
def view_query_experiment_comparison(query_id):
    """Different data analyses on same query

    :param int query_id: The query identifier whose related experiments to compare
    """
    query = safe_get_query(query_id)
    experiment_ids = [experiment.id for experiment in query.experiments]
    return render_experiment_comparison(experiment_ids, query.experiments)
