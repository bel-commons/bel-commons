# -*- coding: utf-8 -*-

"""This module runs the database-backed PyBEL API"""

import csv
import json
import logging
import pickle
from operator import itemgetter

import flask
import networkx as nx
from flask import (
    Blueprint,
    make_response,
    flash,
    current_app,
    jsonify,
    redirect,
    url_for,
    render_template,
    request
)
from flask_login import login_required, current_user
from flask_security import roles_required, roles_accepted
from six import StringIO
from sqlalchemy.exc import IntegrityError

import pybel
from pybel.constants import (
    METADATA_AUTHORS,
    METADATA_CONTACT,
    METADATA_NAME,
)
from pybel.manager import Namespace, Annotation, Network
from pybel_tools import pipeline
from pybel_tools.analysis.npa import RESULT_LABELS
from pybel_tools.definition_utils import write_namespace
from pybel_tools.query import Query
from pybel_tools.selection.induce_subgraph import get_subgraph_by_annotations
from pybel_tools.summary import (
    info_json,
    get_authors,
    get_pubmed_identifiers,
    get_undefined_namespace_names,
    get_incorrect_names,
    get_naked_names,
)
from pybel_tools.summary import info_str
from . import models
from .constants import *
from .main_service import (
    FORMAT,
    SOURCE_NODE,
    TARGET_NODE,
    PATHS_METHOD,
    UNDIRECTED,
    BLACK_LIST
)
from .main_service import get_network_ids_with_permission
from .models import Report, User, Experiment, Project
from .send_utils import serve_network
from .utils import (
    get_recent_reports,
    manager,
    api,
    user_datastore,
    query_form_to_dict,
    get_query_ancestor_id,
)

log = logging.getLogger(__name__)

api_blueprint = Blueprint('dbs', __name__)


def get_network_from_request(query_id):
    """Process the GET request returning the filtered network

    :param int query_id: Query id
    :return: A BEL graph
    :rtype: pybel.BELGraph
    """
    try:
        return manager.session.query(models.Query).get(query_id).run(api)
    except IntegrityError:
        flask.flash("You do not have permission to access the queried network")
        log.exception('User %s trying to access not allowed network', current_user)
        return redirect(url_for('home'))


@api_blueprint.route('/api/receive', methods=['POST'])
def receive():
    """Receives a JSON serialized BEL graph"""
    try:
        network = pybel.from_json(request.get_json())
    except:
        flask.flash('Error parsing json')
        return redirect(url_for('home'))

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

    return redirect(url_for('home'))


####################################
# NAMESPACE
####################################

@api_blueprint.route('/api/namespaces', methods=['GET'])
def list_namespaces():
    """Lists all namespaces"""
    namespaces = api.query_namespaces()
    return jsonify(namespaces)


@api_blueprint.route('/api/namespace/<keyword>', methods=['GET'])
def list_names(keyword):
    """Lists all names from a given namespace, by keyword"""
    names = api.query_namespaces(name_list=True, keyword=keyword)
    return jsonify(names)


@api_blueprint.route('/api/namespace/<int:namespace_id>/drop')
@roles_required('admin')
def drop_namespace_by_id(namespace_id):
    """Drops a namespace given its identifier"""
    log.info('dropping namespace %s', namespace_id)
    manager.session.query(Namespace).filter(Namespace.id == namespace_id).delete()
    manager.session.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/namespace/drop')
@roles_required('admin')
def drop_namespaces():
    """Drops all namespaces"""
    log.info('dropping all namespaces')
    manager.session.query(Namespace).delete()
    manager.session.commit()
    return jsonify({'status': 200})


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


@api_blueprint.route('/api/namespace/builder/undefined/<network_id>/<namespace>')
def download_undefined_namespace(network_id, namespace):
    """Outputs a namespace built for this undefined namespace"""
    """Outputs a namespace built for this undefined namespace"""
    network = api.get_network_by_id(network_id)
    names = get_undefined_namespace_names(network, namespace)
    return _build_namespace_helper(network, namespace, names)


@api_blueprint.route('/api/namespace/builder/incorrect/<network_id>/<namespace>')
def download_missing_namespace(network_id, namespace):
    """Outputs a namespace built from the missing names in the given namespace"""
    graph = api.get_network_by_id(network_id)
    names = get_incorrect_names(graph, namespace)
    return _build_namespace_helper(graph, namespace, names)


@api_blueprint.route('/api/namespace/builder/naked/<network_id>/')
def download_naked_names(network_id):
    """Outputs a namespace built from the naked names in the given namespace"""
    graph = api.get_network_by_id(network_id)
    names = get_naked_names(graph)
    return _build_namespace_helper(graph, 'NAKED', names)


####################################
# ANNOTATIONS
####################################

@api_blueprint.route('/api/annotations', methods=['GET'])
def list_annotations():
    """Lists all annotations"""
    annotations = api.query_annotations()
    return jsonify(annotations)


@api_blueprint.route('/api/annotation/<keyword>', methods=['GET'])
def list_annotation_names(keyword):
    """Lists the values in an annotation, by keyword"""
    values = api.query_annotations(name_list=True, keyword=keyword)
    return jsonify(values)


@api_blueprint.route('/api/annotation/<annotation_id>/drop')
@roles_required('admin')
def drop_annotation_by_id(annotation_id):
    """Drops an annotation given its identifier"""
    log.info('dropping annotation %s', annotation_id)
    manager.session.query(Annotation).filter(Annotation.id == annotation_id).delete()
    manager.session.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/annotation/drop')
@roles_required('admin')
def drop_annotations():
    """Drops all annotations"""
    log.info('dropping all annotations')
    manager.session.query(Annotation).delete()
    manager.session.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/annotation/suggestion/')
def suggest_annotation():
    """Creates a suggestion for annotations"""
    if not request.args['search']:
        return jsonify([])

    autocompletion_set = api.get_annotations_containing_keyword(request.args['search'])

    return jsonify(autocompletion_set)


####################################
# NETWORKS
####################################

@api_blueprint.route('/api/query/<int:query_id>/export/<serve_format>', methods=['GET'])
def download_network(query_id, serve_format):
    """Downloads a network in the given format"""
    network = manager.session.query(models.Query).get(query_id).run(api)
    return serve_network(network, serve_format=serve_format)


@api_blueprint.route('/api/network/<int:network_id>/namespaces', methods=['GET'])
def namespaces_by_network(network_id):
    """Gets all of the namespaces in a network"""
    network_namespaces = api.query_namespaces(network_id=network_id)
    return jsonify(network_namespaces)


@api_blueprint.route('/api/network/<int:network_id>/annotations', methods=['GET'])
def annotations_by_network(network_id):
    """Gets all of the annotations in a network"""
    network_annotations = api.query_annotations(network_id=network_id)
    return jsonify(network_annotations)


@api_blueprint.route('/api/network/<int:network_id>/citations', methods=['GET'])
def citations_by_network(network_id):
    """Gets all of the citations in a given network"""
    citations = api.query_citations(network_id=network_id)
    return jsonify(citations)


@api_blueprint.route('/api/network/<int:network_id>/edges', methods=['GET'])
def edges_by_network(network_id):
    """Gets all of the edges in a network"""
    edges = api.query_edges(network_id=network_id)
    return jsonify(edges)


@api_blueprint.route('/api/network/<int:network_id>/edges/offset/<int:offset_start>/<int:offset_end>', methods=['GET'])
def edges_by_network_offset(network_id, offset_start, offset_end):
    """Gets all of the edges in a given network with a given offset"""
    edges = api.query_edges(network_id=network_id, offset_start=offset_start, offset_end=offset_end)
    return jsonify(edges)


@api_blueprint.route('/api/network/<int:network_id>/nodes/', methods=['GET'])
def nodes_by_network(network_id):
    """Gets all of the nodes in a network"""
    nodes = api.query_nodes(network_id=network_id)
    return jsonify(nodes)


@api_blueprint.route('/api/network/<int:network_id>/drop')
@roles_required('admin')
def drop_network_by_id(network_id):
    """Drops a specific graph"""
    log.info('dropping graphs %s', network_id)
    api.forget_network(network_id)
    manager.drop_network_by_id(network_id)
    return jsonify({'status': 200})


@api_blueprint.route('/api/network/drop')
@roles_required('admin')
def drop_networks():
    """Drops all graphs"""
    log.info('dropping all networks')
    api.clear()
    manager.drop_networks()
    return jsonify({'status': 200})


@api_blueprint.route('/api/network/list', methods=['GET'])
def get_network_list():
    """Gets a list of networks"""
    return jsonify(manager.list_networks())


@api_blueprint.route('/api/network/<int:network_id>/summarize')
def get_number_nodes(network_id):
    """Gets a summary of the given network"""
    return jsonify(info_json(api.get_network_by_id(network_id)))


@api_blueprint.route('/api/network/<int:query_id>', methods=['GET'])
@login_required
def get_network(query_id):
    """Builds a graph from the given network id and sends it in the given format"""
    network = get_network_from_request(query_id)
    network = api.relabel_nodes_to_identifiers(network)
    return serve_network(network, request.args.get(FORMAT))


@api_blueprint.route('/api/network/<int:network_id>/name')
def get_network_name_by_id(network_id):
    """Returns network name given its id"""
    if network_id == 0:
        return ''

    network = api.get_network_by_id(network_id)
    return jsonify(network.name)


@api_blueprint.route('/api/network/<int:network_id>/drop')
@roles_required('admin')
def drop_network(network_id):
    """Drops a given network

    :param int network_id: The identifier of the network to drop
    """
    manager.drop_network_by_id(network_id)
    flash('Dropped network {}'.format(network_id))
    return redirect(url_for('view_networks'))


@api_blueprint.route('/api/network/<int:network_id>/drop/<int:user_id>')
@login_required
def drop_user_network(network_id, user_id):
    """Drops a given network"""
    if current_user.id != user_id:
        flask.abort(403)

    try:
        report = manager.session.query(Report).filter(Report.network_id == network_id,
                                                      Report.user_id == user_id).one()
        manager.session.delete(report.network)
        manager.session.delete(report)
        manager.session.commit()
        flash('Dropped network {}'.format(network_id))
    except Exception:
        manager.session.rollback()
        flash('Problem dropping network {}'.format(network_id), category='error')

    return redirect(url_for('view_networks'))


@api_blueprint.route('/api/network/<int:network_id>/make_public')
@roles_accepted('admin', 'scai')
def make_network_public(network_id):
    """Makes a given network public using admin powers"""
    report = manager.session.query(Report).filter(Report.network_id == network_id).one()
    report.public = True
    manager.session.commit()

    flash('Made {} public'.format(report.network))
    return redirect(url_for('view_networks'))


@api_blueprint.route('/api/network/<int:network_id>/make_private')
@roles_accepted('admin', 'scai')
def make_network_private(network_id):
    """Makes a given network private using admin powers"""
    report = manager.session.query(Report).filter(Report.network_id == network_id).one()
    report.public = False
    manager.session.commit()

    flash('Made {} private'.format(report.network))
    return redirect(url_for('view_networks'))


@api_blueprint.route('/api/network/<int:network_id>/make_public/<int:user_id>')
@login_required
def make_user_network_public(user_id, network_id):
    """Makes a given network public after authenticating that the given user is the owner."""
    if current_user.id != user_id:
        return flask.abort(402)

    report = manager.session.query(Report).filter(Report.network_id == network_id, Report.user_id == user_id).one()
    report.public = True
    manager.session.commit()

    flash('Made {} public'.format(report.network))
    return redirect(url_for('view_networks'))


@api_blueprint.route('/api/network/make_private/<int:user_id>/<int:network_id>')
@login_required
def make_user_network_private(user_id, network_id):
    """Makes a given network private after authenticating that the given user is the owner."""
    if current_user.id != user_id:
        return flask.abort(402)

    report = manager.session.query(Report).filter(Report.network_id == network_id, Report.user_id == user_id).one()
    report.public = False
    manager.session.commit()

    flash('Made {} private'.format(report.network))
    return redirect(url_for('view_networks'))


@api_blueprint.route('/api/query/<int:query_id>/tree/')
@login_required
def get_tree_api(query_id):
    """Builds the annotation tree data structure for a given graph"""

    network = get_network_from_request(query_id)

    return jsonify(api.get_tree_annotations(network))


####################################
# NETWORK QUERIES
####################################


@api_blueprint.route('/api/query/<int:query_id>/paths/<int:source_id>/<int:target_id>/')
def get_paths(query_id, source_id, target_id):
    """Returns array of shortest/all paths given a source node and target node both belonging in the graph

    :return: JSON
    """

    network = get_network_from_request(query_id)

    method = request.args.get(PATHS_METHOD)

    undirected = UNDIRECTED in request.args

    cutoff = request.args.get('cutoff', 12)

    source = api.get_node_by_id(source_id)
    target = api.get_node_by_id(target_id)

    log.info('Source: %s, target: %s', source, target)

    if source not in network or target not in network:
        log.info('Source/target node not in network')
        log.info('Nodes in network: %s', network.nodes())
        return flask.abort(500, 'Source/target node not in network')

    if undirected:
        network = network.to_undirected()

    if method == 'all':
        all_paths = nx.all_simple_paths(network, source=source, target=target, cutoff=cutoff)
        return jsonify(api.paths_tuples_to_ids(all_paths))

    try:
        shortest_path = nx.shortest_path(network, source=source, target=target)
    except nx.NetworkXNoPath:
        log.debug('No paths between: {} and {}'.format(source, target))
        return 'No paths between the selected nodes'

    return jsonify(api.get_node_ids(shortest_path))


@api_blueprint.route('/api/query/<int:query_id>/centrality/<int:node_number>', methods=['GET'])
def get_nodes_by_betweenness_centrality(query_id, node_number):
    """Gets a list of nodes with the top betweenness-centrality"""
    network = get_network_from_request(query_id)

    if node_number > nx.number_of_nodes(network):
        return 'The number introduced is bigger than the nodes in the network'

    bw_dict = nx.betweenness_centrality(network)

    return jsonify([
        api.get_node_id(node)
        for node, score in sorted(bw_dict.items(), key=itemgetter(1), reverse=True)[0:node_number]
    ])


@api_blueprint.route('/api/query/<int:query_id>/pmids/')
def get_all_pmids(query_id):
    """Gets a list of all PubMed identifiers in the network produced by the given URL parameters"""
    network = get_network_from_request(query_id)
    return jsonify(sorted(get_pubmed_identifiers(network)))


@api_blueprint.route('/api/query/nodes/')
def get_node_hashes():
    """Gets the dictionary of {node id: pybel node tuples}"""
    return jsonify(api.nid_node)


####################################
# CITATIONS
####################################

@api_blueprint.route('/api/citations', methods=['GET'])
def list_citations():
    """Gets all citations"""
    citations = api.query_citations()
    return jsonify(citations)


@api_blueprint.route('/api/citations/by_author/<author>', methods=['GET'])
def list_citations_by_author(author):
    """Gets all citations from the given author"""
    citations = api.query_citations(author=author)
    return jsonify(citations)


@api_blueprint.route('/api/pubmed/suggestion/')
def get_pubmed_suggestion():
    """Return list of pubmedids matching the integer keyword"""

    autocompletion_set = api.get_pubmed_containing_keyword(request.args['search'])

    return jsonify([
        {"text": pubmed, "id": index}
        for index, pubmed in enumerate(autocompletion_set)
    ])


####################################
# AUTHOR
####################################

@api_blueprint.route('/api/query/<query_id>/authors')
def get_all_authors(query_id):
    """Gets a list of all authors in the graph produced by the given URL parameters"""
    network = get_network_from_request(query_id)
    return jsonify(sorted(get_authors(network)))


@api_blueprint.route('/api/authors/suggestion/')
def get_author_suggestion():
    """Return list of authors matching the author keyword"""

    autocompletion_set = api.get_authors_containing_keyword(request.args['search'])

    return jsonify([
        {"text": pubmed, "id": index}
        for index, pubmed in enumerate(autocompletion_set)
    ])


####################################
# EDGES
####################################

@api_blueprint.route('/api/edges/by_bel/statement/<statement_bel>', methods=['GET'])
def edges_by_bel_statement(statement_bel):
    """Get edges that match the given BEL"""
    edges = api.query_edges(statement=statement_bel)
    return jsonify(edges)


@api_blueprint.route('/api/edges/by_bel/source/<source_bel>', methods=['GET'])
def edges_by_bel_source(source_bel):
    """Get edges whose sources match the given BEL"""
    edges = api.query_edges(source=source_bel)
    return jsonify(edges)


@api_blueprint.route('/api/edges/by_bel/target/<target_bel>', methods=['GET'])
def edges_by_bel_target(target_bel):
    """Gets edges whose targets match the given BEL"""
    edges = api.query_edges(target=target_bel)
    return jsonify(edges)


@api_blueprint.route('/api/edges/by_pmid/<int:pmid>', methods=['GET'])
def edges_by_pmid(pmid):
    """Gets edges that have a given PubMed identifier"""
    edges = api.query_edges(pmid=pmid)
    return jsonify(edges)


@api_blueprint.route('/api/edges/by_author/<author>', methods=['GET'])
def edges_by_author(author):
    """Gets edges with a given author"""
    edges = api.query_edges(author=author)
    return jsonify(edges)


@api_blueprint.route('/api/edges/by_annotation/<annotation_name>/<annotation_value>', methods=['GET'])
def edges_by_annotation(annotation_name, annotation_value):
    """Gets edges with the given annotation/value combination"""
    edges = api.query_edges(annotations={annotation_name: annotation_value})
    return jsonify(edges)


@api_blueprint.route('/api/edges/provenance/<int:source_id>/<int:target_id>')
def get_edges(source_id, target_id):
    """Gets all edges between the two given nodes"""
    source = api.get_node_by_id(source_id)
    target = api.get_node_by_id(target_id)
    return jsonify(api.get_edges(source, target))


####################################
# NODES
####################################

@api_blueprint.route('/api/nodes/by_bel/<node_bel>', methods=['GET'])
def nodes_by_bel(node_bel):
    """Gets all nodes that match the given BEL"""
    nodes = api.query_nodes(bel=node_bel)
    return jsonify(nodes)


@api_blueprint.route('/api/nodes/by_name/<node_name>', methods=['GET'])
def nodes_by_name(node_name):
    """Gets all nodes with the given name"""
    nodes = api.query_nodes(name=node_name)
    return jsonify(nodes)


@api_blueprint.route('/api/nodes/by_namespace/<namespace>', methods=['GET'])
def nodes_by_namespace(namespace):
    """Gets all nodes with identifiers from the given namespace"""
    nodes = api.query_nodes(namespace=namespace)
    return jsonify(nodes)


@api_blueprint.route('/api/nodes/by_defined_name/<node_namespace>/<node_name>', methods=['GET'])
def nodes_by_namespace_name(node_namespace, node_name):
    """Gets all nodes with the given namespace and name"""
    nodes = api.query_nodes(namespace=node_namespace, name=node_name)
    return jsonify(nodes)


@api_blueprint.route('/api/nodes/<int:node_id>')
def get_node_hash(node_id):
    """Gets the pybel node tuple

    :param node_id: A node identifier
    """
    node = api.get_node_by_id(node_id)
    return jsonify(node)


@api_blueprint.route('/api/nodes/suggestion/')
def get_node_suggestion():
    """Suggests a node based on the search criteria"""
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


@api_blueprint.route('/api/pipeline/query', methods=['POST'])
def get_pipeline():
    """Executes a pipeline"""

    d = query_form_to_dict(request.form)

    q = Query.from_json(d)

    assembly = models.Assembly(networks=[
        manager.session.query(Network).get(network_id)
        for network_id in q.network_ids
    ])

    qo = models.Query(
        user=current_user,
        assembly=assembly,
        seeding=json.dumps(q.seeds),
        pipeline_protocol=q.pipeline.to_jsons(),
        dump=q.to_jsons(),
    )

    manager.session.add(qo)
    manager.session.commit()

    return render_template(
        'run_query.html',
        query=qo
    )


@api_blueprint.route('/api/pipeline/query/<int:query_id>/drop', methods=['GET', 'POST'])
@login_required
def drop_query_by_id(query_id):
    """Deletes a query"""
    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        return flask.abort(404, 'Invalid Query ID')

    if not (current_user.admin or query.user_id == current_user.id):
        return flask.abort(403, 'Unauthorized user')

    manager.session.delete(query)
    manager.session.commit()
    flash('Deleted query {}'.format(query_id))

    return redirect(url_for('home'))


@api_blueprint.route('/api/query/dropall/<int:user_id>', methods=['GET'])
@login_required
def drop_user_queries(user_id):
    """Deletes all queries associated to the user"""

    if not (current_user.admin or user_id == current_user.id):
        return flask.abort(403, 'Unauthorized user')

    query = manager.session.query(models.Query).filter_by(user_id=current_user.id).delete()
    manager.session.commit()
    flash('Deleted query {}'.format('All queries associated with your user has been deleted'))

    return redirect(url_for('home'))


@api_blueprint.route('/api/query/<int:query_id>/info', methods=['GET'])
def query_to_network(query_id):
    """Returns info from a given query ID"""
    query = manager.session.query(models.Query).get(query_id)

    # TODO: Make a function to get the query checking permission
    if query is None:
        return flask.abort(404, 'Invalid Query ID')

    if not (current_user.admin or query.user_id == current_user.id):
        flask.abort(403)

    j = query.data.to_json()
    j['id'] = query.id

    network_ids = j['network_ids']
    j['networks'] = [
        api.get_network_by_id(network_id).name
        for network_id in network_ids
    ]

    return jsonify(j)


@api_blueprint.route('/api/query/<int:query_id>/parent', methods=['GET'])
def get_query_parent(query_id):
    """Returns the parent of the query"""

    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        return flask.abort(404, 'Invalid Query ID')

    if not (current_user.admin or query.user_id == current_user.id):
        flask.abort(403)

    if not query.parent:
        return jsonify({
            'id': query.id, 'parent': False
        })

    return jsonify({
        'id': query.parent.id, 'parent': True
    })


@api_blueprint.route('/api/query/<int:query_id>/ancestor', methods=['GET'])
def get_query_oldest_ancestry(query_id):
    """Returns the parent of the query"""

    query = manager.session.query(models.Query).get(query_id)

    if query is None:
        return flask.abort(404, 'Invalid Query ID')

    if not (current_user.admin or query.user_id == current_user.id):
        flask.abort(403)

    ancestor_id = get_query_ancestor_id(query.id)

    if not query.parent:
        return jsonify({
            'id': ancestor_id, 'parent': False
        })

    return jsonify({
        'id': ancestor_id, 'parent': True
    })


@api_blueprint.route('/api/network/<int:network_id>/export/<serve_format>', methods=['GET'])
@login_required
def export_network(network_id, serve_format):
    """Builds a graph from the given network id and sends it in the given format"""

    networks_ids = get_network_ids_with_permission(api)

    if network_id not in networks_ids:
        return flask.abort(404, 'You have no permission to download the selected network')

    network = api.get_network_by_id(network_id)

    return serve_network(network, serve_format)


def add_pipeline_entry(query_id, name, *args, **kwargs):
    """Adds an entry to the pipeline and """
    query = manager.session.query(models.Query).get(query_id)

    q = query.data
    q.pipeline.append(name, *args, **kwargs)

    result = q.run(api)
    log.info('result info: %s', info_str(result))

    qo = models.Query(
        user=current_user,
        assembly=query.assembly,
        seeding=json.dumps(q.seeds),
        pipeline_protocol=q.pipeline.to_jsons(),
        dump=q.to_jsons(),
        parent_id=query_id,
    )

    log.info('result info: %s', info_str(qo.run(api)))

    manager.session.add(qo)
    manager.session.commit()

    return jsonify({
        'id': qo.id
    })


@api_blueprint.route('/api/query/<int:query_id>/add_applier/<name>', methods=['GET'])
def add_applier_to_query(query_id, name):
    """Builds a new query with the applier in the url and adds it to the end of the pipeline"""
    return add_pipeline_entry(query_id, name)


@api_blueprint.route('/api/query/<int:query_id>/add_node_list_applier/<name>/<intlist:node_ids>', methods=['GET'])
def add_node_list_applier_to_query(query_id, name, node_ids):
    """Builds a new query with a node list applier added to the end of the pipeline

    :param int query_id: A query's database identifier
    :param str name: The name of the function to apply at the end of the query
    :param list[int] node_ids: The node identifiers to use as the argument to the function
    """
    return add_pipeline_entry(query_id, name, node_ids)


@api_blueprint.route('/api/query/<int:query_id>/add_node_applier/<name>/<int:node_id>', methods=['GET'])
def add_node_applier_to_query(query_id, name, node_id):
    """Builds a new query with a node applier added to the end of the pipeline

    :param int query_id: A query's database identifier
    :param str name: The name of the function to apply at the end of the query
    :param int node_id: The node identifier to use as the argument ot the function
    """
    return add_pipeline_entry(query_id, name, node_id)


@api_blueprint.route('/api/query/<int:query_id>/add_annotation_filter/', methods=['GET'])
def add_annotation_filter_to_query(query_id):
    """Builds a new query with the annotation in the arguments. If 'and' is passed as an argument, it performs a AND
    query. By default it uses the OR condition.

    :param int query_id: A query's database identifier
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


@api_blueprint.route('/api/user/<user>/add_role/<role>')
@roles_required('admin')
def add_user_role(user, role):
    """Adds a role to a use"""
    user_datastore.add_role_to_user(user, role)
    user_datastore.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/user/<user>/remove_role/<role>')
@roles_required('admin')
def remove_user_role(user, role):
    """Removes a role from a user"""
    user_datastore.remove_role_from_user(user, role)
    user_datastore.commit()
    return jsonify({'status': 200})


@api_blueprint.route('/api/user/<int:user_id>/delete')
@roles_required('admin')
def delete_user(user_id):
    """Deletes a user"""
    u = User.query.get(user_id)
    user_datastore.delete_user(u)
    user_datastore.commit()
    return jsonify({'status': 200, 'action': 'deleted user', 'user': str(u)})


####################################
# Analysis
####################################

@api_blueprint.route('/api/query/<int:query_id>/analysis/<int:analysis_id>/')
def get_analysis(query_id, analysis_id):
    """Returns data from analysis"""
    network = get_network_from_request(query_id)
    experiment = manager.session.query(Experiment).get(analysis_id)
    data = pickle.loads(experiment.result)
    results = [
        {'node': api.get_node_id(node), 'data': data[node]}
        for node in network.nodes_iter()
        if node in data
    ]

    return jsonify(results)


@api_blueprint.route('/api/query/<int:query_id>/analysis/<int:analysis_id>/median')
def get_analysis_median(query_id, analysis_id):
    """Returns data from analysis"""
    network = get_network_from_request(query_id)
    experiment = manager.session.query(Experiment).get(analysis_id)
    data = pickle.loads(experiment.result)
    # position 3 is the 'median' score
    results = {
        api.get_node_id(node): data[node][3]
        for node in network.nodes_iter()
        if node in data
    }

    return jsonify(results)


@api_blueprint.route('/api/analysis/<int:analysis_id>/drop')
@login_required
def delete_analysis_results(analysis_id):
    """Drops an analysis"""
    if not current_user.admin:
        flask.abort(403)

    manager.session.query(Experiment).get(analysis_id).delete()
    manager.session.commit()

    if 'next' in request.args:
        flash('Dropped Experiment #{}'.format(analysis_id))
        return redirect(request.args['next'])

    return jsonify({'status': 200})


@api_blueprint.route('/api/analysis/<int:analysis_id>/download')
def download_analysis(analysis_id):
    """Downloads data from a given experiment as a CSV"""
    experiment = manager.session.query(Experiment).get(analysis_id)
    si = StringIO()
    cw = csv.writer(si)
    csv_list = [('Namespace', 'Name') + tuple(RESULT_LABELS)]
    experiment_data = pickle.loads(experiment.result)
    csv_list.extend((ns, n) + tuple(v) for (_, ns, n), v in experiment_data.items())
    cw.writerows(csv_list)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=cmpa_{}.csv".format(analysis_id)
    output.headers["Content-type"] = "text/csv"
    return output


####################################
# RIGHTS MANAGEMENT
####################################


@api_blueprint.route('/api/network/<int:network_id>/grant_project/<int:project_id>')
def grant_network_to_project(network_id, project_id):
    """Adds rights to a network to a project"""
    network = manager.session.query(Network).get(network_id)

    # Check that the user is the owner of the the network
    if not network.report.user.id == current_user.id:
        flask.abort(403)

    organization = manager.session.query(Project).get(project_id)
    organization.networks.append(network)

    manager.session.commit()

    return jsonify({'status': 200})


@api_blueprint.route('/api/network/<int:network_id>/grant_user/<int:user_id>')
def grant_network_to_user(network_id, user_id):
    """Adds rights to a network to a anther user"""
    network = manager.session.query(Network).get(network_id)

    # Check that the user is the owner of the the network
    if not network.report.user.id == current_user.id:
        flask.abort(403)

    user = manager.session.query(User).get(user_id)
    user.networks.append(network)

    manager.session.commit()

    return jsonify({'status': 200})


####################################
# METADATA
####################################

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
