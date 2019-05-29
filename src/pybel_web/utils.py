# -*- coding: utf-8 -*-

"""Utilities for BEL Commons."""

import logging
from typing import Dict, List

from flask import request

from pybel import BELGraph
from pybel.struct.summary import get_annotation_values_by_annotation, get_annotations, get_pubmed_identifiers
from .version import VERSION

__all__ = [
    'get_version',
    'calculate_overlap_info',
    'get_tree_annotations',
    'add_edge_filter',
]

log = logging.getLogger(__name__)


def get_version() -> str:
    """Get the current BEL Commons version string."""
    return VERSION


def calculate_overlap_info(g1: BELGraph, g2: BELGraph):
    """Calculate a summary over the overlaps between two graphs."""
    g1_nodes, g2_nodes = set(g1), set(g2)
    overlap_nodes = g1 & g2

    g1_edges, g2_edges = set(g1.edges()), set(g2.edges())
    overlap_edges = g1_edges & g2_edges

    g1_citations, g2_citations = get_pubmed_identifiers(g1), get_pubmed_identifiers(g2)
    overlap_citations = g1_citations & g2_citations

    g1_annotations, g2_annotations = get_annotations(g1), get_annotations(g2)
    overlap_annotations = g1_annotations & g2_annotations

    return {
        'nodes': (len(g1_nodes), len(overlap_nodes), len(g2_nodes)),
        'edges': (len(g1_edges), len(overlap_edges), len(g2_edges)),
        'citations': (len(g1_citations), len(overlap_citations), len(g2_citations)),
        'annotations': (len(g1_annotations), len(overlap_annotations), len(g2_annotations)),
    }


def get_tree_annotations(graph: BELGraph) -> List[Dict]:
    """Build a tree structure with annotation for a given graph.

    :return: The JSON structure necessary for building the tree box
    """
    return [
        {
            'text': annotation,
            'children': [
                {
                    'text': value,
                }
                for value in sorted(values)
            ],
        }
        for annotation, values in sorted(get_annotation_values_by_annotation(graph).items())
    ]


def add_edge_filter(edge_query, limit_default=None, offset_default=None):
    limit = request.args.get('limit', type=int, default=limit_default)
    offset = request.args.get('offset', type=int, default=offset_default)

    if limit is not None:
        edge_query = edge_query.limit(limit)

    if offset is not None:
        edge_query = edge_query.offset(offset)

    return edge_query

