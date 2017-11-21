# -*- coding: utf-8 -*-

"""This module contains integrations developed for external services"""

import logging
import os

from flask import (
    Blueprint, request,
)
from flask_cors import cross_origin
from pybel import from_pickle
from pybel_tools.mutation import add_canonical_names
from pybel_tools.selection import (
    get_subgraph_by_edge_filter,
    search_node_names, get_subgraph_by_neighborhood)

from .graph_utils import build_annotation_search_filter
from .send_utils import serve_network

log = logging.getLogger(__name__)

mozg_blueprint = Blueprint('mozg', __name__)

data_path = os.environ.get('BEL4IMOCEDE_DATA_PATH')

if data_path is None:
    raise ValueError('Cant find bel4imocede projection environment variable')

data_path = os.path.expanduser(data_path)

projection_graph = from_pickle(os.path.join(data_path, 'projections.gpickle'))
anhedonia_graph = from_pickle(os.path.join(data_path, 'anhedonia.gpickle'))

BEL4IMOCEDE_MAPPING = {
    1: projection_graph,
    2: anhedonia_graph
}


@mozg_blueprint.route('/api/external/mozg/network/<int:network_id>')
@cross_origin()
def get_mozg_query(network_id):
    """Gets a network matching the induction over nodes and edges that match the given annotations and values

    ---
    """
    log.debug('Network id: %s', network_id)
    annotations = request.args.getlist('annotation[]')
    log.debug('Annotations: %s', annotations)
    values = request.args.getlist('value[]')
    log.debug('Values: %s', values)

    graph = from_pickle(BEL4IMOCEDE_MAPPING[network_id])

    nodes = list(search_node_names(projection_graph, values))

    neighborhoods = get_subgraph_by_neighborhood(graph, nodes)

    filtered_graph = get_subgraph_by_edge_filter(graph, build_annotation_search_filter(annotations, values))

    if neighborhoods is None:
        result = filtered_graph
    elif filtered_graph is None:
        result = neighborhoods
    else:
        result = neighborhoods + filtered_graph

    log.debug('Number of returned nodes: %d', len(result.nodes()))

    add_canonical_names(result)
    return serve_network(result)
