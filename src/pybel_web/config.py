# -*- coding: utf-8 -*-

"""Configurations for PyBEL Web.

Resources:

- https://stackoverflow.com/questions/12078667/how-do-you-unit-test-a-celery-task
- https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/
"""

import os
from typing import Optional

from easy_config import EasyConfig


class PyBELWebConfig(EasyConfig):
    """Configuration for BEL Commons."""

    NAME = 'pybel_web'
    FILES = [os.path.join(os.path.expanduser('~'), '.config', 'pybel-web', 'config.ini')]

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
    """This is the default configuration to be used in a development environment. It assumes you have:
    
    - SQLite for the PyBEL Cache on localhost
    - RabbitMQ or another message broker supporting the AMQP protocol running on localhost

    If it's running on redis, use ``CELERY_BROKER_URL = 'redis://XXX:6379'`` where XXX is the name of the container
    in docker-compose or localhost if running locally.
    """
    #: The Flask app secret key. CHANGE THIS
    SECRET_KEY = os.environ.get('SECRET_KEY', 'pybel_not_default_key1234567890')
    DEBUG = os.environ.get('PYBEL_WEB_DEBUG', False)
    TESTING = os.environ.get('PYBEL_WEB_TESTING', False)

    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://localhost')
    CELERY_BACKEND_URL = os.environ.get('CELERY_BACKEND_URL', 'redis://localhost')

    SECURITY_REGISTERABLE = True
    SECURITY_CONFIRMABLE = False
    SECURITY_SEND_REGISTER_EMAIL = False
    SECURITY_RECOVERABLE = True
    #: What hash algorithm should we use for passwords
    SECURITY_PASSWORD_HASH = 'pbkdf2_sha512'
    #: What salt should we use to hash passwords? DEFINITELY CHANGE THIS
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT', 'pybel_not_default_salt1234567890')
