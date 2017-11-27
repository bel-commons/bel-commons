# -*- coding: utf-8 -*-

import os

from pybel.constants import PYBEL_DATA_DIR

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

explorer_toolbox = [
    ('collapse_by_central_dogma_to_genes', 'Central Dogma to Genes', 'Collapse Protein/RNA/Gene nodes to genes'),
    ('collapse_all_variants', 'Collapse Variants', 'Collapse Variants to their Parent Nodes'),
    ('collapse_to_protein_interactions', 'Protein Interaction Network',
     'Reduce the Network to Interactions between Proteins'),
    ('infer_central_dogma', 'Infer Central Dogma',
     'Adds RNAs corresponding to Proteins, then adds Genes corresponding to RNAs and miRNAs'),
    ('prune_central_dogma', 'Prune Central Dogma', 'Prunes genes, then RNA'),
    ('expand_periphery', 'Expand Periphery', 'Expand the periphery of the network'),
    ('expand_internal', 'Expand Internal', 'Adds missing edges between nodes in the network'),
    ('remove_isolated_nodes', 'Remove Isolated Nodes', 'Remove from the network all isolated nodes'),
    ('enrich_rnas', 'Enrich RNA controllers', 'Adds the miRNA controllers of RNA nodes from miRTarBase'),
    ('enrich_mirnas', 'Enrich miRNA targets', 'Adds the RNA targets of miRNA nodes from miRTarBase'),
    ('get_largest_component', 'Get Largest Component', 'Retain only the largest component and removes all others'),
    ('enrich_unqualified', 'Enrich unqualified edges',
     'Enriches the subgraph with the unqualified edges from the graph'),
]
