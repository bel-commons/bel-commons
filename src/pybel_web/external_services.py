# -*- coding: utf-8 -*-

"""This module contains integrations developed for external services"""

from flask import (
    Blueprint,
    request,
)
from flask_cors import cross_origin

from pybel import from_url
from pybel.constants import ANNOTATIONS
from pybel.struct import union
from pybel_tools.selection import (
    get_subgraph_by_annotations,
    get_subgraph_by_edge_filter,
    search_node_names,
    get_subgraph_by_neighborhood
)
from .send_utils import serve_network
from .utils import manager, api

belief_blueprint = Blueprint('belief', __name__)
neurommsig_blueprint = Blueprint('neurommsig', __name__)


@belief_blueprint.route('/belief/merge', methods=["POST"])
def semantic_merge():
    """Performs a semantic merge on BEL documents

    This endpoint receives a list of URLs, parses them synchronously, performs a semantic merge, then serializes
    a BEL document as the response.
    ---
    parameters:
      - name: urls
        in: query
        description: A list of URLs to BEL documents
        required: true
        schema:
          type: array
          items:
            type: string
    responses:
      200:
        description: A merged BEL document
    """
    request_json = request.get_json()
    urls = request_json['urls']

    graphs = [
        from_url(url, manager=manager)
        for url in urls
    ]

    super_graph = union(graphs)

    return serve_network(super_graph, serve_format='bel')


@neurommsig_blueprint.route('/api/get_alzheimers_subgraphs/')
@cross_origin()
def get_neurommsigs():
    """Returns AD NeuroMMSigs"""

    subgraph_annotations = request.args.getlist('subgraphs[]')

    alzheimers_network = manager.get_most_recent_network_by_name("Alzheimer's Disease Knowledge Assembly")

    network = get_subgraph_by_annotations(alzheimers_network, {'Subgraph': subgraph_annotations}, True)

    network = api.relabel_nodes_to_identifiers(network)

    return serve_network(network)


def build_annotation_search_filter(annotations, values):
    """Builds an annotation search filter for Mozg

    :param list[str] annotations: A list of the annotations to search
    :param list[str] values: A list of values to match against any annotations
    :return:
    """

    def annotation_dict_filter(graph, u, v, k, d):
        """Returns if any of the annotations and values match up"""
        if ANNOTATIONS not in d:
            return False

        for annotation in annotations:
            if annotation not in d[ANNOTATIONS]:
                continue
            if any(value in d[ANNOTATIONS][annotation] for value in values):
                return True

        return False


@neurommsig_blueprint.route('/api/mozg/network/serve')
@cross_origin()
def get_mozg_query():
    """Gets a network matching the induction over nodes and edges that match the given annotations and values

    ----
    tags:
        - external
        - mozg
    parameters:
      - name: network
        in: query
        description: The database network identifier(s)
        required: true
        type: integer
      - name: annotation
        in: query
        description: The annotations to search
        required: true
        type: string
      - name: value
        in: query
        description: The values to search in the given annotations
        required: true
        type: string
    responses:
      200:
        description: The network JSON
    """
    network_ids = request.args.getlist('network[]', type=int)

    graph = api.get_graphs_by_ids(network_ids)

    annotations = request.args.getlist('annotation[]')
    values = request.args.getlist('value[]')

    nodes = search_node_names(graph, values)
    neighborhoods = get_subgraph_by_neighborhood(graph, nodes)

    filtered_graph = get_subgraph_by_edge_filter(graph, build_annotation_search_filter(annotations, values))

    result = neighborhoods + filtered_graph

    network = api.relabel_nodes_to_identifiers(result)
    return serve_network(network)
