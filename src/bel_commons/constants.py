# -*- coding: utf-8 -*-

"""Constants for BEL Commons."""

# Configuration parameter names
BEL_COMMONS_ADMIN_EMAIL = 'BEL_COMMONS_ADMIN_EMAIL'
BEL_COMMONS_ADMIN_PASSWORD = 'BEL_COMMONS_ADMIN_PASSWORD'
BEL_COMMONS_CONFIG_JSON = 'BEL_COMMONS_CONFIG_JSON'
BEL_COMMONS_CONFIG_OBJECT = 'BEL_COMMONS_CONFIG_OBJECT'

BEL_COMMONS_USER_MANIFEST = 'BEL_COMMONS_USER_MANIFEST'

BEL_COMMONS_USE_PARSER_API = 'BEL_COMMONS_USE_PARSER_API'
BEL_COMMONS_STARTUP_NOTIFY = 'BEL_COMMONS_STARTUP_NOTIFY'
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

SWAGGER_CONFIG = {
    'title': 'BEL Commons API',
    'description': 'This exposes the functions of PyBEL as a RESTful API',
    'contact': {
        'responsibleDeveloper': 'Charles Tapley Hoyt',
        'email': 'cthoyt@gmail.com',
    },
    'version': '0.1.0',
}
