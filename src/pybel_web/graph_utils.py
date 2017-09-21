# -*- coding: utf-8 -*-

from pybel.constants import ANNOTATIONS


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
