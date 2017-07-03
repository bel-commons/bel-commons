# -*- coding: utf-8 -*-

import logging

from flask import send_file, Response, jsonify
from six import BytesIO, StringIO

from pybel import to_cx, to_bel_lines, to_graphml, to_bytes, to_csv, to_sif, to_jgif, to_gsea
from pybel.constants import GRAPH_ANNOTATION_LIST
from pybel_tools.mutation.metadata import serialize_authors

log = logging.getLogger(__name__)


def to_json_custom(graph, _id='id', source='source', target='target', key='key'):
    result = {
        'directed': graph.is_directed(),
        'multigraph': graph.is_multigraph(),
        'graph': graph.graph
    }

    if GRAPH_ANNOTATION_LIST in result['graph']:
        result['graph'][GRAPH_ANNOTATION_LIST] = {
            k: list(sorted(v))
            for k, v in result['graph'][GRAPH_ANNOTATION_LIST].items()
        }

    mapping = {}

    result['nodes'] = []
    for i, node in enumerate(sorted(graph.nodes_iter())):
        nd = graph.node[node].copy()
        nd[_id] = node
        result['nodes'].append(nd)
        mapping[node] = i

    result['links'] = []
    for u, v, k, d in graph.edges_iter(keys=True, data=True):
        ed = {
            source: mapping[u],
            target: mapping[v],
            key: k
        }
        ed.update(d)
        result['links'].append(ed)

    return result


def serve_network(graph, serve_format=None):
    """A helper function to serialize a graph and download as a file"""
    if serve_format is None or serve_format == 'json':
        return jsonify(to_json_custom(graph))

    if serve_format == 'cx':
        return jsonify(to_cx(graph))

    if serve_format == 'jgif':
        return jsonify(to_jgif(graph))

    if serve_format == 'bytes':
        data = to_bytes(graph)
        return send_file(
            data,
            mimetype='application/octet-stream',
            as_attachment=True,
            attachment_filename='graph.gpickle'
        )

    if serve_format == 'bel':
        serialize_authors(graph)
        data = '\n'.join(to_bel_lines(graph))
        return Response(data, mimetype='text/plain')

    if serve_format == 'graphml':
        bio = BytesIO()
        to_graphml(graph, bio)
        bio.seek(0)
        data = StringIO(bio.read().decode('utf-8'))
        return send_file(data, mimetype='text/xml', attachment_filename='graph.graphml', as_attachment=True)

    if serve_format == 'sif':
        bio = BytesIO()
        to_sif(graph, bio)
        bio.seek(0)
        data = StringIO(bio.read().decode('utf-8'))
        return send_file(data, attachment_filename="graph.sif", as_attachment=True)

    if serve_format == 'csv':
        bio = BytesIO()
        to_csv(graph, bio)
        bio.seek(0)
        data = StringIO(bio.read().decode('utf-8'))
        return send_file(data, attachment_filename="graph.tsv", as_attachment=True)

    if serve_format == 'gsea':
        bio = BytesIO()
        to_gsea(graph, bio)
        bio.seek(0)
        data = StringIO(bio.read().decode('utf-8'))
        return send_file(data, attachment_filename="graph.tsv", as_attachment=True)

    raise TypeError('{} is not a valid format'.format(serve_format))
