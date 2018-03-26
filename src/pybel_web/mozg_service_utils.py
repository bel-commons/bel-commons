# -*- coding: utf-8 -*-

import pandas as pd

from pybel.constants import ANNOTATIONS
from pybel.struct.summary import get_annotation_values_by_annotation
from pybel_tools.selection import get_subgraph_by_edge_filter, get_subgraph_by_neighborhood, search_node_names


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
    :rtype: (pybel.BELGraph, tuple, tuple, int) -> bool
    """

    def annotation_dict_filter(graph, u, v, k):
        """Returns if any of the annotations and values match up"""
        return _annotation_dict_filter_helper(graph.edge[u][v][k], annotations, values)

    return annotation_dict_filter


def make_graph(graph, annotations, values):
    """Makes a graph, based on nodes as well as using annotations and values

    :param pybel.BELGraph graph:
    :param annotations:
    :param values:
    :rtype: pybel.BELGraph
    """

    nodes = list(search_node_names(graph, values))

    neighborhoods = get_subgraph_by_neighborhood(graph, nodes)

    filtered_graph = get_subgraph_by_edge_filter(graph, build_annotation_search_filter(annotations, values))

    if neighborhoods is None:
        result = filtered_graph
    elif filtered_graph is None:
        result = neighborhoods
    else:
        result = neighborhoods + filtered_graph

    return result


def do_simple_complicated_filter(fd, data):
    """

    :param dict[str,str] fd: An annotations dictionary to use to filter
    :param dict data: Data from service to be filtered
    :rtype: bool
    """

    annotation, value = zip(*fd.items())
    return get_subgraph_by_edge_filter(data, build_annotation_search_filter(annotation, value))



def do_more_complicated_filter(data, fdl):
    """Builds an annotation search filter for Mozg that takes a list of dicts with annotations/values
        build_more_complicated_filter

        :param list[dict] data: A graph data
        :param list[dict] fdl: A list of the annotations dictionaries to use to filter
        :rtype: (pybel.BELGraph, tuple, tuple, int) -> bool
        """

    return any(
        do_simple_complicated_filter(fd, data)
        for fd in fdl
    )


def build_one_region_and_annotations_filter(fdl):
    """Builds an annotation search filter for Mozg that takes a list of dicts with annotations/values
    build_more_complicated_filter

    :param list[dict] fdl: A list of the annotations dictionaries to use to filter
    :rtype: (pybel.BELGraph, tuple, tuple, int) -> bool
    """

    def my_filter(graph, u, v, k):
        data = graph[u][v][k]
        return do_more_complicated_filter(data, fdl)

    return my_filter


def get_rc_tree_annotations(graph):
    """Builds rc-tree structure with annotation for a given graph

    :param pybel.BELGraph graph: A BEL Graph
    :return: The JSON structure necessary for building the rc-tree
    :rtype: list[dict]
    """
    annotations = get_annotation_values_by_annotation(graph)
    return [
        {
            'title': annotation,
            'key': annotation,
            # 'key': '{annotation}__{bits}'.format(annotation=annotation, bits=getrandbits(16)),
            'search': annotation.lower(),
            'children': [
                {
                    'title': value,
                    'key': value,
                    # 'key': '{value}__{bits}'.format(value=value, bits=getrandbits(16)),
                    'search': value.lower()
                }
                for value in sorted(values)
            ]
        }
        for annotation, values in sorted(annotations.items())
    ]

def xsls_to_dct(file_name):
    """Creates a data dictionary from xlsx files, where keys are indexes, and values are columns

    :param file_name: xlsx file
    :rtype: dict
    """

    df = pd.read_excel(file_name)
    return df.set_index('ROIs').T.to_dict()

def get_mapping_dct(file_name, index_col, acronym_col):
    """Creates a mapping dictionary

    :param file_name: csv file
    :rtype: dict
    """
    df = pd.read_csv('./mapping_npao_to_aba.csv', index_col=index_col)
    return df.to_dict()[acronym_col]
