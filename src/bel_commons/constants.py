# -*- coding: utf-8 -*-

"""Constants for BEL Commons."""

BEL_COMMONS_STARTUP_NOTIFY = 'BEL_COMMONS_STARTUP_NOTIFY'
SENTRY_DSN = 'SENTRY_DSN'
SWAGGER = 'SWAGGER'
SQLALCHEMY_DATABASE_URI = 'SQLALCHEMY_DATABASE_URI'
SQLALCHEMY_TRACK_MODIFICATIONS = 'SQLALCHEMY_TRACK_MODIFICATIONS'
MAIL_DEFAULT_SENDER = 'MAIL_DEFAULT_SENDER'
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
