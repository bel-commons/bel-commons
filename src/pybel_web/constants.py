# -*- coding: utf-8 -*-

from logging import getLogger

import os

from pybel.constants import PYBEL_LOG_DIR
from pybel_tools.constants import BMS_BASE

PYBEL_WEB_VERSION = '0.1.1'

PYBEL_CACHE_CONNECTION = 'pybel_cache_connection'
PYBEL_DEFINITION_MANAGER = 'pybel_definition_manager'
PYBEL_METADATA_PARSER = 'pybel_metadata_parser'
PYBEL_GRAPH_MANAGER = 'pybel_graph_manager'
SECRET_KEY = 'SECRET_KEY'

PYBEL_GITHUB_CLIENT_ID = 'PYBEL_GITHUB_CLIENT_ID'
PYBEL_GITHUB_CLIENT_SECRET = 'PYBEL_GITHUB_CLIENT_SECRET'
PYBEL_WEB_PASSWORD_SALT = 'PYBEL_WEB_PASSWORD_SALT'

integrity_message = "A graph with the same name ({}) and version ({}) already exists. If there have been changes since the last version, try bumping the version number."
reporting_log = getLogger('pybelreporting')

DEFAULT_SERVICE_URL = 'http://pybel.scai.fraunhofer.de'

DICTIONARY_SERVICE = 'dictionary_service'
DEFAULT_TITLE = 'Biological Network Explorer'

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

log_runner_path = os.path.join(PYBEL_LOG_DIR, 'pybel_web_runner.txt')
log_worker_path = os.path.join(PYBEL_LOG_DIR, 'pybel_web_worker.txt')

CHARLIE_EMAIL = 'charles.hoyt@scai.fraunhofer.de'
DANIEL_EMAIL = 'daniel.domingo.fernandez@scai.fraunhofer.de'
ALEX_EMAIL = 'aliaksandr.masny@scai.fraunhofer.de'

BMS_IS_AVAILABLE = BMS_BASE in os.environ
