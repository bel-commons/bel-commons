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
from copy import deepcopy
import os

from flask import Blueprint, request, jsonify, redirect, url_for, abort
from flask_cors import cross_origin
from pybel import from_pickle
from pybel_tools.mutation import add_canonical_names

from pybel_tools.dict_manager import DictManager
from pybel_tools.pipeline import mutator, function_is_registered
from pybel_tools.selection import get_subgraph_by_annotations

from .mozg_service_utils import get_rc_tree_annotations, make_graph, xsls_to_dct, get_mapping_dct
from .send_utils import to_json_custom
from pybel_tools.query import Query

from .constants import BLACK_LIST

AND = 'and'

log = logging.getLogger(__name__)

mozg_blueprint = Blueprint('mozg', __name__, url_prefix='/api/external/mozg')



#: Loads the folder where the projections and anhedonia pickle are
data_path = os.environ.get('BEL4IMOCEDE_DATA_PATH')

if data_path is None:
    raise ValueError('Cant find bel4imocede projection environment variable')

data_path = os.path.expanduser(data_path)

# Initial BEL Networks are parsed, preprocessed and additional information
# is added to related nodes. Preprocessing is done in the Jupyter Notebook.
projection_graph_path = os.path.join(data_path, 'projections.gpickle')

if not os.path.exists(projection_graph_path):
    raise RuntimeError('Projection graph missing from {}'.format(projection_graph_path))

projection_graph = from_pickle(projection_graph_path)

anhedonia_graph_path = os.path.join(data_path, 'anhedonia.gpickle')

if not os.path.exists(anhedonia_graph_path):
    raise RuntimeError('Anhedonia graph missing from {}'.format(anhedonia_graph_path))

anhedonia_graph = from_pickle(anhedonia_graph_path)

# Registers this function so we can look it up later
mutator(make_graph)

# Inserting graphs into the Manager
manager = DictManager()
queries = {}

projection_metadata = manager.insert_graph(projection_graph)
anhedonia_metadata = manager.insert_graph(anhedonia_graph)

MAPPING = {
    'projections': projection_metadata.id,
    'anhedonia': anhedonia_metadata.id
}

bi_data_path = os.path.join(data_path, 'vehicle.haloperidol-1.right_summary.xlsx')
BI_DATA = xsls_to_dct(bi_data_path)

mapping_dct_path = os.path.join(data_path, 'mapping_npao_to_aba.csv')
MAPPING_DICT = get_mapping_dct(mapping_dct_path)

def get_query_or_404(query_id):
    """Get a query if it exists

    :param int query_id:
    :rtype: Query
    """
    q = queries.get(query_id)
    if q is None:
        abort(404)
    return q


@mozg_blueprint.route('/network/<name>')
@cross_origin()
def get_mozg_initial_query(name):
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

    graph_id = MAPPING[name]

    query = Query()
    query.append_network(graph_id)
    query.append_pipeline(make_graph, annotations=annotations, values=values)

    query_id = len(queries)
    log.debug('Query: %d', query_id)

    queries[query_id] = query

    return redirect(url_for('.get_mozg_query_by_id', query_id=query_id))


def build_appended(query_id, name, *args, **kwargs):
    """Builds a new query with the given function appended to the current query's pipeline

    :param str name: Append function name
    :param args: Append function positional arguments
    :param kwargs: Append function keyword arguments
    :rtype: Query
    """
    query = get_query_or_404(query_id)
    new_query = deepcopy(query)
    new_query.pipeline.append(name, *args, **kwargs)

    new_query_id = len(queries)
    queries[new_query_id] = new_query

    return new_query_id, new_query


def add_pipeline_entry(query_id, name, *args, **kwargs):
    """Adds an entry to the pipeline

    :param int query_id: The identifier of the query
    :param str name: The name of the function to append
    """
    if not function_is_registered(name):
        abort(403, 'Invalid function name')

    qo_id, qo = build_appended(query_id, name, *args, **kwargs)

    return jsonify({
        'status': True,
        'id': qo_id,
    })

@mozg_blueprint.route('/query/<int:query_id>/add_annotation_filter/', methods=['GET', 'POST'])
@cross_origin()
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

    filters = request.get_json()

    # filters = {
    #     key: request.get_json()
    #     for key in request.args
    #     if key not in BLACK_LIST
    # }

    if not filters:  # If no filters send back the same query
        return jsonify({
            'status': False,
            'id': query_id
        })

    query_type = not request.args.get(AND)

    return add_pipeline_entry(query_id, get_subgraph_by_annotations, filters, query_type)

@mozg_blueprint.route('/query/<int:query_id>')
@cross_origin()
def get_mozg_query_by_id(query_id):

    query = queries[query_id]

    result = query.run(manager)

    log.debug('Number of returned nodes: %d', result.number_of_nodes())

    add_canonical_names(result)


    json_graph = to_json_custom(result)

    # Here we prepare and serve data for rc-tree
    rv = {}

    tree = get_rc_tree_annotations(result)

    if tree is not None:
        rv['status'] = True
        rv['payload'] = tree
    else:
        rv['status'] = False

    return jsonify(tree=rv, query_id=query_id, graph=json_graph)


@mozg_blueprint.route('/data/roi/<roi>')
@cross_origin()
def get_bi_data_by_roi(roi):
    """Returns BI data based on Region of Interest (roi)

    :param str roi: region of interest
    """

    roi_data = BI_DATA.get(roi)

    if not roi_data:
        return jsonify({
            'data': False,
        })

    return jsonify({
            'data': True,
            'roi_data': roi_data
        })

@mozg_blueprint.route('/mapping/<npao_region>')
@cross_origin()
def npao_to_aba(npao_region):
    """Maps NPAO term to Allen Brain Atlas ontology

    :param str npao_region: region of interest
    """

    roi_region = MAPPING_DICT.get(npao_region)

    if not roi_region :
        return jsonify({
            'mapping': False,
        })

    return jsonify({
            'mapping': True,
            'data': roi_region
        })