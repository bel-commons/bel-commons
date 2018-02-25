# -*- coding: utf-8 -*-

"""
This module is developed to facilitate the Master thesis project (codename: Mozg)
and BEL4IMOCEDE project.

The abovementioned projects require to represent a subpart of a BEL network with
a requested term as a seed. The term can be present in a network as a node or as
an annotation of the node. Also the neighbourhood of found nodes is fetched.
Combined network is returned as a result.
"""

import logging
import os

from flask import (
    Blueprint, request,
)
from flask_cors import cross_origin

from pybel import from_pickle
from pybel.constants import ANNOTATIONS
from pybel_tools.mutation import add_canonical_names
from pybel_tools.selection import get_subgraph_by_edge_filter, get_subgraph_by_neighborhood, search_node_names
from .send_utils import serve_network

log = logging.getLogger(__name__)

mozg_blueprint = Blueprint('mozg', __name__, url_prefix='/api/external/mozg')

#: Loads the folder where the projections and anhedonia pickle are
data_path = os.environ.get('BEL4IMOCEDE_DATA_PATH')

if data_path is None:
    raise ValueError('Cant find bel4imocede projection environment variable')

data_path = os.path.expanduser(data_path)

# Initial BEL Networks are parsed, preprocessed and additional information
# is added to related nodes. Preprocessing is done in the Jupyter Notebook.
projection_graph = from_pickle(os.path.join(data_path, 'projections.gpickle'))
anhedonia_graph = from_pickle(os.path.join(data_path, 'anhedonia.gpickle'))

MAPPING = {
    'projections': projection_graph,
    'anhedonia': anhedonia_graph
}


def _annotation_dict_filter_helper(data, annotations, values):
    """Returns if any of the annotations and values match up

    :param dict data:
    :param list[str] annotations: A list of the annotations to search
    :param list[str] values: A list of values to match against any annotations
    :rtype: bool
    """
    if ANNOTATIONS not in data:
        return False

    data_annotations = data[ANNOTATIONS]

    for annotation in annotations:
        if annotation not in data_annotations:
            continue

        if any(value in data_annotations[annotation] for value in values):
            return True

    return False


def build_annotation_search_filter(annotations, values):
    """Builds an annotation search filter for Mozg

    :param list[str] annotations: A list of the annotations to search
    :param list[str] values: A list of values to match against any annotations
    :return: Edge filter function
    """

    def annotation_dict_filter(graph, u, v, k, d):
        """Returns if any of the annotations and values match up"""
        return _annotation_dict_filter_helper(d, annotations, values)

    return annotation_dict_filter


@mozg_blueprint.route('/network/<name>')
@cross_origin()
def get_mozg_query(name):
    """This endpoint receives a network name, annotation(s) and a related query term(s), prepares a network
    matching the induction over nodes and edges that match the given annotations and values and sends
    a combined BEL network as the response.

    ---
    tags:
        - mozg
    parameters:
      - name: name
        in: path
        description: A name of a network
        required: true
        type: string
        enum: [projections, anhedonia]
      - name: annotation[]
        in: query
        description: A network annotation
        required: true
        allowMultiple: true
        type: string
        minimum: 1
      - name: value[]
        in: query
        description: A network annotation's value
        required: true
        allowMultiple: true
        type: string
        minimum: 1
    responses:
      200:
        description: A BEL network with requested node(s) and its(their) neighborhood
    """
    log.debug('Network name: %s', name)

    annotations = request.args.getlist('annotation[]')
    log.debug('Annotations: %s', annotations)

    values = request.args.getlist('value[]')
    log.debug('Values: %s', values)

    graph = MAPPING[name]

    nodes = list(search_node_names(graph, values))

    neighborhoods = get_subgraph_by_neighborhood(graph, nodes)

    filtered_graph = get_subgraph_by_edge_filter(graph, build_annotation_search_filter(annotations, values))

    if neighborhoods is None:
        result = filtered_graph
    elif filtered_graph is None:
        result = neighborhoods
    else:
        result = neighborhoods + filtered_graph

    log.debug('Number of returned nodes: %d', result.number_of_nodes())

    add_canonical_names(result)
    return serve_network(result)
