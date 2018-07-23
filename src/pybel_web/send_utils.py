# -*- coding: utf-8 -*-

import logging
from io import BytesIO, StringIO

from flask import Response, jsonify, send_file

from pybel import to_bel_lines, to_bytes, to_csv, to_graphml, to_gsea, to_jgif, to_json, to_sif
from pybel.canonicalize import node_to_bel
from pybel.constants import (
    CAUSAL_DECREASE_RELATIONS, CAUSAL_INCREASE_RELATIONS, DECREASES, FUSION, HASH, INCREASES, MEMBERS, RELATION,
    TWO_WAY_RELATIONS, VARIANTS,
)
from pybel.struct.summary import get_pubmed_identifiers
from pybel.utils import hash_edge, hash_node
from pybel_cx import to_cx
from pybel_tools.mutation.metadata import serialize_authors

__all__ = [
    'to_json_custom',
    'serve_network',
]

log = logging.getLogger(__name__)


def to_json_custom(graph, _id='id', source='source', target='target'):
    """Prepares JSON for the biological network explorer

    :type graph: pybel.BELGraph
    :param str _id: The key to use for the identifier of a node, which is calculated with an enumeration
    :param str source: The key to use for the source node
    :param str target: The key to use for the target node
    :rtype: dict
    """
    result = {}

    mapping = {}

    result['nodes'] = []
    for i, node in enumerate(sorted(graph, key=hash_node)):
        nd = graph.node[node].copy()
        nd[_id] = hash_node(node)
        nd['bel'] = node_to_bel(nd)
        if VARIANTS in nd or FUSION in nd or MEMBERS in nd:
            nd['cname'] = nd['bel']
        result['nodes'].append(nd)
        mapping[node] = i

    edge_set = set()

    rr = {}

    for u, v, data in graph.edges_iter(data=True):

        if data[RELATION] in TWO_WAY_RELATIONS and (u, v) != tuple(sorted((u, v))):
            continue  # don't keep two way edges twice

        entry_code = u, v

        if entry_code not in edge_set:  # Avoids duplicate sending multiple edges between nodes with same relation
            rr[entry_code] = {
                source: mapping[u],
                target: mapping[v],
                'contexts': []
            }

            edge_set.add(entry_code)

        payload = {
            'id': data.get(HASH, hash_edge(u, v, data)),
            'bel': graph.edge_to_bel(u, v, data=data)
        }
        payload.update(data)

        if data[RELATION] in CAUSAL_INCREASE_RELATIONS:
            rr[entry_code][RELATION] = INCREASES

        elif data[RELATION] in CAUSAL_DECREASE_RELATIONS:
            rr[entry_code][RELATION] = DECREASES

        rr[entry_code]['contexts'].append(payload)

    result['links'] = list(rr.values())

    return result


def serve_network(graph, serve_format=None):
    """A helper function to serialize a graph and download as a file

    :param pybel.BELGraph graph: A BEL graph
    :param Optional[str] serve_format: The format to serve the network
    :rtype: flask.Response
    """
    if serve_format is None:
        return jsonify(to_json_custom(graph))

    elif serve_format in {'nl', 'nodelink'}:
        return jsonify(to_json(graph))

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

    elif serve_format == 'citations':
        bio = StringIO()

        for pubmed_identifier in sorted(get_pubmed_identifiers(graph)):
            print(pubmed_identifier, file=bio)

        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            mimetype="text/tab-separated-values",
            attachment_filename="citations.txt",
            as_attachment=True
        )

    raise TypeError('{} is not a valid format'.format(serve_format))
