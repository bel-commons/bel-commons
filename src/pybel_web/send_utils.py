# -*- coding: utf-8 -*-

import logging
from io import BytesIO, StringIO
from operator import methodcaller
from typing import Optional

from flask import Response, jsonify, send_file

from pybel import BELGraph, to_bel_lines, to_bytes, to_csv, to_graphml, to_gsea, to_jgif, to_json, to_sif
from pybel.canonicalize import edge_to_bel
from pybel.constants import (
    CAUSAL_DECREASE_RELATIONS, CAUSAL_INCREASE_RELATIONS, DECREASES, FUSION, INCREASES, MEMBERS, RELATION,
    TWO_WAY_RELATIONS, VARIANTS,
)
from pybel.struct.summary import get_pubmed_identifiers
from pybel_tools.mutation.metadata import serialize_authors

try:
    from pybel_cx import to_cx
except ImportError:
    to_cx = None

__all__ = [
    'to_json_custom',
    'serve_network',
]

log = logging.getLogger(__name__)


def to_json_custom(graph: BELGraph, id_key: str = 'id', source_key: str = 'source', target_key: str = 'target'):
    """Prepares JSON for the biological network explorer.

    :param id_key: The key to use for the identifier of a node, which is calculated with an enumeration
    :param source_key: The key to use for the source node
    :param target_key: The key to use for the target node
    :rtype: dict
    """
    result = {}
    mapping = {}

    result['nodes'] = []
    for i, node in enumerate(sorted(graph, key=methodcaller('as_bel'))):
        data = node.copy()
        data[id_key] = node.sha512
        data['bel'] = node.as_bel()
        if any(attr in data for attr in (VARIANTS, FUSION, MEMBERS)):
            data['cname'] = data['bel']

        result['nodes'].append(data)
        mapping[node] = i

    edge_set = set()

    rr = {}

    for u, v, key, data in graph.edges(keys=True, data=True):
        if data[RELATION] in TWO_WAY_RELATIONS and (u, v) != tuple(sorted((u, v), key=methodcaller('as_bel'))):
            continue  # don't keep two way edges twice

        entry_code = u, v

        if entry_code not in edge_set:  # Avoids duplicate sending multiple edges between nodes with same relation
            rr[entry_code] = {
                source_key: mapping[u],
                target_key: mapping[v],
                'contexts': []
            }

            edge_set.add(entry_code)

        payload = {
            'id': key,
            'bel': edge_to_bel(u, v, data)
        }
        payload.update(data)

        if data[RELATION] in CAUSAL_INCREASE_RELATIONS:
            rr[entry_code][RELATION] = INCREASES

        elif data[RELATION] in CAUSAL_DECREASE_RELATIONS:
            rr[entry_code][RELATION] = DECREASES

        rr[entry_code]['contexts'].append(payload)

    result['links'] = list(rr.values())

    return result


def serve_network(graph: BELGraph, serve_format: Optional[str] = None) -> Response:
    """Help serialize a graph and download as a file."""
    if serve_format is None:
        return jsonify(to_json_custom(graph))

    elif serve_format in {'nl', 'nodelink', 'json'}:
        return jsonify(to_json(graph))

    elif serve_format == 'cx' and to_cx is not None:
        return jsonify(to_cx(graph))

    elif serve_format == 'jgif':
        return jsonify(to_jgif(graph))

    elif serve_format == 'bytes':
        data = BytesIO(to_bytes(graph))
        return send_file(
            data,
            mimetype='application/octet-stream',
            as_attachment=True,
            attachment_filename='{}.gpickle'.format(graph.name)
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
            attachment_filename='{}.graphml'.format(graph.name),
            as_attachment=True
        )

    elif serve_format == 'sif':
        bio = StringIO()
        to_sif(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            attachment_filename="{}.sif".format(graph.name),
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
            attachment_filename="{}.tsv".format(graph.name),
            as_attachment=True
        )

    elif serve_format == 'gsea':
        bio = StringIO()
        to_gsea(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            attachment_filename="{}.grp".format(graph.name),
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
            attachment_filename="{}-citations.txt".format(graph.name),
            as_attachment=True
        )

    raise TypeError('{} is not a valid format'.format(serve_format))
