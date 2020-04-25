# -*- coding: utf-8 -*-

"""Configurations for BEL Commons.

Resources:

- https://stackoverflow.com/questions/12078667/how-do-you-unit-test-a-celery-task
- https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/
"""

import logging
from typing import Optional

from dataclasses_json import dataclass_json
from easy_config import EasyConfig

from pybel.config import CONFIG_FILE_PATHS

logger = logging.getLogger(__name__)

_DEFAULT_SECURITY_SALT = 'default_please_override'


@dataclass_json
class BELCommonsConfig(EasyConfig):
    """Configuration for BEL Commons.

    It assumes you have:

    - SQLite for the PyBEL Cache on localhost
    - RabbitMQ or another message broker supporting the AMQP protocol running on localhost
    """

    NAME = 'bel_commons'
    FILES = CONFIG_FILE_PATHS

    #: The Flask app secret key.
    SECRET_KEY: str

    #: Password for the butler account
    BUTLER_PASSWORD: str
    BUTLER_EMAIL: str = 'butler'
    BUTLER_NAME: str = 'BEL Commons Butler'

    #: Flask app debug mode
    DEBUG: bool = False
    #: Flask app testing mode
    TESTING: bool = False

    JSONIFY_PRETTYPRINT_REGULAR: bool = True

    #: Should celery be used?
    USE_CELERY: bool = True

    #: Celery broker URL. If it's running on redis, use ``CELERY_BROKER_URL = 'redis://XXX:6379'`` where XXX is the
    # name of the container in docker-compose or localhost if running locally.
    CELERY_BROKER_URL: str = 'amqp://localhost'

    #: Celery backend url
    CELERY_BACKEND_URL: str = 'redis://localhost'

    SECURITY_REGISTERABLE: bool = True
    SECURITY_CONFIRMABLE: bool = False
    SECURITY_SEND_REGISTER_EMAIL: bool = False
    SECURITY_RECOVERABLE: bool = True

    #: What hash algorithm should we use for passwords
    SECURITY_PASSWORD_HASH: str = 'pbkdf2_sha512'
    #: What salt should to use to hash passwords
    SECURITY_PASSWORD_SALT: str = _DEFAULT_SECURITY_SALT

    MAIL_SERVER: Optional[str] = None
    MAIL_DEFAULT_SENDER_NAME: str = 'BEL Commons'
    MAIL_DEFAULT_SENDER_EMAIL: Optional[str] = None

    #: Should example graphs be automatically included?
    register_examples: bool = True
    #: Path to user manifest file
    register_users: Optional[str] = None
    register_admin: bool = True
    register_transformations: bool = True
    WRITE_REPORTS: bool = False

    """Which parts of BEL Commons should run?"""
    enable_uploader: bool = True
    enable_parser: bool = False
    enable_analysis: bool = False
    enable_curation: bool = False

    def __post_init__(self) -> None:  # noqa: D105
        if self.SECURITY_REGISTERABLE:
            if not self.SECURITY_PASSWORD_SALT:
                raise RuntimeError('Configuration is missing SECURITY_PASSWORD_SALT')

            if self.SECURITY_PASSWORD_SALT == _DEFAULT_SECURITY_SALT:
                raise RuntimeError('Configuration is missing SECURITY_PASSWORD_SALT')

            if self.SECURITY_SEND_REGISTER_EMAIL and not self.MAIL_SERVER:
                raise ValueError('Configuration is missing MAIL_SERVER')

        if self.MAIL_SERVER is not None and self.MAIL_DEFAULT_SENDER_EMAIL is None:
            raise ValueError('MAIL_DEFAULT_SENDER_EMAIL must be set if MAIL_SERVER is set')


bel_commons_config = BELCommonsConfig.load()
