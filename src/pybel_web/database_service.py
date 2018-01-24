# -*- coding: utf-8 -*-

"""This module runs the database-backed PyBEL API"""

import csv
import logging
import pickle
import random
import time
from functools import lru_cache
from io import StringIO
from operator import itemgetter

import flask
import networkx as nx
from flask import Blueprint, abort, current_app, flash, jsonify, make_response, redirect, request
from flask_security import current_user, login_required, roles_required
from sqlalchemy import func

import pybel
from pybel.constants import METADATA_AUTHORS, METADATA_CONTACT, METADATA_NAME, NAME, NAMESPACE, NAMESPACE_DOMAIN_OTHER
from pybel.manager.models import (
    Annotation, AnnotationEntry, Author, Citation, Edge, Namespace, Network, Node, network_edge,
)
from pybel.resources.definitions import write_annotation, write_namespace
from pybel.struct import union
from pybel.struct.summary import get_pubmed_identifiers
from pybel.utils import hash_node
from pybel_tools import pipeline
from pybel_tools.analysis.cmpa import RESULT_LABELS
from pybel_tools.filters.node_filters import exclude_pathology_filter
from pybel_tools.mutation import add_canonical_names
from pybel_tools.query import Query
from pybel_tools.selection import get_subgraph_by_annotations, get_subgraph_by_node_filter
from pybel_tools.summary import (
    get_authors, get_incorrect_names_by_namespace, get_naked_names, get_tree_annotations, get_undefined_namespace_names,
    info_json, info_list,
)
from . import models
from .constants import *
from .main_service import BLACK_LIST, PATHS_METHOD, UNDIRECTED
from .manager import *
from .models import EdgeComment, Experiment, Project, Report, User
from .send_utils import serve_network, to_json_custom
from .utils import (
    current_user_has_query_rights, fill_out_report, get_edge_by_hash_or_404,
    get_network_ids_with_permission_helper, get_network_or_404, get_node_by_hash_or_404, get_node_overlaps,
    get_or_create_vote, get_query_ancestor_id, get_recent_reports, help_get_edge_entry, make_graph_summary, manager,
    next_or_jsonify, safe_get_network, safe_get_project, safe_get_query, user_datastore,
)

log = logging.getLogger(__name__)

api_blueprint = Blueprint('dbs', __name__)


@lru_cache(maxsize=64)
def get_graph_from_request(query_id):
    """Process the GET request returning the filtered network

    :param int query_id: The database query identifier
    :rtype: Optional[pybel.BELGraph]
    """
    query = safe_get_query(query_id)
    return query.run(manager)


@api_blueprint.route('/api/receive', methods=['POST'])
def receive():
    """Receives a JSON serialized BEL graph"""
    # TODO assume https authentication and use this to assign user to receive network function
    payload = request.get_json()
    task = current_app.celery.send_task('receive-network', args=[payload])
    return next_or_jsonify('Sent async receive task', network_id=task.id)


####################################
# NAMESPACE
####################################

@api_blueprint.route('/api/namespaces')
def list_namespaces():
    """Lists all namespaces

    ---
    tags:
        - namespace
    """
    return jsonify([
        namespace.to_json(include_id=True)
        for namespace in manager.list_namespaces()
    ])


@api_blueprint.route('/api/namespace/<int:namespace_id>/drop')
@roles_required('admin')
def drop_namespace_by_id(namespace_id):
    """Drops a namespace given its identifier

    ---
    tags:
        - namespace
    parameters:
      - name: namespace_id
        in: path
        description: The database namespace identifier
        required: true
        type: integer
    """
    namespace = manager.session.query(Namespace).get(namespace_id)

    if namespace is None:
        abort(404)

    log.info('dropping namespace %s', namespace_id)

    manager.session.delete(namespace)
    manager.session.commit()

    return next_or_jsonify(
        'Dropped namespace: {}'.format(namespace),
        namespace={
            'id': namespace.id,
            'name': namespace.name
        }
    )


@api_blueprint.route('/api/namespace/drop')
@roles_required('admin')
def drop_namespaces():
    """Drops all namespaces

    ---
    tags:
        - namespace
    """
    log.info('dropping all namespaces')
    manager.session.query(Namespace).delete()
    manager.session.commit()

    return next_or_jsonify('Dropped all namespaces')


def _build_namespace_helper(graph, namespace, names):
    """Helps build a response holding a BEL namespace"""
    si = StringIO()

    write_namespace(
        namespace_name=namespace,
        namespace_keyword=namespace,
        namespace_domain=NAMESPACE_DOMAIN_OTHER,
        author_name=graph.document.get(METADATA_AUTHORS),
        author_contact=graph.document.get(METADATA_CONTACT),
        citation_name=graph.document.get(METADATA_NAME),
        citation_description='This namespace was serialized by PyBEL Web',
        cacheable=False,
        values=names,
        file=si
    )

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}.belns".format(namespace)
    output.headers["Content-type"] = "text/plain"
    return output


@api_blueprint.route('/api/network/<int:network_id>/builder/namespace/undefined/<namespace>')
def download_undefined_namespace(network_id, namespace):
    """Outputs a namespace built for this undefined namespace

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
      - name: namespace
        in: path
        description: The keyword of the namespace to extract
        required: true
        type: string
    """
    graph = safe_get_graph(network_id)
    names = get_undefined_namespace_names(graph, namespace)  # TODO put into report data
    return _build_namespace_helper(graph, namespace, names)


@api_blueprint.route('/api/network/<int:network_id>/builder/namespace/incorrect/<namespace>')
def download_missing_namespace(network_id, namespace):
    """Outputs a namespace built from the missing names in the given namespace

    ---
    tags:
        - network
        - namespace
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
      - name: namespace
        in: path
        description: The keyword of the namespace to extract
        required: true
        type: string
    """
    graph = safe_get_graph(network_id)
    names = get_incorrect_names_by_namespace(graph, namespace)  # TODO put into report data
    return _build_namespace_helper(graph, namespace, names)


@api_blueprint.route('/api/network/<int:network_id>/builder/namespace/naked')
def download_naked_names(network_id):
    """Outputs a namespace built from the naked names in the given namespace

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The identifier of a network
        required: true
        type: integer
    """
    graph = safe_get_graph(network_id)
    names = get_naked_names(graph)  # TODO put into report data
    return _build_namespace_helper(graph, 'NAKED', names)


def _build_annotation_helper(graph, annotation, values):
    """Builds an annoation document helper

    :param pybel.BELGraph graph:
    :param str annotation:
    :param dict[str,str] values:
    :rtype: flask.Response
    """
    si = StringIO()

    write_annotation(
        keyword=annotation,
        values=values,
        author_name=graph.document.get(METADATA_AUTHORS),
        author_contact=graph.document.get(METADATA_CONTACT),
        citation_name=graph.document.get(METADATA_NAME),
        description='This annotation was serialize by PyBEL Web from {}'.format(graph),
        file=si,
    )

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}.belanno".format(annotation)
    output.headers["Content-type"] = "text/plain"
    return output


@api_blueprint.route('/api/network/<int:network_id>/builder/annotation/list/<annotation>')
def download_list_annotation(network_id, annotation):
    """Outputs an annotation built from the given list definition

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
      - name: annotation
        in: path
        description: The keyword of the annotation to extract
        required: true
        type: string
    """
    graph = safe_get_graph(network_id)

    if annotation not in graph.annotation_list:
        abort(400, 'Graph does not contain this list annotation')

    # Convert to dict with no labels
    values = {
        value: ''
        for value in graph.annotation_list[annotation]
    }

    return _build_annotation_helper(graph, annotation, values)


####################################
# ANNOTATIONS
####################################

@api_blueprint.route('/api/annotation')
def list_annotations():
    """Lists all annotations

    ---
    tags:
        - annotation
    """
    return jsonify([
        annotation.to_json(include_id=True)
        for annotation in manager.list_annotations()
    ])


@api_blueprint.route('/api/annotation/<annotation_id>/drop')
@roles_required('admin')
def drop_annotation_by_id(annotation_id):
    """Drops an annotation given its identifier

    ---
    tags:
        - annotation
    parameters:
      - name: annotation_id
        in: path
        description: The database identifier of an annotation
        required: true
        type: integer
    """
    annotation = manager.session.query(Annotation).get(annotation_id)

    if annotation is None:
        abort(404)

    manager.session.delete(annotation)
    manager.session.commit()

    return next_or_jsonify('Dropped annotation: {}'.format(annotation))


@api_blueprint.route('/api/annotation/drop')
@roles_required('admin')
def drop_annotations():
    """Drops all annotations

    ---
    tags:
        - annotation
    """
    log.info('dropping all annotations')
    manager.session.query(Annotation).delete()
    manager.session.commit()

    return next_or_jsonify('Dropped all annotations')


@api_blueprint.route('/api/annotation/suggestion/')
def suggest_annotation():
    """Creates a suggestion for annotations

    ---
    tags:
        - annotation
    parameters:
      - name: q
        in: query
        description: The search term
        default: Brain
        required: true
        type: string
    """
    q = request.args.get('q')

    if not q:
        return jsonify([])

    entries = manager.session.query(AnnotationEntry).filter(AnnotationEntry.name.contains(q))

    return jsonify([
        {
            'id': entry.id,
            'url': entry.annotation.url,
            'annotation': entry.annotation.keyword,
            'value': entry.name
        }
        for entry in entries
    ])


####################################
# NETWORKS
####################################

@api_blueprint.route('/api/network/<int:network_id>')
@roles_required('admin')
def get_network_metadata(network_id):
    """Returns network metadata

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    responses:
      200:
        description: The metadata describing the network
    """
    network = get_network_or_404(network_id)

    return jsonify(**network.to_json(include_id=True))


@api_blueprint.route('/api/network/<int:network_id>/namespaces')
def namespaces_by_network(network_id):
    """Gets all of the namespaces in a network

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    responses:
      200:
        description: The namespaces described in this network
    """
    abort(501)


@api_blueprint.route('/api/network/<int:network_id>/annotations')
def annotations_by_network(network_id):
    """Gets all of the annotations in a network

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    responses:
      200:
        description: The annotations referenced by the network
    """
    abort(501)


@api_blueprint.route('/api/network/<int:network_id>/citations')
def citations_by_network(network_id):
    """Gets all of the citations in a given network

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    responses:
      200:
        description: The citations referenced by the edges in the network
    """
    abort(501)


@api_blueprint.route('/api/network/<int:network_id>/edges')
def edges_by_network(network_id):
    """Gets all of the edges in a network

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer

      - name: offset
        in: query
        required: false
        type: integer
        default: 0
        description: The database offset

      - name: limit
        in: query
        required: false
        type: integer
        default: 100
        description: The database limit

    responses:
      200:
        description: The edges in the network
    """
    offset = request.args.get('offset', default=0, type=int)
    limit = request.args.get('limit', default=100, type=int)

    # FIXME check user rights for network

    edges = manager.session.query(Edge). \
        join(network_edge).join(Network). \
        filter(Network.id == network_id). \
        offset(offset).limit(limit)

    return jsonify([
        edge.to_json(include_id=True, include_hash=True)
        for edge in edges
    ])


@api_blueprint.route('/api/network/<int:network_id>/nodes/')
def nodes_by_network(network_id):
    """Gets all of the nodes in a network

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    responses:
      200:
        description: The nodes referenced by the edges in the network
    """
    network = manager.get_network_by_id(network_id)
    return jsonify_nodes(network.nodes)


def drop_network_helper(network_id):
    """Drops a network

    :type network_id: int
    :rtype: flask.Response
    """
    network = safe_get_network(network_id)

    log.info('dropping network %s', network_id)

    try:
        manager.drop_network(network)

    except Exception as e:
        manager.session.rollback()

        if 'next' in request.args:
            flash('Dropped network #{} failed: {}'.format(network_id, e), category='error')
            return redirect(request.args['next'])

        return jsonify({
            'status': 400,
            'action': 'drop network',
            'network_id': network_id,
            'exception': str(e),
        })

    else:
        return next_or_jsonify('Dropped network #{}'.format(network_id), network_id=network_id, action='drop network')


@api_blueprint.route('/api/network/<int:network_id>/drop')
@login_required
def drop_network(network_id):
    """Drops a specific graph

    :param int network_id: The identifier of the network to drop

    ---
    tags:
        - network

    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer

    responses:
      200:
        description: The network was dropped
    """
    return drop_network_helper(network_id)


@api_blueprint.route('/api/network/drop')
@roles_required('admin')
def drop_networks():
    """Drops all networks

    ---
    tags:
        - network

    responses:
      200:
        description: All networks were dropped
    """
    log.info('dropping all networks')

    for network_id, in manager.session.query(Network.id).all():
        drop_network_helper(network_id)

    return next_or_jsonify('Dropped all networks')


def _help_claim_network(network, user):
    """Claims a network and fills out its report

    :param Network network: A network to claim
    :param User user: The user who will claim it
    :rtype: Optional[Report]
    """
    if network.report:
        return

    graph = network.as_bel()
    add_canonical_names(graph)
    network.store_bel(graph)

    manager.session.add(network)
    manager.session.commit()

    graph_summary = make_graph_summary(graph)

    report = Report(
        user=user,
        public=False,
        time=0.0,
    )

    fill_out_report(network, report, graph_summary)

    manager.session.add(report)
    manager.session.commit()

    return report


@api_blueprint.route('/api/network/<int:network_id>/claim')
@roles_required('admin')
def claim_network(network_id):
    """Adds a report for the given network

    :param int network_id: A network's database identifier

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    """
    network = get_network_or_404(network_id)

    res = _help_claim_network(network, current_user)

    if not res:
        return next_or_jsonify(
            'Already claimed by {}'.format(network.report.user),
            network={'id': network.id},
            owner={'id': network.report.user.id},
        )

    return next_or_jsonify(
        'Claimed {}'.format(network),
        network={'id': network.id},
        owner={'id': current_user.id}
    )


@api_blueprint.route('/api/network/pillage')
@roles_required('admin')
def pillage():
    """Claims all unclaimed networks"""
    counter = 0
    t = time.time()

    for network in manager.session.query(Network):
        if network.report is not None:
            continue

        res = _help_claim_network(network, current_user)

        if res:
            counter += 1

    return next_or_jsonify('Claimed {} networks in {:.2f} seconds'.format(counter, time.time() - t))


@api_blueprint.route('/api/network')
def get_network_list():
    """Gets a list of networks

    ---
    tags:
        - network
    """
    return jsonify([
        network.to_json(include_id=True)
        for network in manager.list_networks()
    ])


@api_blueprint.route('/api/network/<int:network_id>/export/<serve_format>')
def export_network(network_id, serve_format):
    """Builds a graph from the given network id and sends it in the given format

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer

      - name: serve_format
        in: path
        description: The format of the network to return
        required: false
        schema:
            type: string
            enum:
              - json
              - cx
              - jgif
              - bytes
              - bel
              - graphml
              - sif
              - csv
              - gsea
    """
    network_ids = get_network_ids_with_permission_helper(current_user, manager)

    if network_id not in network_ids:
        abort(403, 'You do not have permission to download the selected network')

    graph = manager.get_graph_by_id(network_id)

    return serve_network(graph, serve_format)


@api_blueprint.route('/api/network/<int:network_id>/summarize')
def get_graph_info_json(network_id):
    """Gets a summary of the given network

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    responses:
      200:
        description: A summary of the network
    """
    network = manager.get_network_by_id(network_id)
    return jsonify(network.report.as_info_json())


@api_blueprint.route('/api/network/<int:network_id>/name')
def get_network_name_by_id(network_id):
    """Returns network name given its id

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    """
    network = manager.get_network_by_id(network_id)
    return jsonify(network.name)


def update_network_status(network_id, public):
    """Update whether a network is public or private
    
    :param int network_id: 
    :param bool public:
    """
    network = get_network_or_404(network_id)

    if network.report is None:
        abort(400)

    if not current_user.is_admin or current_user.id != network.report.user_id:
        abort(403, 'You do not have permission to modify that network')

    network.report.public = public
    manager.session.commit()

    return next_or_jsonify(
        'Set public to {} for {}'.format(public, network),
        network_id=network_id,
        public=public,
    )


@api_blueprint.route('/api/network/<int:network_id>/make_public')
@login_required
def make_network_public(network_id):
    """Makes a given network public using admin powers

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    """
    return update_network_status(network_id, True)


@api_blueprint.route('/api/network/<int:network_id>/make_private')
@login_required
def make_network_private(network_id):
    """Makes a given network private using admin powers

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database network identifier
        required: true
        type: integer
    """
    return update_network_status(network_id, False)


####################################
# NETWORK QUERIES
####################################

@lru_cache(maxsize=64)
def get_tree_from_query(query_id):
    """Gets the tree json for a given network

    :param int query_id:
    :rtype: dict
    """
    graph = get_graph_from_request(query_id)

    if graph is None:
        return

    return get_tree_annotations(graph)


@api_blueprint.route('/api/query/<int:query_id>.json')
def download_query_json(query_id):
    """Downloads the query"""
    query = safe_get_query(query_id)
    query_json = query.to_json()
    return jsonify(query_json)


@api_blueprint.route('/api/query/<int:query_id>/tree/')
def get_tree_api(query_id):
    """Builds the annotation tree data structure for a given graph

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """

    rv = {
        'query': query_id
    }

    tree = get_tree_from_query(query_id)

    if tree is not None:
        rv['status'] = True
        rv['payload'] = tree
    else:
        rv['status'] = False

    return jsonify(rv)


@api_blueprint.route('/api/query/<int:query_id>/rights/')
def check_query_rights(query_id):
    """Returns if the current user has rights to the given query

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """
    return jsonify({
        'status': 200,
        'query_id': query_id,
        'allowed': current_user_has_query_rights(query_id)
    })


@api_blueprint.route('/api/query/<int:query_id>/export/<serve_format>')
def download_network(query_id, serve_format):
    """Downloads a network in the given format

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer

      - name: serve_format
        in: path
        description: The format of the network to return
        required: false
        schema:
            type: string
            enum:
              - json
              - cx
              - jgif
              - bytes
              - bel
              - graphml
              - sif
              - csv
              - gsea
    """
    graph = get_graph_from_request(query_id)
    return serve_network(graph, serve_format=serve_format)


@api_blueprint.route('/api/query/<int:query_id>/relabel')
def get_network(query_id):
    """Builds a graph from the given network id and sends it (relabeled) for the explorer

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """
    graph = get_graph_from_request(query_id)
    payload = to_json_custom(graph)
    return jsonify(payload)


@api_blueprint.route('/api/query/<int:query_id>/paths/<source_id>/<target_id>/')
def get_paths(query_id, source_id, target_id):
    """Returns array of shortest/all paths given a source node and target node both belonging in the graph

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer

      - name: source_id
        in: path
        description: The identifier of the source node
        required: true
        type: integer

      - name: target_id
        in: path
        description: The identifier of the target node
        required: true
        type: integer

      - name: cutoff
        in: query
        description: The largest path length to keep
        required: true
        type: integer

      - name: undirected

      - name: paths_method
        in: path
        description: The method by which paths are generated - either just the shortest path, or all paths
        required: false
        default: shortest
        schema:
            type: string
            enum:
              - all
              - shortest
    """
    source = manager.get_node_by_hash(source_id)
    if source is None:
        raise IndexError('Source missing from cache: %s', source_id)
    source = source.to_tuple()

    target = manager.get_node_by_hash(target_id)
    if target is None:
        raise IndexError('target is missing from cache: %s', target_id)
    target = target.to_tuple()

    network = get_graph_from_request(query_id)
    method = request.args.get(PATHS_METHOD)
    undirected = UNDIRECTED in request.args
    remove_pathologies = PATHOLOGY_FILTER in request.args
    cutoff = request.args.get('cutoff', default=7, type=int)

    if source not in network or target not in network:
        log.info('Source/target node not in network')
        log.info('Nodes in network: %s', network.nodes())
        abort(500, 'Source/target node not in network')

    if undirected:
        network = network.to_undirected()

    if remove_pathologies:
        network = get_subgraph_by_node_filter(network, exclude_pathology_filter)

    if method == 'all':
        paths = nx.all_simple_paths(network, source=source, target=target, cutoff=cutoff)
        return jsonify([
            [
                hash_node(node)
                for node in path
            ]
            for path in paths
        ])

    try:
        shortest_path = nx.shortest_path(network, source=source, target=target)
    except nx.NetworkXNoPath:
        log.debug('No paths between: {} and {}'.format(source, target))

        # Returns normal message if it is not a random call from graph_controller.js
        if RANDOM_PATH not in request.args:
            return 'No paths between the selected nodes'

        # In case the random node is an isolated one, returns it alone
        if not network.neighbors(source)[0]:
            return jsonify([source])

        shortest_path = nx.shortest_path(network, source=source, target=network.neighbors(source)[0])

    return jsonify([
        hash_node(node)
        for node in shortest_path
    ])


@api_blueprint.route('/api/query/<int:query_id>/paths/random')
def get_random_paths(query_id):
    """Gets random paths given the query identifier

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """
    network = get_graph_from_request(query_id)

    network = network.to_undirected()

    nodes = network.nodes()

    def pick_random_pair():
        return random.choices(nodes, k=2)

    source, target = pick_random_pair()

    tries = 0
    sentinel_tries = 5
    while not nx.has_path(network, source, target) and tries < sentinel_tries:
        tries += 1
        source, target = pick_random_pair()

    if tries == sentinel_tries:
        return source

    shortest_path = nx.shortest_path(network, source=source, target=target)

    return jsonify([
        hash_node(node)
        for node in shortest_path
    ])


@api_blueprint.route('/api/query/<int:query_id>/centrality/<int:node_number>')
def get_nodes_by_betweenness_centrality(query_id, node_number):
    """Gets a list of nodes with the top betweenness-centrality

    ---
    tags:
        - query

    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
      - name: node_number
        in: path
        description: The number of top between-nodes to return
        required: true
        type: integer
    """
    graph = get_graph_from_request(query_id)

    if node_number > graph.number_of_nodes():
        node_number = graph.number_of_nodes()

    bw_dict = nx.betweenness_centrality(graph)

    return jsonify([
        hash_node(node)
        for node, score in sorted(bw_dict.items(), key=itemgetter(1), reverse=True)[:node_number]
    ])


@api_blueprint.route('/api/query/<int:query_id>/pmids/')
def get_all_pmids(query_id):
    """Gets a list of all PubMed identifiers in the network produced by the given URL parameters

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """
    graph = get_graph_from_request(query_id)
    return jsonify(sorted(get_pubmed_identifiers(graph)))


@api_blueprint.route('/api/query/<int:query_id>/summarize')
def get_query_summary(query_id):
    """Gets a summary of the results from a given query

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """
    rv = {
        'query': query_id
    }

    network = get_graph_from_request(query_id)

    # TODO: @choyt check if this is the best way to check if the network is empty
    if network.nodes():
        rv['status'] = True
        rv['payload'] = info_json(network)
    else:
        rv['status'] = False

    return jsonify(rv)


####################################
# CITATIONS
####################################


@api_blueprint.route('/api/citation')
def list_citations():
    """Gets all citations

    ---
    tags:
        - citation
    """
    return jsonify([
        citation.to_json(include_id=True)
        for citation in manager.session.query(Citation).all()
    ])


@api_blueprint.route('/api/author/<author>/citations')
def list_citations_by_author(author):
    """Gets all citations from the given author

    ---
    tags:
      - author
    parameters:
      - name: author
        in: path
        description: An author name
        required: true
        type: string
    """
    author = manager.session.query(Author).filter(Author.name == author)

    return jsonify([
        citation.to_json(include_id=True)
        for citation in author.citations
    ])


@api_blueprint.route('/api/citation/pubmed/suggestion/')
def get_pubmed_suggestion():
    """Return list of PubMed identifiers matching the integer keyword

    ---
    tags:
        - citation
    parameters:
      - name: q
        in: query
        description: The search term
        required: true
        type: string
    """
    q = request.args.get('q')

    if not q:
        return jsonify([])

    citations = manager.session.query(Citation).filter(Citation.type == 'PubMed', Citation.reference.startswith(q))

    return jsonify([
        {
            "text": citation.reference,
            "id": citation.id
        }
        for citation in citations
    ])


####################################
# AUTHOR
####################################

@api_blueprint.route('/api/query/<int:query_id>/authors')
def get_all_authors(query_id):
    """Gets a list of all authors in the graph produced by the given URL parameters

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database query identifier
        required: true
        type: integer
    """
    graph = get_graph_from_request(query_id)
    return jsonify(sorted(get_authors(graph)))


@api_blueprint.route('/api/author/suggestion/')
def suggest_authors():
    """Return list of authors matching the author keyword

    ---
    tags:
        - author
    parameters:
      - name: q
        in: query
        description: The search term
        required: true
        type: string
    """
    q = request.args.get('q')

    if not q:
        return jsonify([])

    authors = manager.session.query(Author).filter(Author.name.contains(q)).all()

    return jsonify([
        {
            "id": author.id,
            "text": author.name,
        }
        for author in authors
    ])


####################################
# EDGES
####################################

@api_blueprint.route('/api/edge')
@roles_required('admin')
def get_edges():
    """Gets all edges

    ---
    tags:
        - edge
    parameters:
      - name: limit
        in: query
        description: The number of edges to return
        required: false
        type: integer
      - name: offset
        in: query
        description: The number of edges to return
        required: false
        type: integer
    """
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int)

    bq = manager.session.query(Edge)

    if limit:
        bq = bq.limit(limit)

    if offset:
        bq = bq.offset(offset)

    return jsonify([
        help_get_edge_entry(manager, edge)
        for edge in bq.all()
    ])


@api_blueprint.route('/api/edge/drop')
@roles_required('admin')
def drop_edges():
    """Drops all edges

    ---
    tags:
        - edge
    """
    log.warning('dropping all edges')
    manager.drop_edges()
    return next_or_jsonify('dropped all edges')


@api_blueprint.route('/api/edge/by_bel/statement/<bel>')
def get_edges_by_bel(bel):
    """Get edges that match the given BEL

    ---
    tags:
        - edge
    parameters:
      - name: bel
        in: path
        description: A BEL statement
        required: true
        type: string
    """
    edges = manager.query_edges(bel=bel)
    return jsonify(edges)


@api_blueprint.route('/api/edge/by_bel/source/<source_bel>')
def get_edges_by_source_bel(source_bel):
    """Get edges whose sources match the given BEL

    ---
    tags:
      - edge
    parameters:
      - name: source_bel
        in: path
        description: A BEL term
        required: true
        type: string
    """
    edges = manager.query_edges(source=source_bel)
    return jsonify(edges)


@api_blueprint.route('/api/edge/by_bel/target/<target_bel>')
def get_edges_by_target_bel(target_bel):
    """Gets edges whose targets match the given BEL

    ---
    tags:
      - edge
    parameters:
      - name: target_bel
        in: path
        description: A BEL term
        required: true
        type: string
    """
    edges = manager.query_edges(target=target_bel)
    return jsonify(edges)


@api_blueprint.route('/api/citation/pubmed/<pubmed_identifier>/edges')
def get_edges_by_pubmed(pubmed_identifier):
    """Gets edges that have a given PubMed identifier

    ---
    tags:
      - citation
    parameters:
      - name: pubmed_identifier
        in: path
        description: A NCBI PubMed identifier
        required: true
        type: string
    """
    edges = manager.query_edges(citation=pubmed_identifier)
    return jsonify(edges)


@api_blueprint.route('/api/author/<author>/edges')
def get_edges_by_author(author):
    """Gets edges with a given author

    ---
    tags:
      - author
    parameters:
      - name: author
        in: path
        description: An author name
        required: true
        type: string
    """
    citations = manager.query_citations(author=author)
    edges = manager.query_edges(citation=citations)
    return jsonify(edges)


@api_blueprint.route('/api/annotation/<annotation>/value/<value>/edges')
def get_edges_by_annotation(annotation, value):
    """Gets edges with the given annotation/value combination

    ---
    tags:
      - annotation
    parameters:
      - name: annotation
        in: path
        description: An annotation keyword
        required: true
        type: string
    parameters:
      - name: value
        in: path
        description: An entry in the given annotation
        required: true
        type: string
    """
    edges = manager.query_edges(annotations={annotation: value})
    return jsonify(edges)


@api_blueprint.route('/api/edge/<edge_hash>')
def get_edge_by_hash(edge_hash):
    """Gets an edge data dictionary by hash

    ---
    tags:
        - edge
    parameters:
      - name: edge_hash
        in: path
        description: The PyBEL hash of an edge
        required: true
        type: string
    """
    edge = get_edge_by_hash_or_404(edge_hash)
    return jsonify(help_get_edge_entry(manager, edge))


@api_blueprint.route('/api/edge/hash_starts/<edge_hash>')
@roles_required('admin')
def search_edge_by_hash(edge_hash):
    """Gets an edge data dictionary by the beginning of its hash

    ---
    tags:
        - edge
    parameters:
      - name: edge_hash
        in: path
        description: The PyBEL hash of an edge
        required: true
        type: string
    """
    edges = manager.session.query(Edge).filter(Edge.sha512.startswith(edge_hash))

    return jsonify([
        edge.to_json(include_id=True)
        for edge in edges
    ])


@api_blueprint.route('/api/edge/<edge_hash>/vote/up')
@login_required
def store_up_vote(edge_hash):
    """Up votes an edge

    ---
    tags:
      - edge
    parameters:
      - name: edge_hash
        in: path
        description: The PyBEL hash of an edge
        required: true
        type: string
    """
    edge = get_edge_by_hash_or_404(edge_hash)
    vote = get_or_create_vote(manager, edge, current_user, True)
    return jsonify(vote.to_json())


@api_blueprint.route('/api/edge/<edge_hash>/vote/down')
@login_required
def store_down_vote(edge_hash):
    """Down votes an edge

    ---
    tags:
      - edge
    parameters:
      - name: edge_hash
        in: path
        description: The PyBEL hash of an edge
        required: true
        type: string
    """
    edge = get_edge_by_hash_or_404(edge_hash)
    vote = get_or_create_vote(manager, edge, current_user, False)
    return jsonify(vote.to_json())


@api_blueprint.route('/api/edge/<edge_hash>/comment', methods=('GET', 'POST'))
@login_required
def store_comment(edge_hash):
    """Adds a comment to the edge

    ---
    tags:
      - edge
    parameters:
      - name: edge_hash
        in: path
        description: The PyBEL hash of an edge
        required: true
        type: string
    """
    edge = get_edge_by_hash_or_404(edge_hash)

    comment = request.args.get('comment')

    if comment is None:
        abort(403, 'Comment not found')  # FIXME put correct code

    comment = EdgeComment(
        user=current_user,
        edge=edge,
        comment=comment
    )

    manager.session.add(comment)
    manager.session.commit()

    return jsonify(comment.to_json())


####################################
# NODES
####################################

def jsonify_nodes(nodes):
    return jsonify([
        node.to_json(include_id=True)
        for node in nodes
    ])


@api_blueprint.route('/api/node/')
@roles_required('admin')
def get_nodes():
    """Gets all nodes

    ---
    tags:
        - node
    parameters:
      - name: limit
        in: query
        description: The number of edges to return
        required: false
        type: integer
      - name: offset
        in: query
        description: The number of edges to return
        required: false
        type: integer
    """
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int)

    bq = manager.session.query(Node)

    if limit:
        bq = bq.limit(limit)

    if offset:
        bq = bq.offset(offset)

    return jsonify_nodes(bq)


@api_blueprint.route('/api/node/drop')
@roles_required('admin')
def drop_nodes():
    """Drops all nodes

    ---
    tags:
        - node
    """
    log.warning('dropping all nodes')
    manager.session.query(Node).delete()
    manager.session.commit()
    return next_or_jsonify('Dropped all nodes')


@api_blueprint.route('/api/node/<node_hash>')
def get_node_by_hash(node_hash):
    """Gets a node

    :param node_hash: A PyBEL node hash

    ---
    tags:
        - node
    parameters:
      - name: node_hash
        in: path
        description: The PyBEL hash of a node
        required: true
        type: string
    """
    node = get_node_by_hash_or_404(node_hash)

    rv = node.to_json()

    rv = enrich_node_json(rv)

    return jsonify(rv)


@api_blueprint.route('/api/node/<node_hash>/drop')
def drop_node(node_hash):
    """Drops a node

    :param node_hash: A PyBEL node hash

    ---
    tags:
        - node
    parameters:
      - name: node_hash
        in: path
        description: The PyBEL hash of a node
        required: true
        type: string
    """
    node = get_node_by_hash_or_404(node_hash)
    manager.session.delete(node)
    manager.session.commit()
    return next_or_jsonify('Dropped node: {}'.format(node.bel))


@api_blueprint.route('/api/node/by_bel/<bel>')
def nodes_by_bel(bel):
    """Gets all nodes that match the given BEL

    ---
    tags:
        - node
    """
    nodes = manager.query_nodes(bel=bel)
    return jsonify_nodes(nodes)


@api_blueprint.route('/api/node/by_name/<name>')
def nodes_by_name(name):
    """Gets all nodes with the given name

    ---
    tags:
        - node
    """
    nodes = manager.query_nodes(name=name)
    return jsonify_nodes(nodes)


@api_blueprint.route('/api/namespace/<namespace>/nodes')
def nodes_by_namespace(namespace):
    """Gets all nodes with identifiers from the given namespace

    ---
    tags:
        - namespace
    """
    nodes = manager.query_nodes(namespace=namespace)
    return jsonify_nodes(nodes)


@api_blueprint.route('/api/namespace/<namespace>/name/<name>/nodes')
def nodes_by_namespace_name(namespace, name):
    """Gets all nodes with the given namespace and name

    ---
    tags:
        - namespace
    """
    nodes = manager.query_nodes(namespace=namespace, name=name)
    return jsonify_nodes(nodes)


@api_blueprint.route('/api/node')
@roles_required('admin')
def get_all_nodes():
    """Gets all nodes

    ---
    tags:
        - node
    """
    return jsonify([
        node.to_json(include_id=True)
        for node in manager.session.query(Node).all()
    ])


def enrich_node_json(node_data):
    """Enrich the node data with some of the Bio2BEL managers

    :param dict node_data:
    :rtype: dict
    """
    if NAMESPACE not in node_data:
        return

    namespace = node_data[NAMESPACE]
    name = node_data[NAME]
    node_data['annotations'] = {}

    if namespace == 'HGNC' and hgnc_manager:
        model = hgnc_manager.get_gene_by_hgnc_symbol(name)
        node_data['annotations']['HGNC'] = model.to_dict()

    elif namespace == 'CHEBI' and chebi_manager:
        model = chebi_manager.get_chemical_by_chebi_name(name)
        node_data['annotations']['CHEBI'] = model.to_json()

    elif namespace == 'RGD':
        pass

    elif namespace == 'MGI':
        pass

    return node_data


@api_blueprint.route('/api/node/suggestion/')
def get_node_suggestion():
    """Suggests a node

    ---
    tags:
        - node
    parameters:
      - name: q
        in: query
        description: The search term
        required: true
        type: string
    """
    q = request.args.get('q')

    if not q:
        return jsonify([])

    nodes = manager.session.query(Node).filter(Node.bel.contains(q)).order_by(func.length(Node.bel))

    return jsonify([
        {
            "text": node.bel,
            "id": node.sha512
        }
        for node in nodes
    ])


####################################
# PIPELINE
####################################

@api_blueprint.route('/api/pipeline/suggestion/')
def get_pipeline_function_names():
    """Sends a list of functions to use in the pipeline"""
    q = request.args.get('q')

    if not q:
        return jsonify([])

    q = q.casefold()

    return jsonify([
        p.replace("_", " ").capitalize()
        for p in pipeline.no_arguments_map
        if q in p.replace("_", " ").casefold()
    ])


@api_blueprint.route('/api/query/<int:query_id>/drop')
@login_required
def drop_query_by_id(query_id):
    """Drops a query

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
    """
    query = safe_get_query(query_id)

    manager.session.delete(query)
    manager.session.commit()

    return next_or_jsonify('Dropped query #{}'.format(query_id))


@api_blueprint.route('/api/query/drop')
@roles_required('admin')
def drop_queries():
    """Drops all queries

    ---
    tags:
        - query
    """
    manager.session.query(models.Query).delete()
    manager.session.commit()

    return next_or_jsonify('Dropped all queries')


@api_blueprint.route('/api/user/<int:user_id>/drop-queries/')
@login_required
def drop_user_queries(user_id):
    """Drops all queries associated with the user

    ---
    tags:
      - query
      - user
    parameters:
      - name: user_id
        in: path
        description: The database identifier of a user
        required: true
        type: integer
    """
    if not (current_user.is_admin or user_id == current_user.id):
        abort(403, 'Unauthorized user')

    manager.session.query(models.Query).filter(models.Query.user_id == user_id).delete()
    manager.session.commit()

    return next_or_jsonify('Dropped all queries associated with {}'.format(current_user))


@api_blueprint.route('/api/query/<int:query_id>/info')
def query_to_network(query_id):
    """Returns info from a given query identifier

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
    """
    query = safe_get_query(query_id)

    rv = query.data.to_json()
    rv['id'] = query.id

    if query.user:
        rv['creator'] = str(query.user)

    network_ids = rv['network_ids']
    rv['networks'] = [
        '{} v{}'.format(name, version)
        for name, version in manager.session.query(Network.name, Network.version).filter(Network.id.in_(network_ids))
    ]

    return jsonify(rv)


@api_blueprint.route('/api/query/<int:query_id>/parent')
def get_query_parent(query_id):
    """Returns the parent of the query

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
    """
    query = safe_get_query(query_id)

    if not query.parent:
        return jsonify({
            'id': query.id,
            'parent': False
        })

    return jsonify({
        'id': query.parent.id,
        'parent': True
    })


@api_blueprint.route('/api/query/<int:query_id>/ancestor')
def get_query_oldest_ancestry(query_id):
    """Returns the parent of the query

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
    """
    query = safe_get_query(query_id)

    ancestor_id = get_query_ancestor_id(query.id)

    return jsonify({
        'id': ancestor_id,
        'parent': bool(query.parent)
    })


def add_pipeline_entry(query_id, name, *args, **kwargs):
    """Adds an entry to the pipeline

    :param int query_id: The identifier of the query
    :param str name: The name of the function to append
    """
    query = safe_get_query(query_id)
    qo = query.build_appended(name, *args, **kwargs)

    if current_user.is_authenticated:
        qo.user = current_user

    manager.session.add(qo)
    manager.session.commit()

    return jsonify({
        'status': 200,
        'id': qo.id,
    })


@api_blueprint.route('/api/query/<int:query_id>/isolated_node/<node_hash>')
def get_query_from_isolated_node(query_id, node_hash):
    """Creates a query with a single node hash

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
      - name: node_hash
        in: path
        description: The PyBEL hash of a node
        required: true
        type: string
    """
    parent_query = safe_get_query(query_id)
    node = manager.get_node_tuple_by_hash(node_hash)

    child_query = Query(network_ids=[
        network.id
        for network in parent_query.assembly.networks
    ])
    child_query.append_seeding_induction([node])

    child_query_model = models.Query(
        assembly=parent_query.assembly,
        seeding=child_query.seeding_to_jsons(),
        pipeline_protocol=child_query.pipeline.to_jsons(),
        parent_id=parent_query.id,
    )

    if current_user.is_authenticated:
        child_query_model.user = current_user

    manager.session.add(child_query_model)
    manager.session.commit()

    return jsonify(child_query_model.to_json())


@api_blueprint.route('/api/query/<int:query_id>/add_applier/<name>')
def add_applier_to_query(query_id, name):
    """Builds a new query with the applier in the url and adds it to the end of the pipeline

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
      - name: name
        in: path
        description: The name of the function to apply
        required: true
        type: string
    """
    return add_pipeline_entry(query_id, name)


@api_blueprint.route('/api/query/<int:query_id>/add_node_list_applier/<name>/<node_hashes>')
def add_node_list_applier_to_query(query_id, name, node_hashes):
    """Builds a new query with a node list applier added to the end of the pipeline

    :param int query_id: A query's database identifier
    :param str name: The name of the function to apply at the end of the query
    :param list[str] node_hashes: The node identifiers to use as the argument to the function

    ---
    tags:
        - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
      - name: name
        in: path
        description: The name of the function to apply
        required: true
        type: string
      - name: node_hashes
        in: path
        description: A list of comma-separated PyBEL node hashes
        required: true
        type: string
    """
    return add_pipeline_entry(query_id, name, node_hashes)


@api_blueprint.route('/api/query/<int:query_id>/add_node_applier/<name>/<node_hash>')
def add_node_applier_to_query(query_id, name, node_hash):
    """Builds a new query with a node applier added to the end of the pipeline

    :param int query_id: A query's database identifier
    :param str name: The name of the function to apply at the end of the query
    :param int node_hash: The node identifier to use as the argument ot the function

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
      - name: name
        in: path
        description: The name of the function to apply
        required: true
        type: string
      - name: node_hash
        in: path
        description: The PyBEL hash of a node
        required: true
        type: string
    """
    return add_pipeline_entry(query_id, name, node_hash)


@api_blueprint.route('/api/query/<int:query_id>/add_annotation_filter/')
def add_annotation_filter_to_query(query_id):
    """Builds a new query with the annotation in the arguments. If 'and' is passed as an argument, it performs a AND
    query. By default it uses the OR condition.

    :param int query_id: A query's database identifier

    ---
    tags:
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
    """
    filters = {
        key: request.args.getlist(key)
        for key in request.args
        if key not in BLACK_LIST
    }

    if not filters:  # If no filters send back the same query
        return jsonify({
            'id': query_id
        })

    query_type = not request.args.get(AND)

    return add_pipeline_entry(query_id, get_subgraph_by_annotations, filters, query_type)


####################################
# USER
####################################

@api_blueprint.route('/api/user/count')
def get_number_users():
    """Return the number of users"""
    count = manager.session.query(func.count(User.id)).scalar()
    return jsonify({
        'time': str(time.asctime()),
        'count': count
    })


@api_blueprint.route('/api/user')
@roles_required('admin')
def get_all_users():
    """Returns all users

    ---
    tags:
        - user
    """
    return jsonify([
        user.to_json(include_id=True)
        for user in manager.session.query(User).all()
    ])


@api_blueprint.route('/api/user/current')
@login_required
def get_current_user():
    """Returns the current user

    ---
    tags:
        - user
    """
    return jsonify(current_user.to_json())


@api_blueprint.route('/api/user/<user>/add_role/<role>')
@roles_required('admin')
def add_user_role(user, role):
    """Adds a role to a use

    ---
    tags:
        - user
    """
    user_datastore.add_role_to_user(user, role)
    user_datastore.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/user/<user>/remove_role/<role>')
@roles_required('admin')
def drop_user_role(user, role):
    """Removes a role from a user

    ---
    tags:
        - user
    """
    user_datastore.remove_role_from_user(user, role)
    user_datastore.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/user/<int:user_id>/drop')
@roles_required('admin')
def drop_user(user_id):
    """Drops a user

    ---
    tags:
        - user
    parameters:
      - name: user_id
        in: path
        description: The database identifier of a user
        required: true
        type: integer
    """
    user = User.query.get(user_id)

    if user is None:
        abort(404)

    user_datastore.delete_user(user)
    user_datastore.commit()

    return next_or_jsonify(
        'Dropped user: {}'.format(user),
        user={
            'id': user.id,
            'email': user.email
        }
    )


####################################
# Analysis
####################################

def get_experiment_or_404(experiment_id):
    experiment = manager.session.query(Experiment).get(experiment_id)

    if experiment is None:
        abort(404, 'Experiment {} does not exist'.format(experiment_id))

    return experiment


@api_blueprint.route('/api/query/<int:query_id>/analysis/<int:experiment_id>/')
def get_analysis(query_id, experiment_id):
    """Returns data from analysis

    ---
    tags:
      - experiment
      - query
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
      - name: experiment_id
        in: path
        description: The database identifier of an experiment
        required: true
        type: integer
    """
    graph = get_graph_from_request(query_id)
    experiment = get_experiment_or_404(experiment_id)

    data = pickle.loads(experiment.result)
    results = [
        {
            'node': hash_node(node),
            'data': data[node]
        }
        for node in graph
        if node in data
    ]

    return jsonify(results)


@api_blueprint.route('/api/query/<int:query_id>/analysis/<int:experiment_id>/median')
def get_analysis_median(query_id, experiment_id):
    """Returns data from analysis

    ---
    tags:
      - query
      - experiment
    parameters:
      - name: query_id
        in: path
        description: The database identifier of a query
        required: true
        type: integer
      - name: experiment_id
        in: path
        description: The database identifier of an experiment
        required: true
        type: integer
    """
    graph = get_graph_from_request(query_id)
    experiment = get_experiment_or_404(experiment_id)

    data = pickle.loads(experiment.result)
    # position 3 is the 'median' score
    results = {
        hash_node(node): data[node][3]
        for node in graph
        if node in data
    }

    return jsonify(results)


@api_blueprint.route('/api/experiment/<int:experiment_id>/drop')
@login_required
def drop_experiment_by_id(experiment_id):
    """Drops an experiment

    ---
    tags:
      - experiment
    parameters:
      - name: experiment_id
        in: path
        description: The identifier of the experiment
        required: true
        type: integer
        format: int32
    """
    experiment = get_experiment_or_404(experiment_id)

    if not current_user.is_admin and (current_user != experiment.user):
        abort(403)

    manager.session.delete(experiment)
    manager.session.commit()

    return next_or_jsonify(
        'Dropped Experiment #{}'.format(experiment.id),
        experiment={
            'id': experiment.id,
            'description': experiment.description
        }
    )


@api_blueprint.route('/api/experiment/<int:experiment_id>/download')
@login_required
def download_analysis(experiment_id):
    """Downloads data from a given experiment as a CSV

    ---
    tags:
        - experiment
    parameters:
      - name: experiment_id
        in: path
        description: The identifier of the experiment
        required: true
        type: integer
        format: int32
    responses:
      200:
        description: A CSV document with the results in it
    """
    experiment = get_experiment_or_404(experiment_id)

    if not current_user.is_admin and (current_user != experiment.user):
        abort(403)

    si = StringIO()
    cw = csv.writer(si)
    csv_list = [('Namespace', 'Name') + tuple(RESULT_LABELS)]
    experiment_data = pickle.loads(experiment.result)
    csv_list.extend(
        (namespace, name) + tuple(values)
        for (_, namespace, name), values in experiment_data.items()
    )
    cw.writerows(csv_list)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=cmpa_{}.csv".format(experiment_id)
    output.headers["Content-type"] = "text/csv"
    return output


####################################
# RIGHTS MANAGEMENT
####################################


@api_blueprint.route('/api/network/<int:network_id>/grant_project/<int:project_id>')
@login_required
def grant_network_to_project(network_id, project_id):
    """Adds rights to a network to a project

    ---
    tags:
        - network
    parameters:
      - name: network_id
        in: path
        description: The database identifier of a network
        required: true
        type: integer
        format: int32
      - name: project_id
        in: path
        description: The identifier of a project
        required: true
        type: integer
        format: int32
    """
    network = safe_get_network(network_id)
    project = safe_get_project(project_id)
    project.networks.append(network)

    manager.session.commit()

    return next_or_jsonify(
        'Added rights for {} to {}'.format(network, project),
        network={
            'id': network.id,
        }
    )


@api_blueprint.route('/api/network/<int:network_id>/grant_user/<int:user_id>')
@login_required
def grant_network_to_user(network_id, user_id):
    """Adds rights to a network to a user

    ---
    tags:
        - network
        - user
    parameters:
      - name: network_id
        in: path
        description: The identifier of a network
        required: true
        type: integer
        format: int32
      - name: user_id
        in: path
        description: The identifier of a user
        required: true
        type: integer
        format: int32
    """
    network = safe_get_network(network_id)

    user = manager.session.query(User).get(user_id)
    user.networks.append(network)

    manager.session.commit()

    return next_or_jsonify('Added rights for {} to {}'.format(network, user))


def safe_get_graph(network_id):
    """Gets the network as a BEL graph or aborts if the user is not the owner

    :type network_id: int
    :rtype: pybel.BELGraph
    """
    network = safe_get_network(network_id)
    return network.as_bel()


@api_blueprint.route('/api/project')
@roles_required('admin')
def get_all_projects():
    """Returns all project as a JSON file

    ---
    tags:
        - project
    """
    return jsonify([
        project.to_json(include_id=True)
        for project in manager.session.query(Project).all()
    ])


@api_blueprint.route('/api/project/<int:project_id>')
@login_required
def get_project_metadata(project_id):
    """Returns the project as a JSON file

    ---
    tags:
        - project
    parameters:
      - name: project_id
        in: path
        description: The identifier of a project
        required: true
        type: integer
        format: int32
    """
    project = safe_get_project(project_id)

    return jsonify(**project.to_json())


@api_blueprint.route('/api/project/<int:project_id>/drop')
@login_required
def drop_project_by_id(project_id):
    """Drops a given project from the database

    :param int project_id: THe project's database identifier

    ---
    tags:
        - project
    parameters:
      - name: project_id
        in: path
        description: The identifier of a project
        required: true
        type: integer
        format: int32
    """
    project = safe_get_project(project_id)

    # FIXME cascade on project/users

    manager.session.delete(project)
    manager.session.commit()

    return next_or_jsonify('Dropped project: {}'.format(project.name))


@api_blueprint.route('/api/project/<int:project_id>/summarize')
@login_required
def summarize_project(project_id):
    """Provides a summary of all networks in a project as a CSV file

    :param int project_id: The identifier of the project

    ---
    tags:
        - project
    parameters:
      - name: project_id
        in: path
        description: The identifier of a project
        required: true
        type: integer
        format: int32
    """
    project = safe_get_project(project_id)

    si = StringIO()
    cw = csv.writer(si)
    csv_list = [
        ('Name', 'Version', 'Nodes', 'Edges', 'Citations', 'Authors', 'Density', 'Components', 'AvgDegree', 'Warnings')]

    # TODO add all of these to the network's model or to the report
    for network in project.networks:
        csv_list_entry = network.name, network.version
        csv_list_entry += tuple(
            v
            for _, v in info_list(network.as_bel())
        )

        csv_list.append(csv_list_entry)

    csv_list.append(('Total', '') + tuple(v for _, v in info_list(project.as_bel())))

    cw.writerows(csv_list)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}_summary.csv".format(project.name.replace(' ', '_'))
    output.headers["Content-type"] = "text/csv"
    return output


@api_blueprint.route('/api/project/<project_id>/export/<serve_format>')
@login_required
def export_project_network(project_id, serve_format):
    """Builds a graph the networks belonging to the given project and sends it in the given format

    ---
    tags:
        - project
    parameters:
      - name: project_id
        in: path
        description: The identifier of a project
        required: true
        type: integer
        format: int32

      - name: serve_format
        in: path
        description: The format of the network to return
        required: false
        schema:
            type: string
            enum:
              - json
              - cx
              - jgif
              - bytes
              - bel
              - graphml
              - sif
              - csv
              - gsea
    """
    project = safe_get_project(project_id)

    networks = [network.as_bel() for network in project.networks]

    network = union(networks)

    return serve_network(network, serve_format)


####################################
# METADATA
####################################


@api_blueprint.route('/api/meta/config')
@roles_required('admin')
def view_config():
    """Lists the application configuration"""
    return jsonify({
        key: str(value)
        for key, value in current_app.config.items()
    })


@api_blueprint.route('/api/meta/blacklist')
def get_blacklist():
    """Return list of blacklist constants"""
    return jsonify(sorted(BLACK_LIST))


@api_blueprint.route('/api/text/report')
def get_recent_report():
    """Gets the recent reports"""
    lines = get_recent_reports(manager)
    output = make_response('\n'.join(lines))
    output.headers["Content-type"] = "text/plain"
    return output


@api_blueprint.route('/api/network/overlap')
@roles_required('admin')
def list_all_network_overview():
    """Returns a meta-network describing the overlaps of all networks"""
    node_elements = []
    edge_elements = []

    for source_network in manager.list_networks():
        source_network_id = source_network.id
        source_bel_graph = manager.get_graph_by_id(source_network_id)
        overlap = get_node_overlaps(source_network_id)

        node_elements.append({
            'data': {
                'id': source_network_id,
                'name': source_network.name,
                'size': source_bel_graph.number_of_nodes()
            }
        })

        for target_network_id, weight in overlap.items():
            weight = int(100 * weight)

            if weight < 25:
                continue  # don't have a complete graph

            if source_network_id < target_network_id:
                continue  # no duplicates

            edge_elements.append({
                'data': {
                    'id': 'edge{}'.format(len(edge_elements)),
                    'source': source_network_id,
                    'target': target_network_id,
                    'weight': weight
                }
            })

    return jsonify(node_elements + edge_elements)


@api_blueprint.route('/api/network/overview')
@roles_required('admin')
def universe_summary():
    """Renders the graph summary page"""

    chart_data = {
        'networks': manager.count_networks(),
        'nodes': manager.count_nodes(),
        'edges': manager.count_edges(),
        'namespaces': manager.count_namespaces(),
        'annotations': manager.count_annotations(),
        # TODO count variants, transformations, modifications, degradation, etc
    }

    return jsonify(**chart_data)
