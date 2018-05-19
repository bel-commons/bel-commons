# -*- coding: utf-8 -*-

import os

import pybel_tools.constants


class Config:
    """This is the default configuration to be used in a development environment. It assumes you have:
    
    - SQLite for the PyBEL Cache on localhost
    - RabbitMQ or another message broker supporting the AMQP protocol running on localhost

    If it's running on redis, use ``CELERY_BROKER_URL = 'redis://XXX:6379'`` where XXX is the name of the container
    in docker-compose or localhost if running locally.
    """
    #: The Flask app secret key. CHANGE THIS
    SECRET_KEY = 'pybel_not_default_key1234567890"'
    DEBUG = False
    TESTING = False

    CELERY_BROKER_URL = os.environ.get('PYBEL_CELERY_BROKER_URL', 'amqp://localhost')
    BMS_BASE = os.environ.get(pybel_tools.constants.BMS_BASE)

    SECURITY_REGISTERABLE = True
    SECURITY_CONFIRMABLE = False
    SECURITY_SEND_REGISTER_EMAIL = False
    SECURITY_RECOVERABLE = True
    #: What hash algorithm should we use for passwords
    SECURITY_PASSWORD_HASH = 'pbkdf2_sha512'
    #: What salt should we use to hash passwords? DEFINITELY CHANGE THIS
    SECURITY_PASSWORD_SALT = os.environ.get('PYBEL_SECURITY_PASSWORD_SALT', 'pybel_not_default_salt1234567890')

    #: A connection string for the PyBEL cache
    PYBEL_CONNECTION = None


class DockerConfig(Config):
    """Follows format from guide at
    https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/
    """
    SECRET_KEY = os.environ.get('SECRET_KEY')
    DEBUG = os.environ.get('DEBUG')
    TESTING = False

    MAIL_SERVER = None

    DB_USER = os.environ.get('PYBEL_DATABASE_USER')
    DB_PASSWORD = os.environ.get('PYBEL_DATABASE_PASSWORD')
    DB_HOST = os.environ.get('PYBEL_DATABASE_HOST')
    DB_DATABASE = os.environ.get('PYBEL_DATABASE_DATABASE')

    PYBEL_CONNECTION = 'mysql+pymysql://{user}:{password}@{host}/{database}?charset={charset}'.format(
        user=DB_USER,
        host=DB_HOST,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        charset='utf8'
    )


class UnitTestConfig(Config):
    #: See: https://stackoverflow.com/questions/12078667/how-do-you-unit-test-a-celery-task
    CELERY_ALWAYS_EAGER = True
    CELERY_BROKER_URL = 'memory'
    BROKER_BACKEND = 'memory'
    CELERY_RESULT_BACKEND = 'cache+memory://'
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True
