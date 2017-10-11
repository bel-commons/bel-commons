# -*- coding: utf-8 -*-

import logging

from flask import send_file, Response, jsonify
from six import StringIO, BytesIO

from pybel import to_cx, to_bel_lines, to_graphml, to_bytes, to_csv, to_sif, to_jgif, to_gsea
from pybel.constants import GRAPH_ANNOTATION_LIST, RELATION
from pybel.utils import hash_node
from pybel_tools.mutation.metadata import serialize_authors

__all__ = [
    'to_json_custom',
    'serve_network',
]

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
    for i, node in enumerate(sorted(graph.nodes_iter(), key=hash_node)):
        nd = graph.node[node].copy()
        nd[_id] = node
        result['nodes'].append(nd)
        mapping[node] = i

    edge_set = set()

    result['links'] = []
    for u, v, k, d in graph.edges_iter(keys=True, data=True):

        if (u, v, d[RELATION]) in edge_set:  # Avoids duplicate sending multiple edges between nodes with same relation
            continue

        ed = {
            source: mapping[u],
            target: mapping[v],
            key: k,
        }
        ed.update(d)
        result['links'].append(ed)

        edge_set.add((u, v, d[RELATION]))

    return result


def serve_network(graph, serve_format=None):
    """A helper function to serialize a graph and download as a file

    :param Optional[pybel.BELGraph] graph: A BEL graph
    :param str serve_format: The format to serve the network
    :rtype: flask.Response
    """
    if serve_format is None or serve_format == 'json':
        return jsonify(to_json_custom(graph))

    elif serve_format == 'cx':
        return jsonify(to_cx(graph))

    elif serve_format == 'jgif':
        return jsonify(to_jgif(graph))

    elif serve_format == 'bytes':
        data = BytesIO(to_bytes(graph))
        return send_file(
            data,
            mimetype='application/octet-stream',
            as_attachment=True,
            attachment_filename='graph.gpickle'
        )

    elif serve_format == 'bel':
        serialize_authors(graph)
        data = '\n'.join(to_bel_lines(graph))
        return Response(data, mimetype='text/plain')

    elif serve_format == 'graphml':
        bio = BytesIO()
        to_graphml(graph, bio)
        bio.seek(0)
        return send_file(
            bio,
            mimetype='text/xml',
            attachment_filename='graph.graphml',
            as_attachment=True
        )

    elif serve_format == 'sif':
        bio = StringIO()
        to_sif(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            attachment_filename="graph.sif",
            as_attachment=True
        )

    elif serve_format == 'csv':
        bio = StringIO()
        to_csv(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            mimetype="text/tab-separated-values",
            attachment_filename="graph.tsv",
            as_attachment=True
        )

    elif serve_format == 'gsea':
        bio = StringIO()
        to_gsea(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            attachment_filename="graph.grp",
            as_attachment=True
        )

    raise TypeError('{} is not a valid format'.format(serve_format))
