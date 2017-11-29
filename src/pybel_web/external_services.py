# -*- coding: utf-8 -*-

"""This module contains integrations developed for external services"""

import logging

from flask import Blueprint, jsonify, request
from flask_cors import cross_origin

from pybel import from_url
from pybel.struct import union
from pybel_tools.selection import get_subgraph_by_annotations
from pybel_tools.summary import get_annotation_values
from .send_utils import serve_network
from .utils import manager, relabel_nodes_to_hashes

log = logging.getLogger(__name__)

belief_blueprint = Blueprint('belief', __name__)
external_blueprint = Blueprint('external', __name__)


@belief_blueprint.route('/api/external/belief/merge', methods=["POST"])
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


@external_blueprint.route('/api/external/neurommsig/list_alzheimers_subgraphs/')
@cross_origin()
def list_neurommsig_ad_subgraph_names():
    """Returns a list of Alzheimer's Disease NeuroMMSigs

    ---
    tags:
      - neurommsig
    """
    alzheimers_network = manager.get_most_recent_network_by_name("Alzheimer's Disease Knowledge Assembly")
    values = get_annotation_values(alzheimers_network.as_bel(), 'Subgraph')
    return jsonify(sorted(values))


@external_blueprint.route('/api/external/neurommsig/get_alzheimers_subgraphs/')
@cross_origin()
def get_neurommsig_ad_subgraph():
    """Returns Alzheimer's Disease NeuroMMSigs

    ---
    tags:
      - neurommsig
    parameters:
      - name: subgraphs[]
        in: query
        description: Names of NeuroMMSig subgraphs
        required: true
        allowMultiple: true
        type: string
        minimum: 1
    """
    subgraph_annotations = request.args.getlist('subgraphs[]')

    alzheimers_network = manager.get_most_recent_network_by_name("Alzheimer's Disease Knowledge Assembly")

    network = get_subgraph_by_annotations(alzheimers_network.as_bel(), {'Subgraph': subgraph_annotations})

    network = relabel_nodes_to_hashes(network)

    return serve_network(network)
