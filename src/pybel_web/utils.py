# -*- coding: utf-8 -*-

import base64
import logging
from io import BytesIO

import pybel
from pybel.struct.summary import get_annotation_values_by_annotation, get_pubmed_identifiers
from pybel_tools.summary import get_annotations
from .constants import VERSION

__all__ = [
    'calculate_overlap_dict',
    'get_tree_annotations',
    'get_version',
]

log = logging.getLogger(__name__)


def calculate_overlap_dict(g1, g2, g1_label=None, g2_label=None):
    """Creates a dictionary of images depicting the graphs' overlaps in multiple categories

    :param pybel.BELGraph g1: A BEL graph
    :param pybel.BELGraph g2: A BEL graph
    :param str g1_label: The label for the first fraph
    :param str g2_label: The label for the first fraph
    :return: A dictionary containing important information for displaying base64 images
    :rtype: dict
    """
    set_labels = (g1_label, g2_label)

    import matplotlib
    # See: http://matplotlib.org/faq/usage_faq.html#what-is-a-backend
    matplotlib.use('AGG')

    from matplotlib_venn import venn2
    import matplotlib.pyplot as plt

    plt.clf()
    plt.cla()
    plt.close()

    nodes_overlap_file = BytesIO()
    g1_nodes = set(g1)
    g2_nodes = set(g2)
    venn2(
        [g1_nodes, g2_nodes],
        set_labels=set_labels
    )
    plt.savefig(nodes_overlap_file, format='png')
    nodes_overlap_file.seek(0)
    nodes_overlap_data = base64.b64encode(nodes_overlap_file.getvalue())

    plt.clf()
    plt.cla()
    plt.close()

    edges_overlap_file = BytesIO()
    venn2(
        [set(g1.edges_iter()), set(g2.edges_iter())],
        set_labels=set_labels
    )
    plt.savefig(edges_overlap_file, format='png')
    edges_overlap_file.seek(0)
    edges_overlap_data = base64.b64encode(edges_overlap_file.getvalue())

    plt.clf()
    plt.cla()
    plt.close()

    citations_overlap_file = BytesIO()
    venn2(
        [get_pubmed_identifiers(g1), get_pubmed_identifiers(g2)],
        set_labels=set_labels

    )
    plt.savefig(citations_overlap_file, format='png')
    citations_overlap_file.seek(0)
    citations_overlap_data = base64.b64encode(citations_overlap_file.getvalue())

    plt.clf()
    plt.cla()
    plt.close()

    annotations_overlap_file = BytesIO()
    g1_annotations = get_annotations(g1)
    g2_annotations = get_annotations(g2)
    venn2(
        [g1_annotations, g2_annotations],
        set_labels=set_labels

    )
    plt.savefig(annotations_overlap_file, format='png')
    annotations_overlap_file.seek(0)
    annotations_overlap_data = base64.b64encode(annotations_overlap_file.getvalue())

    return {
        'nodes': nodes_overlap_data.decode('utf-8'),
        'edges': edges_overlap_data.decode('utf-8'),
        'citations': citations_overlap_data.decode('utf-8'),
        'annotations': annotations_overlap_data.decode('utf-8')
    }


def get_tree_annotations(graph):
    """Build a tree structure with annotation for a given graph.

    :param pybel.BELGraph graph: A BEL Graph
    :return: The JSON structure necessary for building the tree box
    :rtype: list[dict]
    """
    annotations = get_annotation_values_by_annotation(graph)
    return [
        {
            'text': annotation,
            'children': [
                {'text': value}
                for value in sorted(values)
            ]
        }
        for annotation, values in sorted(annotations.items())
    ]


def get_version():
    """Gets the current BEL Commons version

    :return: The current BEL Commons version
    :rtype: str
    """
    return VERSION
