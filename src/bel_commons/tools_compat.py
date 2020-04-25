# -*- coding: utf-8 -*-

"""Compatibility layer for PyBEL Tools."""

from pybel_tools import get_version as get_tools_version
from pybel_tools.analysis.heat import RESULT_LABELS, calculate_average_scores_on_subgraphs
from pybel_tools.biogrammar.double_edges import summarize_completeness
from pybel_tools.document_utils import write_boilerplate
from pybel_tools.filters import remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import rewire_variants_to_genes
from pybel_tools.summary import (
    BELGraphSummary, get_incorrect_names_by_namespace, get_naked_names,
    get_undefined_namespace_names,
)
from pybel_tools.summary.error_summary import calculate_error_by_annotation
from pybel_tools.utils import min_tanimoto_set_similarity

__all__ = [
    'get_tools_version',
    'calculate_error_by_annotation',
    'summarize_completeness',
    'get_incorrect_names_by_namespace',
    'get_naked_names',
    'get_undefined_namespace_names',
    'RESULT_LABELS',
    'min_tanimoto_set_similarity',
    'calculate_average_scores_on_subgraphs',
    'remove_nodes_by_namespace',
    'generate_bioprocess_mechanisms',
    'overlay_type_data',
    'rewire_variants_to_genes',
    'BELGraphSummary',
    'write_boilerplate',
]
