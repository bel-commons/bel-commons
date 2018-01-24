# -*- coding: utf-8 -*-

"""This module contains the user interface to PyBEL Web"""

import datetime
import itertools as itt
import logging
import sys
import time
from collections import defaultdict

import flask
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_security import current_user, login_required, roles_required

import pybel_tools.query
from pybel.constants import CITATION_TYPE_PUBMED
from pybel.manager.models import Annotation, Edge, Namespace, Node
from pybel.utils import get_version as get_pybel_version
from pybel_tools.pipeline import no_arguments_map
from pybel_tools.utils import get_version as get_pybel_tools_version
from . import models
from .constants import *
from .manager import *
from .models import Project, Query, Report, User
from .utils import (
    calculate_overlap_dict, get_network_ids_with_permission_helper, get_networks_with_permission,
    manager, next_or_jsonify, query_form_to_dict, query_from_network, redirect_explorer, render_network_summary_safe,
    safe_get_network, safe_get_query,
)

log = logging.getLogger(__name__)

ui_blueprint = Blueprint('ui', __name__)
time_instantiated = str(datetime.datetime.now())


def _serve_relations(edges, source, target=None):
    """Serves a list of edges

    :param iter[pybel.manager.models.Edge] edges:
    :param Node source:
    :param Node target:
    :rtype: flask.Response
    """
    data = defaultdict(list)
    ev2cit = {}
    for edge in edges:
        if not edge.evidence:
            continue
        ev = edge.evidence.text
        data[ev].append((edge, edge.to_json()))
        ev2cit[ev] = edge.evidence.citation.to_json()

    return render_template(
        'evidence_list.html',
        data=data,
        ev2cit=ev2cit,
        source_bel=source.bel,
        target_bel=target.bel if target else None,
    )


@ui_blueprint.route('/', methods=['GET', 'POST'])
def home():
    """The home page has links to the main features of PyBEL Web:

    1. BEL Parser
    2. Curation Tools
    3. Namespace and Annotation Store
    4. Network/Edge/NanoPub Store Navigator
    5. Query Builder
    """
    return render_template('index.html', current_user=current_user)


@ui_blueprint.route('/networks', methods=['GET', 'POST'])
def view_networks():
    """The networks page has two components: a search box, and a list of networks. Each network is shown by name,
    with the version number and the first author. Each has several actions:

    1. View one of the following summaries:
      - Statistical summary
      - Compilation summary
      - Biological grammar summary

    2. Explore the full network, or a random subgraph if it is too big.
    3. Create a biological query starting with this network
    4. Analyze the network with one of the procedures (CMPA, etc.)
    5. Execute one of the following actions if the current user is the owner:
      - Drop
      - Make public/private
    """
    networks = get_networks_with_permission(manager)

    return render_template(
        'networks.html',
        networks=sorted(networks, key=lambda network: network.created, reverse=True),
        current_user=current_user,
        BMS_BASE=current_app.config.get('BMS_BASE'),
    )


@ui_blueprint.route('/edges')
@roles_required('admin')
def view_edges():
    """Renders a page viewing all edges"""
    return render_template('edges.html', edges=manager.session.query(Edge).limit(15), current_user=current_user)


@ui_blueprint.route('/edge/<edge_hash>')
@roles_required('admin')
def view_edge(edge_hash):
    """Renders a page viewing a single edges

    :param str edge_hash: The identifier of the edge to display
    """
    return render_template('edges.html', edges=[manager.get_edge_by_hash(edge_hash)], current_user=current_user)

@ui_blueprint.route('/nodes')
@roles_required('admin')
def view_nodes():
    """Renders a page viewing all edges"""
    return render_template(
        'nodes.html',
        nodes=manager.session.query(Node),
        current_user=current_user,
        hgnc_manager=hgnc_manager,
        chebi_manager=chebi_manager,
        go_manager=go_manager,
    )


@ui_blueprint.route('/network/<int:network_id>/explore', methods=['GET'])
def view_explore_network(network_id):
    """Renders a page for the user to explore a network

    :param int network_id: The identifier of the network to explore
    """
    if network_id not in get_network_ids_with_permission_helper(current_user, manager):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    query = query_from_network(network_id)


    return redirect_explorer(query.id)


@ui_blueprint.route('/explore/<int:query_id>', methods=['GET'])
def view_explorer_query(query_id):
    """Renders a page for the user to explore a network

    :param int query_id: The identifier of the query
    """
    query = safe_get_query(query_id)
    return render_template('explorer.html', query=query, explorer_toolbox=get_explorer_toolbox())


@ui_blueprint.route('/project/<int:project_id>/explore', methods=['GET'])
@login_required
def view_explore_project(project_id):
    """Renders a page for the user to explore the full network from a project

    :param int project_id: The identifier of the project to explore
    """
    project = manager.session.query(Project).get(project_id)

    q = pybel_tools.query.Query(network_ids=[
        network.id
        for network in project.networks
    ])

    query = Query.from_query(manager, q, current_user)
    query.assembly.name = '{} query of {}'.format(time.asctime(), project.name)

    manager.session.add(query)
    manager.session.commit()

    return redirect_explorer(query.id)


@ui_blueprint.route('/query/build', methods=['GET', 'POST'])
def view_query_builder():
    """Renders the query builder page"""
    networks = get_networks_with_permission(manager)

    return render_template(
        'query_builder.html',
        networks=networks,
        current_user=current_user,
        preselected=request.args.get('start', type=int)
    )


@ui_blueprint.route('/query/compile', methods=['POST'])
def get_pipeline():
    """Executes a pipeline"""
    d = query_form_to_dict(request.form)
    q = pybel_tools.query.Query.from_json(d)
    query = models.Query.from_query(manager, q, current_user)

    manager.session.add(query)
    manager.session.commit()

    return redirect_explorer(query.id)


@ui_blueprint.route('/namespaces')
def view_namespaces():
    """Displays a page listing the namespaces."""
    return render_template(
        'namespaces.html',
        namespaces=manager.session.query(Namespace).order_by(Namespace.keyword).all(),
        current_user=current_user,
    )


@ui_blueprint.route('/annotations')
def view_annotations():
    """Displays a page listing the annotations."""
    return render_template(
        'annotations.html',
        annotations=manager.session.query(Annotation).order_by(Annotation.keyword).all(),
        current_user=current_user,
    )


@ui_blueprint.route('/imprint')
def view_imprint():
    """Renders the impressum"""
    return render_template('imprint.html')


@ui_blueprint.route('/about')
def view_about():
    """Sends the about page"""
    metadata = [
        ('Python Version', sys.version),
        ('PyBEL Version', get_pybel_version()),
        ('PyBEL Tools Version', get_pybel_tools_version()),
        ('PyBEL Web version', PYBEL_WEB_VERSION),
        ('Deployed', time_instantiated)
    ]

    return render_template('about.html', metadata=metadata)


@ui_blueprint.route('/user')
@login_required
def view_current_user_activity():
    """Returns the current user's history."""
    pending_reports = current_user.pending_reports()
    return render_template('user_activity.html', user=current_user, pending_reports=pending_reports,
                           manager=manager)


@ui_blueprint.route('/summary/<int:network_id>')
def view_summarize_statistics(network_id):
    """Renders a page with the statistics of the contents of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_statistics.html')


@ui_blueprint.route('/summary/<int:network_id>/compilation')
def view_summarize_compilation(network_id):
    """Renders a page with the compilation summary of the contents of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_compilation.html')


@ui_blueprint.route('/summary/<int:network_id>/warnings')
def view_summarize_warnings(network_id):
    """Renders a page with the parsing errors from a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_warnings.html')


@ui_blueprint.route('/summary/<int:network_id>/biogrammar')
def view_summarize_biogrammar(network_id):
    """Renders a page with the summary of the biogrammar analysis of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_biogrammar.html')


@ui_blueprint.route('/how_to_use', methods=['GET'])
def view_how_to_use():
    """Shows How to use PyBEL-web"""
    return render_template('how_to_use.html')


@ui_blueprint.route('/pipeline/help', methods=['GET'])
def view_pipeline_help():
    """View the help info for the functions"""

    data = []
    for fname, f in no_arguments_map.items():

        if f.__doc__ is None:
            log.warning('No documentation for %s', fname)
            continue

        data.append((fname.replace('_', ' ').title(), f.__doc__.split('\n\n')[0]))

    return render_template(
        'pipeline_help.html',
        function_dict=data
    )


@ui_blueprint.route('/network/<int:network_1_id>/compare/<int:network_2_id>')
def view_network_comparison(network_1_id, network_2_id):
    """View the comparison between two networks

    :param int network_1_id: Identifier for the first network
    :param int network_2_id: Identifier for the second network
    """
    safe_get_network(network_1_id)
    safe_get_network(network_2_id)

    q1 = query_from_network(network_1_id)
    q2 = query_from_network(network_2_id)

    log.info('q1: %s from n1 %s', q1, network_1_id)
    log.info('q2: %s from n2 %s', q2, network_2_id)

    return redirect(url_for(
        '.view_query_comparison',
        query_1_id=q1.id,
        query_2_id=q2.id
    ))


@ui_blueprint.route('/query/<int:query_1_id>/compare/<int:query_2_id>')
def view_query_comparison(query_1_id, query_2_id):
    """View the comparison between the result of two queries

    :param int query_1_id: The identifier of the first query
    :param int query_2_id: The identifier of the second query
    """

    query_1 = safe_get_query(query_1_id)
    query_2 = safe_get_query(query_2_id)

    query_1_result = query_1.run(manager)
    query_2_result = query_2.run(manager)

    data = calculate_overlap_dict(
        g1=query_1_result,
        g1_label='Query {}'.format(query_1_id),
        g2=query_2_result,
        g2_label='Query {}'.format(query_2_id),
    )

    return render_template(
        'query_comparison.html',
        query_1_id=query_1_id,
        query_2_id=query_2_id,
        data=data,
    )


@ui_blueprint.route('/citation/pubmed/<pmid>')
def view_pubmed(pmid):
    """View all evidences and relations extracted from the article with the given PubMed identifier

    :param str pmid: The PubMed identifier
    """
    citation = manager.get_citation_by_reference(CITATION_TYPE_PUBMED, pmid)

    return render_template('citation.html', citation=citation)


@ui_blueprint.route('/node/<source_id>/edges/<target_id>')
def view_relations(source_id, target_id):
    """View a list of all relations between two nodes

    :param str source_id: The source node's hash
    :param str target_id: The target node's hash
    """
    source = manager.get_node_by_hash(source_id)
    target = manager.get_node_by_hash(target_id)
    relations = list(manager.query_edges(source=source, target=target))

    if 'undirected' in request.args:
        relations.extend(manager.query_edges(source=target, target=source))

    return _serve_relations(relations, source, target)


@ui_blueprint.route('/node/<node_id>')
def view_node(node_id):
    """View a node summary with a list of all edges incident to the node

    :param str node_id: The node's hash
    """
    node = manager.get_node_by_hash(node_id)

    if node is None:
        abort(404, 'Node not found: {}'.format(node_id))

    relations = list(itt.chain(
        manager.query_edges(source=node),
        manager.query_edges(target=node)
    ))
    return _serve_relations(relations, node)


@ui_blueprint.route('/download/bel/<fid>')
def download_saved_file(fid):
    """Downloads a BEL file

    :param str fid: The file's identifier
    """
    name = '{}.bel'.format(fid)
    path = os.path.join(merged_document_folder, name)

    if not os.path.exists(path):
        abort(404, 'BEL file does not exist')

    rv = flask.send_file(path)

    # TODO delete as cleanup
    return rv


##########################################
# The following endpoints are admin only #
##########################################

@ui_blueprint.route('/users')
@roles_required('admin')
def view_users():
    """Renders a list of users"""
    return render_template('view_users.html', users=manager.session.query(User))


@ui_blueprint.route('/user/<int:user_id>')
@roles_required('admin')
def view_user_activity(user_id):
    """Returns the given user's history

    :param int user_id: The identifier of the user to summarize
    """
    user = manager.session.query(User).get(user_id)
    pending_reports = user.pending_reports()
    return render_template('user_activity.html', user=user, pending_reports=pending_reports, manager=manager)


@ui_blueprint.route('/reporting', methods=['GET'])
@roles_required('admin')
def view_reports():
    """Shows the uploading reporting"""
    return render_template('reporting.html', reports=manager.session.query(Report).order_by(Report.created).all())


@ui_blueprint.route('/overview')
@roles_required('admin')
def view_overview():
    """Views the overview"""
    return render_template('overview.html')


@ui_blueprint.route('/admin/rollback')
@roles_required('admin')
def rollback():
    """Rolls back the transaction for when something bad happens"""
    manager.session.rollback()
    return next_or_jsonify('rolled back')


@ui_blueprint.route('/admin/nuke/')
@roles_required('admin')
def nuke():
    """Destroys the database and recreates it"""
    log.info('nuking database')
    manager.drop_all(checkfirst=True)
    log.info('   the dust settles')
    return next_or_jsonify('nuked the database')


@ui_blueprint.route('/admin/configuration')
@roles_required('admin')
def view_config():
    """Render the configuration"""
    return render_template('deployment.html', config=current_app.config)


#######################################
# The following endpoints are helpers #
#######################################

@ui_blueprint.route('/project/<int:project_id>/merge/<int:user_id>')
def send_async_project_merge(user_id, project_id):
    """A helper endpoint to submit a project to the asynchronous task queue to merge its associated networks.

    :param int user_id: The identifier of the user sending the task
    :param int project_id: The identifier of the project to merge
    """
    task = current_app.celery.send_task('merge-project', args=[user_id, project_id])
    flash('Merge task sent: {}'.format(task))
    return redirect(url_for('ui.view_current_user_activity'))


@ui_blueprint.route('/network/<int:network_id>/induction-query/')
def build_summary_link_query(network_id):
    """Builds a query with the given network by inducing a subgraph over the nodes included in the request

    :param int network_id: The identifier of the network
    """
    nodes = [
        manager.get_node_tuple_by_hash(node_hash)
        for node_hash in request.args.getlist('nodes')
    ]

    q = pybel_tools.query.Query([network_id])
    q.append_seeding_induction(nodes)
    query = Query.from_query(manager, q, current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect_explorer(query.id)


@ui_blueprint.route('/network/<int:network_id>/sample/')
def build_subsample_query(network_id):
    """Builds and executes a query that induces a random subnetwork over the given network

    :param int network_id: The identifier of the network
    """
    q = pybel_tools.query.Query([network_id])
    q.append_seeding_sample()
    query = Query.from_query(manager, q, current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect_explorer(query.id)
