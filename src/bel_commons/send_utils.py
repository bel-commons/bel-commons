# -*- coding: utf-8 -*-

"""Utilities for rendering BEL graphs via the response."""

from io import BytesIO, StringIO
from operator import methodcaller
from typing import Optional

from flask import Response, jsonify, send_file

from pybel import (
    BELGraph, to_bel_script_lines, to_bytes, to_csv, to_cx, to_graphml, to_gsea, to_jgif, to_nodelink,
    to_sif,
)
from pybel.canonicalize import edge_to_bel
from pybel.constants import (
    CAUSAL_DECREASE_RELATIONS, CAUSAL_INCREASE_RELATIONS, DECREASES, FUSION, INCREASES, MEMBERS, RELATION,
    TWO_WAY_RELATIONS, VARIANTS,
)
from pybel.struct.summary import get_pubmed_identifiers

__all__ = [
    'to_json_custom',
    'serve_network',
]


def to_json_custom(
    graph: BELGraph,
    id_key: str = 'id',
    source_key: str = 'source',
    target_key: str = 'target',
):
    """Prepare JSON for the biological network explorer.

    :param graph: A BEL graph
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
        data[id_key] = node.md5
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
                'contexts': [],
            }

            edge_set.add(entry_code)

        payload = {
            'id': key,
            'bel': edge_to_bel(u, v, data),
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
        return jsonify(to_nodelink(graph))

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
            attachment_filename=f'{graph.name}.bel.pickle',
        )

    elif serve_format == 'bel':
        data = '\n'.join(to_bel_script_lines(graph))
        return Response(data, mimetype='text/plain')

    elif serve_format == 'graphml':
        bio = BytesIO()
        to_graphml(graph, bio)
        bio.seek(0)
        return send_file(
            bio,
            mimetype='text/xml',
            attachment_filename=f'{graph.name}.bel.graphml',
            as_attachment=True,
        )

    elif serve_format == 'sif':
        bio = StringIO()
        to_sif(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            attachment_filename=f"{graph.name}.bel.sif",
            as_attachment=True,
        )

    elif serve_format == 'csv':
        bio = StringIO()
        to_csv(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            mimetype="text/tab-separated-values",
            attachment_filename=f"{graph.name}.bel.tsv",
            as_attachment=True,
        )

    elif serve_format == 'gsea':
        bio = StringIO()
        to_gsea(graph, bio)
        bio.seek(0)
        data = BytesIO(bio.read().encode('utf-8'))
        return send_file(
            data,
            attachment_filename=f"{graph.name}.grp",
            as_attachment=True,
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
            attachment_filename=f"{graph.name}-citations.txt",
            as_attachment=True,
        )

    raise TypeError(f'{serve_format} is not a valid format')
