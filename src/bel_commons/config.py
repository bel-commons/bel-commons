# -*- coding: utf-8 -*-

"""Configurations for BEL Commons.

Resources:

- https://stackoverflow.com/questions/12078667/how-do-you-unit-test-a-celery-task
- https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/
"""

import os
from typing import Optional

from easy_config import EasyConfig

HOME = os.path.expanduser('~')
CONFIG_DIRECTORY = os.path.join(HOME, '.config')


class PyBELConfig(EasyConfig):
    """Configuration for PyBEL."""

    NAME = 'pybel'
    FILES = [os.path.join(CONFIG_DIRECTORY, 'pybel', 'config.ini')]

    # Connection to the database
    connection: Optional[str] = None


class BELCommonsConfig(EasyConfig):
    """Configuration for BEL Commons."""

    NAME = 'bel_commons'
    FILES = [
        os.path.join(CONFIG_DIRECTORY, 'bel_commons', 'config.ini'),
    ]

    #: Should example graphs be automatically included?
    register_examples: bool = False
    #: Path to user manifest file
    register_users: Optional[str] = None
    register_admin: bool = True
    register_transformations: bool = True

    """Which parts of BEL Commons should run?"""
    enable_uploader: bool = False
    enable_parser: bool = False
    enable_analysis: bool = False
    enable_curation: bool = False


class Config:
    """This is the default configuration to be used in a development environment.

    It assumes you have:

    - SQLite for the PyBEL Cache on localhost
    - RabbitMQ or another message broker supporting the AMQP protocol running on localhost

    If it's running on redis, use ``CELERY_BROKER_URL = 'redis://XXX:6379'`` where XXX is the name of the container
    in docker-compose or localhost if running locally.
    """

    #: The Flask app secret key.
    SECRET_KEY = os.environ.get('BEL_COMMONS_SECRET_KEY')
    DEBUG = os.environ.get('BEL_COMMONS_DEBUG', False)
    TESTING = os.environ.get('BEL_COMMONS_TESTING', False)

    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://localhost')
    CELERY_BACKEND_URL = os.environ.get('CELERY_BACKEND_URL', 'redis://localhost')

    SECURITY_REGISTERABLE = True
    SECURITY_CONFIRMABLE = False
    SECURITY_SEND_REGISTER_EMAIL = False
    SECURITY_RECOVERABLE = True
    #: What hash algorithm should we use for passwords
    SECURITY_PASSWORD_HASH = 'pbkdf2_sha512'
    #: What salt should we use to hash passwords? DEFINITELY CHANGE THIS
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT')
