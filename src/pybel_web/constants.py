# -*- coding: utf-8 -*-

import os
from logging import getLogger

from pybel.constants import PYBEL_DATA_DIR

PYBEL_WEB_VERSION = '0.2.1-dev'

integrity_message = "A graph with the same name ({}) and version ({}) already exists. If there have been changes since the last version, try bumping the version number."
reporting_log = getLogger('pybelreporting')

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
