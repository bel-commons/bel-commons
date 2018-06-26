# -*- coding: utf-8 -*-

"""Constants for BEL Commons."""

import os

from pybel.constants import PYBEL_DIR, config
from pybel.struct.pipeline import mapped

VERSION = '0.2.4'

# Configuration parameter names
PYBEL_WEB_ADMIN_EMAIL = 'PYBEL_WEB_ADMIN_EMAIL'
PYBEL_WEB_ADMIN_PASSWORD = 'PYBEL_WEB_ADMIN_PASSWORD'
PYBEL_WEB_CONFIG_JSON = 'PYBEL_WEB_CONFIG_JSON'
PYBEL_WEB_CONFIG_OBJECT = 'PYBEL_WEB_CONFIG_OBJECT'

PYBEL_WEB_USER_MANIFEST = 'PYBEL_WEB_USER_MANIFEST'

# App setup configuration
PYBEL_WEB_REGISTER_EXAMPLES = 'PYBEL_WEB_EXAMPLES'
PYBEL_WEB_REGISTER_ADMIN = 'PYBEL_WEB_REGISTER_ADMIN'
PYBEL_WEB_REGISTER_USERS = 'PYBEL_WEB_REGISTER_USERS'
PYBEL_WEB_REGISTER_TRANSFORMATIONS = 'PYBEL_WEB_REGISTER_TRANSFORMATIONS'

PYBEL_WEB_USE_PARSER_API = 'PYBEL_WEB_USE_PARSER_API'
PYBEL_WEB_STARTUP_NOTIFY = 'PYBEL_WEB_STARTUP_NOTIFY'
SENTRY_DSN = 'SENTRY_DSN'
SWAGGER = 'SWAGGER'
SQLALCHEMY_DATABASE_URI = 'SQLALCHEMY_DATABASE_URI'
SQLALCHEMY_TRACK_MODIFICATIONS = 'SQLALCHEMY_TRACK_MODIFICATIONS'
CELERY_BROKER_URL = 'CELERY_BROKER_URL'
MAIL_DEFAULT_SENDER = 'MAIL_DEFAULT_SENDER'
MAIL_SERVER = 'MAIL_SERVER'
SERVER_NAME = 'SERVER_NAME'

integrity_message = "A graph with the same name ({}) and version ({}) already exists. If there have been changes " \
                    "since the last version, try bumping the version number."

#: Label for nodes' differential gene expression values
LABEL = 'dgxa'

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


def get_admin_email():
    rv = config.get(PYBEL_WEB_ADMIN_EMAIL)
    if rv is None:
        raise RuntimeError('{} is not set'.format(PYBEL_WEB_ADMIN_EMAIL))
    return rv


def get_admin_password():
    rv = config.get(PYBEL_WEB_ADMIN_PASSWORD)
    if rv is None:
        raise RuntimeError('{} is not set'.format(PYBEL_WEB_ADMIN_PASSWORD))
    return rv


SWAGGER_CONFIG = {
    'title': 'BEL Commons API',
    'description': 'This exposes the functions of PyBEL as a RESTful API',
    'contact': {
        'responsibleOrganization': 'Fraunhofer SCAI',
        'responsibleDeveloper': 'Charles Tapley Hoyt',
        'email': 'charles.hoyt@scai.fraunhofer.de',
        'url': 'https://www.scai.fraunhofer.de/de/geschaeftsfelder/bioinformatik.html',
    },
    'version': '0.1.0',
}

merged_document_folder = os.path.join(PYBEL_DIR, 'pbw_merged_documents')
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
    ('remove_associations', 'Remove Associations', 'Remove associative relations'),
    ('remove_pathologies', 'Remove Pathologies', 'Removes all pathology nodes'),
)


def _function_is_registered(name):
    return name in mapped


def get_explorer_toolbox():
    """Gets the explorer toolbox list

    :rtype: list[tuple[str,str,str]]
    """
    explorer_toolbox = list(_explorer_toolbox)

    if _function_is_registered('enrich_rnas'):
        explorer_toolbox.append((
            'enrich_rnas',
            'Enrich RNA controllers',
            'Adds the miRNA controllers of RNA nodes from miRTarBase'
        ))

    if _function_is_registered('enrich_mirnas'):
        explorer_toolbox.append((
            'enrich_mirnas',
            'Enrich miRNA targets',
            'Adds the RNA targets of miRNA nodes from miRTarBase'
        ))

    if _function_is_registered('enrich_genes_with_families'):
        explorer_toolbox.append((
            'enrich_genes_with_families',
            'Enrich Genes with Gene Family Membership',
            'Adds the parents of HGNC Gene Families'
        ))

    if _function_is_registered('enrich_families_with_genes'):
        explorer_toolbox.append((
            'enrich_families_with_genes',
            'Enrich Gene Family Membership',
            'Adds the children to HGNC gene familes'
        ))

    if _function_is_registered('enrich_bioprocesses'):
        explorer_toolbox.append((
            'enrich_bioprocesses',
            'Enrich Biological Process Hierarchy',
            'Adds parent biological processes'
        ))

    if _function_is_registered('enrich_chemical_hierarchy'):
        explorer_toolbox.append((
            'enrich_chemical_hierarchy',
            'Enrich Chemical Hierarchy',
            'Adds parent chemical entries'
        ))

    if _function_is_registered('enrich_proteins_with_enzyme_families'):
        explorer_toolbox.append((
            'enrich_proteins_with_enzyme_families',
            'Add Enzyme Class Members',
            'Adds enzyme classes for each protein'
        ))

    if _function_is_registered('enrich_enzymes'):
        explorer_toolbox.append((
            'enrich_enzymes',
            'Enrich Enzyme Classes',
            'Adds proteins corresponding to present ExPASy Enzyme codes'
        ))

    return explorer_toolbox
