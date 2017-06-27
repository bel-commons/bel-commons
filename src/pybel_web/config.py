# -*- coding: utf-8 -*-


class Config:
    """This is the default configuration to be used in a development environment. It assumes you have:
    
    - SQLite for the PyBEL Cache on localhost
    - RabbitMQ or another message broker supporting the AMQP protocol running on localhost
    """
    #: The Flask app secret key. CHANGE THIS
    SECRET_KEY = 'pybel_default_key'
    DEBUG = False
    TESTING = False

    CELERY_BROKER_URL = 'amqp://localhost'

    SECURITY_REGISTERABLE = True
    SECURITY_CONFIRMABLE = False
    SECURITY_SEND_REGISTER_EMAIL = False
    #: What hash algorithm should we use for passwords
    SECURITY_PASSWORD_HASH = 'pbkdf2_sha512'
    #: What salt should we use to hash passwords? DEFINITELY CHANGE THIS
    SECURITY_PASSWORD_SALT = 'pybel_default_salt'

    #: A connection string for the PyBEL cache
    PYBEL_CONNECTION = None

    #: Should the version of the networks be checked on reload? This is important for maintaining the right data format
    PYBEL_DS_CHECK_VERSION = True
    #: Should networks be preloaded to the in-memory cache of the DatabaseService upon the start of the app?
    PYBEL_DS_PRELOAD = False
    #: Should the difficult to calculate (citations, centrality measures) be precalculated as well?
    PYBEL_DS_EAGER = False
    #: Should networks be saved to the edge store?
    PYBEL_USE_EDGE_STORE = False
