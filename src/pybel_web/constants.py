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



