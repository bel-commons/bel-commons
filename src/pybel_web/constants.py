# -*- coding: utf-8 -*-

import os

from pybel.constants import PYBEL_DATA_DIR
from pybel_tools.pipeline import function_is_registered

PYBEL_WEB_VERSION = '0.2.2-dev'

integrity_message = "A graph with the same name ({}) and version ({}) already exists. If there have been changes since the last version, try bumping the version number."

NETWORK_ID = 'network_id'
SOURCE_NODE = 'source'
TARGET_NODE = 'target'
UNDIRECTED = 'undirected'
FORMAT = 'format'
PATHOLOGY_FILTER = 'pathology_filter'
PATHS_METHOD = 'paths_method'
QUERY = 'query'
AND = 'and'
RANDOM_PATH = 'random'

BLACK_LIST = {
    NETWORK_ID,
    SOURCE_NODE,
    TARGET_NODE,
    UNDIRECTED,
    FORMAT,
    PATHOLOGY_FILTER,
    PATHS_METHOD,
    QUERY,
    AND,
}

CHARLIE_EMAIL = 'charles.hoyt@scai.fraunhofer.de'
DANIEL_EMAIL = 'daniel.domingo.fernandez@scai.fraunhofer.de'
ALEX_EMAIL = 'aliaksandr.masny@scai.fraunhofer.de'

merged_document_folder = os.path.join(PYBEL_DATA_DIR, 'pbw_merged_documents')

if not os.path.exists(merged_document_folder):
    os.mkdir(merged_document_folder)

# Default networkx explorer toolbox functions (name, button text, description)
_explorer_toolbox = (
    ('collapse_by_central_dogma_to_genes', 'Central Dogma to Genes', 'Collapse proteins and RNAs to genes'),
    ('collapse_all_variants', 'Collapse Variants', 'Collapse Variants to their Parent Nodes'),
    ('collapse_to_protein_interactions', 'Protein Interaction Network',
     'Reduce the Network to Interactions between Proteins'),
    ('infer_central_dogma', 'Infer Central Dogma',
     'Adds RNAs corresponding to Proteins, then adds Genes corresponding to RNAs and miRNAs'),
    ('prune_central_dogma', 'Prune Central Dogma', 'Prunes genes, then RNA'),
    ('expand_periphery', 'Expand Periphery', 'Expand the periphery of the network'),
    ('expand_internal', 'Expand Internal', 'Adds missing edges between nodes in the network'),
    ('remove_isolated_nodes', 'Remove Isolated Nodes', 'Remove from the network all isolated nodes'),
    ('get_largest_component', 'Get Largest Component', 'Retain only the largest component and removes all others'),
    ('enrich_unqualified', 'Enrich unqualified edges', 'Adds unqualified edges from the universe'),
    #('remove_pathologies', 'Remove Pathologies', 'Removes all pathology nodes'), # TODO
    #('remove_associative', 'Remove Associative Edges', 'Removes all associative edges'), # TODO
)


def get_explorer_toolbox():
    """Gets the explorer toolbox list

    :rtype: list[tuple[str,str,str]]
    """
    explorer_toolbox = list(_explorer_toolbox)

    if function_is_registered('enrich_rnas'):
        explorer_toolbox.append((
            'enrich_rnas',
            'Enrich RNA controllers',
            'Adds the miRNA controllers of RNA nodes from miRTarBase'
        ))

    if function_is_registered('enrich_mirnas'):
        explorer_toolbox.append((
            'enrich_mirnas',
            'Enrich miRNA targets',
            'Adds the RNA targets of miRNA nodes from miRTarBase'
        ))

    if function_is_registered('enrich_genes_with_families'):
        explorer_toolbox.append((
            'enrich_genes_with_families',
            'Enrich Genes with Gene Family Membership',
            'Adds the parents of HGNC Gene Families'
        ))

    if function_is_registered('enrich_families_with_genes'):
        explorer_toolbox.append((
            'enrich_families_with_genes',
            'Enrich Gene Family Membership',
            'Adds the children to HGNC gene familes'
        ))

    if function_is_registered('enrich_bioprocesses'):
        explorer_toolbox.append((
            'enrich_bioprocesses',
            'Enrich Biological Process Hierarchy',
            'Adds parent biological processes'
        ))

    if function_is_registered('enrich_chemical_hierarchy'):
        explorer_toolbox.append((
            'enrich_chemical_hierarchy',
            'Enrich Chemical Hierarchy',
            'Adds parent chemical entries'
        ))

    return explorer_toolbox
