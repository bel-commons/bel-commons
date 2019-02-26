# -*- coding: utf-8 -*-

"""Constants for building the niological network explorer's transformations toolbox."""

from typing import List, Tuple

from pybel.struct.pipeline.decorators import mapped

# Default NetworkX explorer toolbox functions (name, button text, description)
_explorer_toolbox = (
    ('collapse_to_genes', 'Collapse to Genes', 'Collapse proteins and RNAs to genes'),
    ('collapse_all_variants', 'Collapse Variants', 'Collapse Variants to their Parent Nodes'),
    ('collapse_to_protein_interactions', 'Protein Interaction Network',
     'Reduce the Network to Interactions between Proteins'),
    ('enrich_protein_and_rna_origins', 'Expand Protein Origins',
     'Adds RNAs corresponding to Proteins, then adds Genes corresponding to RNAs and miRNAs'),
    ('prune_protein_rna_origins', 'Prune Genes/RNAs',
     'Delete genes/RNAs that only have transcription/translation edges'),
    ('expand_periphery', 'Expand Periphery', 'Expand the periphery of the network'),
    ('expand_internal', 'Expand Internal', 'Adds missing edges between nodes in the network'),
    ('remove_isolated_nodes', 'Remove Isolated Nodes', 'Remove from the network all isolated nodes'),
    ('get_largest_component', 'Get Largest Component', 'Retain only the largest component and removes all others'),
    ('enrich_unqualified', 'Enrich unqualified edges', 'Adds unqualified edges from the universe'),
    ('remove_associations', 'Remove Associations', 'Remove associative relations'),
    ('remove_pathologies', 'Remove Pathologies', 'Removes all pathology nodes'),
)

_bio2bel_functions = (
    (
        'enrich_rnas',
        'Enrich RNA controllers from miRTarBase',
        'Adds the miRNA controllers of RNA nodes from miRTarBase'
    ), (
        'enrich_mirnas',
        'Enrich miRNA targets',
        'Adds the RNA targets of miRNA nodes from miRTarBase'
    ), (
        'enrich_genes_with_families',
        'Enrich Genes with Gene Family Membership',
        'Adds the parents of HGNC Gene Families'
    ), (
        'enrich_families_with_genes',
        'Enrich Gene Family Membership',
        'Adds the children to HGNC gene familes'
    ), (
        'enrich_bioprocesses',
        'Enrich Biological Process Hierarchy',
        'Adds parent biological processes'
    ), (
        'enrich_chemical_hierarchy',
        'Enrich Chemical Hierarchy',
        'Adds parent chemical entries'
    ), (
        'enrich_proteins_with_enzyme_families',
        'Add Enzyme Class Members',
        'Adds enzyme classes for each protein'
    ), (
        'enrich_enzymes',
        'Enrich Enzyme Classes',
        'Adds proteins corresponding to present ExPASy Enzyme codes'
    )
)


def _function_is_registered(name: str) -> bool:
    return name in mapped


def get_explorer_toolbox() -> List[Tuple[str, str, str]]:
    """Get the explorer toolbox list."""
    explorer_toolbox = list(_explorer_toolbox)
    explorer_toolbox.extend(
        (func_name, title, description)
        for func_name, title, description in _bio2bel_functions
        if _function_is_registered(func_name)
    )
    return explorer_toolbox
