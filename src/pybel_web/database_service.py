# -*- coding: utf-8 -*-

"""This module runs the database-backed PyBEL API"""

import csv
import json
import logging
import pickle
import time

import flask
import networkx as nx
from flask import (
    Blueprint,
    make_response,
    flash,
    current_app,
    jsonify,
    redirect,
    request,
    abort,
)
from flask_security import roles_required, login_required, current_user
from functools import lru_cache
from operator import itemgetter
from six import StringIO
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

import pybel
from pybel.constants import (
    METADATA_AUTHORS,
    METADATA_CONTACT,
    METADATA_NAME,
)
from pybel.manager.models import (
    Namespace,
    Annotation,
    Network,
)
from pybel_tools import pipeline
from pybel_tools.analysis.cmpa import RESULT_LABELS
from pybel_tools.definition_utils import write_namespace, write_annotation
from pybel_tools.filters.node_filters import exclude_pathology_filter
from pybel_tools.query import Query
from pybel_tools.selection import get_subgraph_by_annotations, get_subgraph_by_node_filter
from pybel_tools.summary import (
    count_functions,
    count_relations,
    get_translocated,
    get_degradations,
    get_activities,
    count_namespaces,
    info_json,
    info_list,
    get_authors,
    get_pubmed_identifiers,
    get_undefined_namespace_names,
    get_incorrect_names_by_namespace,
    get_naked_names,
    count_citation_years,
    count_variants,
)
from . import models
from .constants import *
from .main_service import (
    PATHS_METHOD,
    UNDIRECTED,
    BLACK_LIST
)
from .models import (
    Report,
    User,
    Experiment,
    Project,
    EdgeComment,
)
from .send_utils import serve_network
from .utils import (
    get_recent_reports,
    manager,
    api,
    user_datastore,
    get_query_ancestor_id,
    get_network_ids_with_permission_helper,
    user_has_query_rights,
    current_user_has_query_rights,
    safe_get_query,
    get_or_create_vote,
    next_or_jsonify,
    user_owns_network_or_403,
)

log = logging.getLogger(__name__)

api_blueprint = Blueprint('dbs', __name__)


@lru_cache(maxsize=32)
def get_network_from_request(query_id):
    """Process the GET request returning the filtered network

    :param int query_id: Query id
    :return: A BEL graph
    :rtype: pybel.BELGraph
    """
    query = safe_get_query(query_id)
    return query.run(api)


@api_blueprint.route('/api/receive', methods=['POST'])
def receive():
    """Receives a JSON serialized BEL graph"""
    try:
        network = pybel.from_json(request.get_json())
    except Exception as e:
        if 'next' in request.args:
            flask.flash('Error parsing json')
            return redirect(request.args['next'])

        return jsonify({
            'status': '400',
            'exception': str(e),
        })

    try:
        network = manager.insert_graph(network)
        flask.flash('Success uploading {}'.format(network))
    except IntegrityError:
        flask.flash(integrity_message.format(network.name, network.version))
        manager.session.rollback()
    except:
        flask.flash("Error storing in database")
        log.exception('Upload error')
        manager.session.rollback()

    return next_or_jsonify('Success', network_id=network.id)


####################################
# NAMESPACE
####################################

@api_blueprint.route('/api/namespaces', methods=['GET'])
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


@api_blueprint.route('/api/namespace/<keyword>', methods=['GET'])
def list_names(keyword):
    """Lists all names from a given namespace, by keyword

    ---
    tags:
        - namespace
    parameters:
      - name: keyword
        in: path
        description: The namespace keyword
        required: true
        type: integer
    """
    names = api.query_namespaces(name_list=True, keyword=keyword)
    return jsonify(names)


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
        namespace_domain='Other',
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
    """
    graph = api.get_graph_by_id(network_id)
    names = get_undefined_namespace_names(graph, namespace)
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
    """
    graph = api.get_graph_by_id(network_id)
    names = get_incorrect_names_by_namespace(graph, namespace)
    return _build_namespace_helper(graph, namespace, names)


@api_blueprint.route('/api/network/<int:network_id>/builder/namespace/naked')
def download_naked_names(network_id):
    """Outputs a namespace built from the naked names in the given namespace

    ---
    tags:
        - network
    """
    graph = api.get_graph_by_id(network_id)
    names = get_naked_names(graph)
    return _build_namespace_helper(graph, 'NAKED', names)


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
    """
    graph = api.get_graph_by_id(network_id)

    if annotation not in graph.annotation_list:
        abort(400, 'Graph does not contain this list annotation')

    # Convert to dict with no labels
    values = {
        value: ''
        for value in graph.annotation_list[annotation]
    }

    si = StringIO()

    write_annotation(
        keyword=annotation,
        values=values,
        author_name=graph.document.get(METADATA_AUTHORS),
        author_contact=graph.document.get(METADATA_CONTACT),
        citation_name=graph.document.get(METADATA_NAME),
        description='This annotation was serialize by PyBEL Web',
        file=si,
    )

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}.belanno".format(annotation)
    output.headers["Content-type"] = "text/plain"
    return output


####################################
# ANNOTATIONS
####################################

@api_blueprint.route('/api/annotation', methods=['GET'])
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


@api_blueprint.route('/api/annotation/<keyword>', methods=['GET'])
def list_annotation_names(keyword):
    """Lists the values in an annotation, by keyword

    ---
    tags:
        - annotation
    """
    values = api.query_annotations(name_list=True, keyword=keyword)
    return jsonify(values)


@api_blueprint.route('/api/annotation/<annotation_id>/drop')
@roles_required('admin')
def drop_annotation_by_id(annotation_id):
    """Drops an annotation given its identifier

    ---
    tags:
        - annotation
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
    """
    if not request.args['search']:
        return jsonify([])

    autocompletion_set = api.get_annotations_containing_keyword(request.args['search'])

    return jsonify(autocompletion_set)


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
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404)

    return jsonify(**network.to_json(include_id=True))


@api_blueprint.route('/api/network/<int:network_id>/namespaces', methods=['GET'])
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
    network_namespaces = api.query_namespaces(network_id=network_id)
    return jsonify(network_namespaces)


@api_blueprint.route('/api/network/<int:network_id>/annotations', methods=['GET'])
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
    network_annotations = api.query_annotations(network_id=network_id)
    return jsonify(network_annotations)


@api_blueprint.route('/api/network/<int:network_id>/citations', methods=['GET'])
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
    citations = api.query_citations(network_id=network_id)
    return jsonify(citations)


@api_blueprint.route('/api/network/<int:network_id>/edges', methods=['GET'])
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

      - name: offset_start
        in: query
        required: false
        type: integer
        default: 0
        description: The database offset start

      - name: offset_end
        in: query
        required: false
        type: integer
        default: 500
        description: The database offset end

    responses:
      200:
        description: The edges in the network
    """
    offset_start = request.args.get('offset_start', type=int)
    offset_end = request.args.get('offset_end', type=int)

    edges = api.query_edges(
        network_id=network_id,
        offset_start=offset_start,
        offset_end=offset_end,
    )
    return jsonify(edges)


@api_blueprint.route('/api/network/<int:network_id>/nodes/', methods=['GET'])
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
    nodes = api.query_nodes(network_id=network_id)
    return jsonify(nodes)


def drop_network_helper(network_id):
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404, 'Network {} does not exist'.format(network_id))

    if not current_user.is_admin:
        user_owns_network_or_403(network, current_user)

    try:
        manager.session.delete(network)
        manager.session.commit()

        api.forget_network(network_id)
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

    api.clear()

    return next_or_jsonify('Dropped all networks')


@api_blueprint.route('/api/network/<int:network_id>/claim')
@roles_required('admin')
def claim_network(network_id):
    """Adds a report for the given network

    :param int network_id: A network's database identifier

    ---
    tags:
        - network
    """
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404)

    if network.report:
        if 'next' in request.args:
            return next_or_jsonify(
                'Already claimed by {}'.format(network.report.user),
                network={'id': network.id},
                owner={'id': network.report.user.id},
            )

    report = Report(
        network=network,
        user=current_user
    )

    manager.session.add(report)
    manager.session.commit()

    return next_or_jsonify(
        'Claimed {}'.format(network),
        network={'id': network.id},
        owner={'id': current_user.id}
    )


@api_blueprint.route('/api/network', methods=['GET'])
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


@api_blueprint.route('/api/network/<int:network_id>/export/<serve_format>', methods=['GET'])
def export_network(network_id, serve_format):
    """Builds a graph from the given network id and sends it in the given format

    ---
    tags:
        - network
    """
    network_ids = get_network_ids_with_permission_helper(current_user, manager)

    if network_id not in network_ids:
        abort(403, 'You do not have permission to download the selected network')

    graph = api.get_graph_by_id(network_id)

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
    graph = api.get_graph_by_id(network_id)
    return jsonify(info_json(graph))


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
    if network_id == 0:
        return ''

    network = manager.get_network_by_id(network_id)
    return jsonify(network.name)


def update_network_status(network_id, status):
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404)

    if network.report is None:
        abort(400)

    if not current_user.is_admin or current_user.id != network.report.user_id:
        abort(403, 'You do not have permission to modify that network')

    network.report.public = status
    manager.session.commit()

    return next_or_jsonify(
        'Set public to {} for {}'.format(status, network),
        network_id=network_id,
        public=status,
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
    network = get_network_from_request(query_id)
    return jsonify(api.get_tree_annotations(network))


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


@api_blueprint.route('/api/query/<int:query_id>/export/<serve_format>', methods=['GET'])
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
    network = get_network_from_request(query_id)
    return serve_network(network, serve_format=serve_format)


@api_blueprint.route('/api/query/<int:query_id>/relabel', methods=['GET'])
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
    network = get_network_from_request(query_id)
    network = api.relabel_nodes_to_identifiers(network)
    return serve_network(network)


@api_blueprint.route('/api/query/<int:query_id>/paths/<int:source_id>/<int:target_id>/')
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

      - name: undirected

      - name: paths_method
    """
    network = get_network_from_request(query_id)

    method = request.args.get(PATHS_METHOD)

    undirected = UNDIRECTED in request.args

    remove_pathologies = PATHOLOGY_FILTER in request.args

    cutoff = request.args.get('cutoff', 7)

    source = api.get_node_tuple_by_hash(source_id)
    target = api.get_node_tuple_by_hash(target_id)

    log.info('Source: %s, target: %s', source, target)

    if source not in network or target not in network:
        log.info('Source/target node not in network')
        log.info('Nodes in network: %s', network.nodes())
        abort(500, 'Source/target node not in network')

    if undirected:
        network = network.to_undirected()

    if remove_pathologies:
        network = get_subgraph_by_node_filter(network, exclude_pathology_filter)

    if method == 'all':
        all_paths = nx.all_simple_paths(network, source=source, target=target, cutoff=cutoff)
        return jsonify(api.paths_tuples_to_ids(all_paths))

    try:
        shortest_path = nx.shortest_path(network, source=source, target=target)
    except nx.NetworkXNoPath:
        log.debug('No paths between: {} and {}'.format(source, target))
        return 'No paths between the selected nodes'

    return jsonify(api.get_node_hashes(shortest_path))


@api_blueprint.route('/api/query/<int:query_id>/centrality/<int:node_number>', methods=['GET'])
def get_nodes_by_betweenness_centrality(query_id, node_number):
    """Gets a list of nodes with the top betweenness-centrality

    ---
    tags:
        - query

    """
    network = get_network_from_request(query_id)

    if node_number > nx.number_of_nodes(network):
        return 'The number introduced is bigger than the nodes in the network'

    bw_dict = nx.betweenness_centrality(network)

    return jsonify([
        api.get_node_hash(node)
        for node, score in sorted(bw_dict.items(), key=itemgetter(1), reverse=True)[:node_number]
    ])


@api_blueprint.route('/api/query/<int:query_id>/pmids/')
def get_all_pmids(query_id):
    """Gets a list of all PubMed identifiers in the network produced by the given URL parameters

    ---
    tags:
        - query
    """
    network = get_network_from_request(query_id)
    return jsonify(sorted(get_pubmed_identifiers(network)))


@api_blueprint.route('/api/query/nodes/')
def get_node_hashes():
    """Gets the dictionary of {node id: pybel node tuples}

    ---
    tags:
        - node
    """
    return jsonify(api.nid_node)


@api_blueprint.route('/api/query/<int:query_id>/summarize')
def get_query_summary(query_id):
    """Gets a summary of the results from a given query

    ---
    tags:
        - query
    """
    network = get_network_from_request(query_id)
    return jsonify(info_json(network))


####################################
# CITATIONS
####################################


@api_blueprint.route('/api/citation', methods=['GET'])
def list_citations():
    """Gets all citations

    ---
    tags:
        - citation
    """
    citations = api.query_citations()
    return jsonify(citations)


@api_blueprint.route('/api/author/<author>/citations', methods=['GET'])
def list_citations_by_author(author):
    """Gets all citations from the given author

    ---
    tags:
        - author
    """
    citations = api.query_citations(author=author)
    return jsonify(citations)


@api_blueprint.route('/api/citation/pubmed/suggestion/')
def get_pubmed_suggestion():
    """Return list of PubMed identifiers matching the integer keyword

    ---
    tags:
        - citation
    """
    autocompletion_set = api.get_pubmed_containing_keyword(request.args['search'])

    return jsonify([
        {"text": pubmed_identifier, "id": index}
        for index, pubmed_identifier in enumerate(autocompletion_set)
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
    """
    network = get_network_from_request(query_id)
    return jsonify(sorted(get_authors(network)))


@api_blueprint.route('/api/author/suggestion/')
def get_author_suggestion():
    """Return list of authors matching the author keyword

    ---
    tags:
        - author
    """
    autocompletion_set = api.get_authors_containing_keyword(request.args['search'])

    return jsonify([
        {
            "id": index,
            "text": pubmed_identifier,
        }
        for index, pubmed_identifier in enumerate(autocompletion_set)
    ])


####################################
# EDGES
####################################

@api_blueprint.route('/api/edge/by_bel/statement/<statement_bel>', methods=['GET'])
def edges_by_bel_statement(statement_bel):
    """Get edges that match the given BEL

    ---
    tags:
        - edge
    """
    edges = api.query_edges(statement=statement_bel)
    return jsonify(edges)


@api_blueprint.route('/api/edge/by_bel/source/<source_bel>', methods=['GET'])
def edges_by_bel_source(source_bel):
    """Get edges whose sources match the given BEL

    ---
    tags:
        - edge
    """
    edges = api.query_edges(source=source_bel)
    return jsonify(edges)


@api_blueprint.route('/api/edge/by_bel/target/<target_bel>', methods=['GET'])
def edges_by_bel_target(target_bel):
    """Gets edges whose targets match the given BEL

    ---
    tags:
        - edge
    """
    edges = api.query_edges(target=target_bel)
    return jsonify(edges)


@api_blueprint.route('/api/citation/pubmed/<int:pmid>/edges', methods=['GET'])
def edges_by_pmid(pmid):
    """Gets edges that have a given PubMed identifier

    ---
    tags:
        - citation
    """
    edges = api.query_edges(pmid=pmid)
    return jsonify(edges)


@api_blueprint.route('/api/author/<author>/edges', methods=['GET'])
def edges_by_author(author):
    """Gets edges with a given author

    ---
    tags:
        - author
    """
    edges = api.query_edges(author=author)
    return jsonify(edges)


@api_blueprint.route('/api/annotation/<annotation>/value/<value>/edges', methods=['GET'])
def edges_by_annotation(annotation, value):
    """Gets edges with the given annotation/value combination

    ---
    tags:
        - annotation
    """
    edges = api.query_edges(annotations={annotation: value})
    return jsonify(edges)


def get_edge_entry(edge_hash):
    """Gets edge information by edge identifier

    :param int edge_hash: The identifier of a given edge
    :return: A dictionary representing the information about the given edge
    :rtype: dict
    """
    edge = manager.get_edge_by_hash(edge_hash)

    data = edge.to_json()

    data['comments'] = [
        {
            'user': {
                'id': ec.user_id,
                'email': ec.user.email
            },
            'comment': ec.comment,
            'created': ec.created,
        }
        for ec in manager.session.query(EdgeComment).filter(EdgeComment.edge == edge)
    ]

    if current_user.is_authenticated:
        vote = get_or_create_vote(edge, current_user)
        data['vote'] = 0 if (vote is None or vote.agreed is None) else 1 if vote.agreed else -1

    return data


@api_blueprint.route('/api/edge')
@roles_required('admin')
def get_all_edges():
    """Gets all edges

    ---
    tags:
        - edge
    """
    return jsonify([
        get_edge_entry(edge_id)
        for edge_id in api.eid_edge
    ])


@api_blueprint.route('/api/edge/<edge_id>')
def get_edge_by_id(edge_id):
    """Gets an edge data dictionary by id

    ---
    tags:
        - edge
    """
    return jsonify(get_edge_entry(edge_id))


@api_blueprint.route('/api/edge/<edge_id>/vote/up')
@login_required
def store_up_vote(edge_id):
    """Up votes an edge

    ---
    tags:
        - edge
    """
    edge = manager.get_edge_by_hash(edge_id)

    if edge is None:
        abort(403, 'Edge {} not found'.format(edge_id))

    vote = get_or_create_vote(edge, current_user, True)
    return jsonify(vote.to_json())


@api_blueprint.route('/api/edge/<edge_id>/vote/down')
@login_required
def store_down_vote(edge_id):
    """Down votes an edge

    ---
    tags:
        - edge
    """
    edge = manager.get_edge_by_hash(edge_id)

    if edge is None:
        abort(403, 'Edge {} not found'.format(edge_id))

    vote = get_or_create_vote(edge, current_user, False)
    return jsonify(vote.to_json())


@api_blueprint.route('/api/edge/<edge_id>/comment', methods=('GET', 'POST'))
@login_required
def store_comment(edge_id):
    """Adds a comment to the edge

    ---
    tags:
        - edge
    """
    edge = manager.get_edge_by_hash(edge_id)

    if edge is None:
        abort(403, 'Edge {} not found'.format(edge_id))

    if 'comment' not in request.args:
        abort(403, 'Comment not found')

    comment = EdgeComment(
        user=current_user,
        edge=edge,
        comment=request.args['comment']
    )

    manager.session.add(comment)
    manager.session.commit()

    return jsonify(comment.to_json)


####################################
# NODES
####################################

@api_blueprint.route('/api/node/by_bel/<node_bel>', methods=['GET'])
def nodes_by_bel(node_bel):
    """Gets all nodes that match the given BEL

    ---
    tags:
        - node
    """
    nodes = api.query_nodes(bel=node_bel)
    return jsonify(nodes)


@api_blueprint.route('/api/node/by_name/<node_name>', methods=['GET'])
def nodes_by_name(node_name):
    """Gets all nodes with the given name

    ---
    tags:
        - node
    """
    nodes = api.query_nodes(name=node_name)
    return jsonify(nodes)


@api_blueprint.route('/api/namespace/<namespace>/nodes', methods=['GET'])
def nodes_by_namespace(namespace):
    """Gets all nodes with identifiers from the given namespace

    ---
    tags:
        - namespace
    """
    nodes = api.query_nodes(namespace=namespace)
    return jsonify(nodes)


@api_blueprint.route('/api/namespace/<namespace>/name/<name>/nodes', methods=['GET'])
def nodes_by_namespace_name(namespace, name):
    """Gets all nodes with the given namespace and name

    ---
    tags:
        - namespace
    """
    nodes = api.query_nodes(namespace=namespace, name=name)
    return jsonify(nodes)


@api_blueprint.route('/api/node')
@roles_required('admin')
def get_all_nodes():
    """Gets all nodes

    ---
    tags:
        - node
    """
    return jsonify([
        {
            'id': nid,
            'node': node
        }
        for nid, node in api.nid_node.items()
    ])


@api_blueprint.route('/api/node/<node_id>')
def get_node_hash(node_id):
    """Gets the pybel node tuple

    :param node_id: A node identifier

    ---
    tags:
        - node
    """
    node = manager.get_node_by_hash(node_id)
    return jsonify(node.to_json())


@api_blueprint.route('/api/node/suggestion/')
def get_node_suggestion():
    """Suggests a node based on the search criteria

    ---
    tags:
        - node
    """
    if not request.args['search']:
        return jsonify([])

    autocompletion_set = api.get_nodes_containing_keyword(request.args['search'])

    return jsonify(autocompletion_set)


####################################
# PIPELINE
####################################

@api_blueprint.route('/api/pipeline/suggestion/')
def get_pipeline_function_names():
    """Sends a list of functions to use in the pipeline"""
    if not request.args['term']:
        return jsonify([])

    return jsonify([
        p.replace("_", " ").capitalize()
        for p in pipeline.no_arguments_map
        if request.args['term'].casefold() in p.replace("_", " ").casefold()
    ])


@api_blueprint.route('/api/query/<int:query_id>/drop', methods=['GET'])
@login_required
def drop_query_by_id(query_id):
    """Deletes a query

    ---
    tags:
        - query
    """
    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        abort(400, 'Invalid Query ID')

    if not (current_user.is_admin or query.user_id == current_user.id):
        abort(403, 'Unauthorized user')

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


@api_blueprint.route('/api/query/dropall/<int:user_id>', methods=['GET'])
@login_required
def drop_user_queries(user_id):
    """Deletes all queries associated to the user

    ---
    tags:
        - query
    """
    if not (current_user.is_admin or user_id == current_user.id):
        abort(403, 'Unauthorized user')

    manager.session.query(models.Query).filter(models.Query.user == current_user).delete()
    manager.session.commit()

    return next_or_jsonify('Dropped all queries associated with your account')


@api_blueprint.route('/api/query/<int:query_id>/info', methods=['GET'])
def query_to_network(query_id):
    """Returns info from a given query identifier

    ---
    tags:
        - query
    """
    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        abort(404)

    if not user_has_query_rights(current_user, query):
        abort(403, 'Insufficient rights to access query {}'.format(query_id))

    j = query.data.to_json()
    j['id'] = query.id
    j['creator'] = str(query.user)

    network_ids = j['network_ids']
    j['networks'] = [
        str(graph)
        for graph in api.get_graphs_by_ids(network_ids)
    ]

    return jsonify(j)


@api_blueprint.route('/api/query/<int:query_id>/parent', methods=['GET'])
def get_query_parent(query_id):
    """Returns the parent of the query

    ---
    tags:
        - query
    """
    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        abort(404)

    if not user_has_query_rights(current_user, query):
        abort(403, 'Insufficient rights to access query {}'.format(query_id))

    if not query.parent:
        return jsonify({
            'id': query.id,
            'parent': False
        })

    return jsonify({
        'id': query.parent.id,
        'parent': True
    })


@api_blueprint.route('/api/query/<int:query_id>/ancestor', methods=['GET'])
def get_query_oldest_ancestry(query_id):
    """Returns the parent of the query

    ---
    tags:
        - query
    """
    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        abort(404)

    if not user_has_query_rights(current_user, query):
        abort(403, 'Insufficient rights to access query {}'.format(query_id))

    ancestor_id = get_query_ancestor_id(query.id)

    return jsonify({
        'id': ancestor_id,
        'parent': bool(query.parent)
    })


def add_pipeline_entry(query_id, name, *args, **kwargs):
    """Adds an entry to the pipeline and """
    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        abort(404)

    q = query.data
    q.pipeline.append(name, *args, **kwargs)

    try:
        result = q.run(api)
    except Exception as e:
        return jsonify(
            status=400,
            query_id=query_id,
            args=args,
            kwargs=kwargs,
            exception=str(e)
        )

    qo = models.Query(
        assembly=query.assembly,
        seeding=json.dumps(q.seeds),
        pipeline_protocol=q.pipeline.to_jsons(),
        dump=q.to_jsons(),
        parent_id=query_id,
    )

    if current_user.is_authenticated:
        qo.user = current_user

    manager.session.add(qo)
    manager.session.commit()

    return jsonify({
        'status': 200,
        'id': qo.id
    })


@api_blueprint.route('/api/query/<int:query_id>/isolated_node/<node_id>', methods=['GET'])
def get_query_from_isolated_node(query_id, node_id):
    """Creates a query with a single node_id

    ---
    tags:
        - query
    """
    parent_query = safe_get_query(query_id)
    node = api.get_node_tuple_by_hash(node_id)

    child_query = Query(network_ids=[
        network.id
        for network in parent_query.assembly.networks
    ])
    child_query.add_seed_induction([node])

    child_query_model = models.Query(
        assembly=parent_query.assembly,
        seeding=json.dumps(child_query.seeds),
        pipeline_protocol=child_query.pipeline.to_jsons(),
        dump=child_query.to_jsons(),
        parent_id=parent_query.id,
    )

    if current_user.is_authenticated:
        child_query_model.user = current_user

    manager.session.add(child_query_model)
    manager.session.commit()

    return jsonify(child_query_model.to_json())


@api_blueprint.route('/api/query/<int:query_id>/add_applier/<name>', methods=['GET'])
def add_applier_to_query(query_id, name):
    """Builds a new query with the applier in the url and adds it to the end of the pipeline

    ---
    tags:
        - query
    """
    return add_pipeline_entry(query_id, name)


@api_blueprint.route('/api/query/<int:query_id>/add_node_list_applier/<name>/<list:node_ids>', methods=['GET'])
def add_node_list_applier_to_query(query_id, name, node_ids):
    """Builds a new query with a node list applier added to the end of the pipeline

    :param int query_id: A query's database identifier
    :param str name: The name of the function to apply at the end of the query
    :param list[str] node_ids: The node identifiers to use as the argument to the function

    ---
    tags:
        - query
    """
    return add_pipeline_entry(query_id, name, node_ids)


@api_blueprint.route('/api/query/<int:query_id>/add_node_applier/<name>/<node_id>', methods=['GET'])
def add_node_applier_to_query(query_id, name, node_id):
    """Builds a new query with a node applier added to the end of the pipeline

    :param int query_id: A query's database identifier
    :param str name: The name of the function to apply at the end of the query
    :param int node_id: The node identifier to use as the argument ot the function

    ---
    tags:
        - query
    """

    return add_pipeline_entry(query_id, name, node_id)


@api_blueprint.route('/api/query/<int:query_id>/add_annotation_filter/', methods=['GET'])
def add_annotation_filter_to_query(query_id):
    """Builds a new query with the annotation in the arguments. If 'and' is passed as an argument, it performs a AND
    query. By default it uses the OR condition.

    :param int query_id: A query's database identifier

    ---
    tags:
        - query
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
        {
            'id': user.id,
            'email': user.email
        }
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
    return jsonify({
        'id': current_user.id,
        'email': current_user.email
    })


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
def remove_user_role(user, role):
    """Removes a role from a user

    ---
    tags:
        - user
    """
    user_datastore.remove_role_from_user(user, role)
    user_datastore.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/user/<int:user_id>/delete')
@roles_required('admin')
def delete_user(user_id):
    """Deletes a user

    ---
    tags:
        - user
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

@api_blueprint.route('/api/query/<int:query_id>/analysis/<int:experiment_id>/')
def get_analysis(query_id, experiment_id):
    """Returns data from analysis

    ---
    tags:
        - experiment
        - query
    """
    # TODO user rights management
    network = get_network_from_request(query_id)

    experiment = manager.session.query(Experiment).get(experiment_id)
    if experiment is None:
        abort(404)

    data = pickle.loads(experiment.result)
    results = [
        {'node': api.get_node_hash(node), 'data': data[node]}
        for node in network.nodes_iter()
        if node in data
    ]

    return jsonify(results)


@api_blueprint.route('/api/query/<int:query_id>/analysis/<int:experiment_id>/median')
def get_analysis_median(query_id, experiment_id):
    """Returns data from analysis

    ---
    tags:
        - experiment
    """
    # TODO user rights management
    network = get_network_from_request(query_id)

    experiment = manager.session.query(Experiment).get(experiment_id)

    if experiment is None:
        abort(404, 'Experiment {} does not exist'.format(experiment_id))

    data = pickle.loads(experiment.result)
    # position 3 is the 'median' score
    results = {
        api.get_node_hash(node): data[node][3]
        for node in network.nodes_iter()
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
    experiment = manager.session.query(Experiment).get(experiment_id)

    if experiment is None:
        abort(404)

    if not current_user.is_admin and (current_user != experiment.user):
        abort(403, 'You do not have rights to drop this experiment')

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
    experiment = manager.session.query(Experiment).get(experiment_id)

    if experiment is None:
        abort(404)

    if not current_user.is_admin and (current_user != experiment.user):
        abort(403, 'You do not have rights to this experiment')

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
    """
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404)

    user_owns_network_or_403(network, current_user)

    project = manager.session.query(Project).get(project_id)
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
    """Adds rights to a network to a anther user

    ---
    tags:
        - network
    """
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404)

    user_owns_network_or_403(network, current_user)

    user = manager.session.query(User).get(user_id)
    user.networks.append(network)

    manager.session.commit()

    return next_or_jsonify('Added rights for {} to {}'.format(network, user))


@api_blueprint.route('/api/project/<int:project_id>')
@login_required
def get_project_metadata(project_id):
    """Returns the project as a JSON file

    ---
    tags:
        - project
    """
    project = manager.session.query(Project).get(project_id)

    if project is None:
        abort(404)

    if not current_user.is_admin and not project.has_user(current_user):
        abort(403, 'User does not have permission to access this Project')

    return jsonify(**project.to_json())


@api_blueprint.route('/api/project/<int:project_id>/drop')
@login_required
def drop_project_by_id(project_id):
    """Drops a given project from the database

    :param int project_id: THe project's database identifier

    ---
    tags:
        - project
    """
    project = manager.session.query(Project).get(project_id)

    if project is None:
        abort(404)

    if not current_user.is_admin and not project.has_user(current_user):
        abort(403, 'User does not have permission to access this Project')

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
    """
    project = manager.session.query(Project).get(project_id)

    if project is None:
        abort(404)

    if not current_user.is_admin and not project.has_user(current_user):
        abort(403, 'User does not have permission to access this Project')

    si = StringIO()
    cw = csv.writer(si)
    csv_list = [
        ('Name', 'Version', 'Nodes', 'Edges', 'Citations', 'Authors', 'Density', 'Components', 'AvgDegree', 'Warnings')]

    # TODO add all of these to the network's model or to the report
    for network in project.networks:
        csv_list_entry = network.name, network.version
        csv_list_entry += tuple(
            v
            for _, v in info_list(api.get_graph_by_id(network.id))
        )

        csv_list.append(csv_list_entry)

    csv_list.append(('Total', '') + tuple(v for _, v in info_list(project.as_bel())))

    cw.writerows(csv_list)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}_summary.csv".format(project.name.replace(' ', '_'))
    output.headers["Content-type"] = "text/csv"
    return output


@api_blueprint.route('/api/project/<project_id>/export/<serve_format>', methods=['GET'])
@login_required
def export_project_network(project_id, serve_format):
    """Builds a graph the networks belonging to the given project and sends it in the given format

    ---
    tags:
        - project
    """
    project = manager.session.query(Project).get(project_id)

    if project is None:
        abort(404)

    if not current_user.is_admin and not project.has_user(current_user):
        abort(403, 'User does not have permission to access this Project')

    network = project.as_bel()

    return serve_network(network, serve_format)


####################################
# METADATA
####################################

@api_blueprint.route('/api/pillage')
@roles_required('admin')
def pillage():
    """Claims all unclaimed networks"""
    counter = 0

    for network in manager.session.query(Network):
        if network.report is not None:
            continue

        counter += 1

        graph = network.as_bel()

        report = Report(
            network=network,
            user=current_user,
            completed=True,
            number_nodes=graph.number_of_nodes(),
            number_edges=graph.number_of_edges(),
            number_warnings=len(graph.warnings),
            public=False
        )

        manager.session.add(report)

    manager.session.commit()

    return next_or_jsonify('Claimed {} networks'.format(counter))


@api_blueprint.route('/api/meta/config')
@roles_required('admin')
def view_config():
    """Lists the application configuration"""
    return jsonify({
        k: str(v)
        for k, v in current_app.config.items()
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


@api_blueprint.route('/api/reporting/list')
@roles_required('admin')
def list_reporting():
    """Sends the reporting log as a text file"""
    return flask.send_file(os.path.join(PYBEL_LOG_DIR, 'reporting.txt'))


@api_blueprint.route('/api/network/overlap')
@roles_required('admin')
def list_all_network_overview():
    """Returns a meta-network describing the overlaps of all networks"""
    node_elements = []
    edge_elements = []

    for source_network in manager.list_networks():
        source_network_id = source_network.id
        source_bel_graph = api.get_graph_by_id(source_network_id)
        overlap = api.get_node_overlap(source_network_id)

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

    graph = api.universe

    chart_data = {
        'entities': count_functions(graph),
        'relations': count_relations(graph),
        'modifiers': {
            'Translocations': len(get_translocated(graph)),
            'Degradations': len(get_degradations(graph)),
            'Molecular Activities': len(get_activities(graph))
        },
        'variants': count_variants(graph),
        'namespaces': count_namespaces(graph),
        'citations_years': count_citation_years(graph),
        'info': info_json(graph)
    }

    chart_data['networks'] = {'count': len(api.networks)},

    return jsonify(**chart_data)
