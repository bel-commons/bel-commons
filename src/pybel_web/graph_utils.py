# -*- coding: utf-8 -*-

from pybel.constants import ANNOTATIONS


def build_annotation_search_filter(annotations, values):
    """Builds an annotation search filter for Mozg

    :param list[str] annotations: A list of the annotations to search
    :param list[str] values: A list of values to match against any annotations
    :rtype: bool
    """

    def annotation_dict_filter(graph, u, v, k, d):
        """Returns if any of the annotations and values match up"""
        if ANNOTATIONS not in d:
            return False

        for annotation in annotations:
            if annotation not in d[ANNOTATIONS]:
                continue
            if any(value in d[ANNOTATIONS][annotation] for value in values):
                return True

        return False

    return annotation_dict_filter
