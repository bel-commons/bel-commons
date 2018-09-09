# -*- coding: utf-8 -*-

"""Builds a Flask extension for PyBEL.

The following resources were really helpful in learning about this:

1. https://citizen-stig.github.io/2016/02/17/using-celery-with-flask-factories.html
2. https://github.com/citizen-stig/celery-with-flask-factories
3. https://blog.miguelgrinberg.com/post/celery-and-the-flask-application-factory-pattern
4. http://flask.pocoo.org/docs/0.12/patterns/celery/
"""

import logging
import os
import socket
from getpass import getuser

import time
from flasgger import Swagger
from flask import Flask
from flask_bootstrap import Bootstrap, WebCDN
from flask_mail import Mail
from flask_security import Security
from raven.contrib.flask import Sentry
from werkzeug.routing import BaseConverter

from pybel.constants import PYBEL_CONNECTION, config as pybel_config, get_cache_connection
from pybel_web.application_utils import (
    register_admin_service, register_error_handlers, register_examples, register_transformations,
    register_users,
)
from pybel_web.constants import (
    CELERY_BROKER_URL, MAIL_DEFAULT_SENDER, MAIL_SERVER, PYBEL_WEB_CONFIG_JSON, PYBEL_WEB_CONFIG_OBJECT,
    PYBEL_WEB_REGISTER_ADMIN, PYBEL_WEB_REGISTER_EXAMPLES, PYBEL_WEB_REGISTER_TRANSFORMATIONS, PYBEL_WEB_REGISTER_USERS,
    PYBEL_WEB_STARTUP_NOTIFY, SENTRY_DSN, SERVER_NAME, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, SWAGGER,
    SWAGGER_CONFIG,
)
from pybel_web.core import PyBELSQLAlchemy as PyBELSQLAlchemyBase
from pybel_web.core.celery import PyBELCelery
from pybel_web.forms import ExtendedRegisterForm
from pybel_web.manager import WebManager
from pybel_web.utils import get_version

log = logging.getLogger(__name__)

_default_config_location = 'pybel_web.config.Config'

bootstrap = Bootstrap()
mail = Mail()
security = Security()
swagger = Swagger()
celery = PyBELCelery()

# TODO upgrade to jQuery 2?
# See: https://pythonhosted.org/Flask-Bootstrap/faq.html#why-are-you-shipping-jquery-1-instead-of-jquery-2
# app.extensions['bootstrap']['cdns']['jquery'] = jquery2_cdn
jquery2_cdn = WebCDN('//cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/')


class ListConverter(BaseConverter):
    """A converter for comma-delimited lists."""

    #: The separator for lists
    sep = ','

    def to_python(self, value: str):
        """Convert a delimited list."""
        return value.split(self.sep)

    def to_url(self, values):
        """Output a list joined with a delimiter."""
        return self.sep.join(BaseConverter.to_url(self, value) for value in values)


class IntListConverter(ListConverter):
    """A converter for comma-delimited integer lists."""

    def to_python(self, value: str):
        """Convert a delimited list of integers."""
        return [int(entry) for entry in super().to_python(value)]


def _send_startup_mail(app):
    mail_default_sender = app.config.get(MAIL_DEFAULT_SENDER)
    notify = app.config.get(PYBEL_WEB_STARTUP_NOTIFY)
    if notify:
        log.info('sending startup notification to %s', notify)
        with app.app_context():
            mail.send_message(
                subject="BEL Commons Startup",
                body="BEL Commons v{} was started on {} by {} at {}.\n\nDeployed to: {}".format(
                    get_version(),
                    socket.gethostname(),
                    getuser(),
                    time.asctime(),
                    app.config.get(SERVER_NAME)
                ),
                sender=mail_default_sender,
                recipients=[notify]
            )
        log.info('notified %s', notify)


def create_application(**kwargs) -> Flask:
    """Build a Flask app.
    
    1. Loads default config
    2. Updates with kwargs
    
    :param dict kwargs: keyword arguments to add to config
    """
    app = Flask(__name__)

    # Load default config from object
    config_object_name = os.environ.get(PYBEL_WEB_CONFIG_OBJECT)
    if config_object_name is not None:
        app.config.from_object(config_object_name)
    else:
        app.config.from_object(_default_config_location)

    # Load config from PyBEL
    app.config.update(pybel_config)
    app.config[PYBEL_CONNECTION] = get_cache_connection()  # in case config is set funny

    # Load config from JSON
    config_json_path = os.environ.get(PYBEL_WEB_CONFIG_JSON)
    if config_json_path is not None:
        if os.path.exists(config_json_path):
            log.info('importing config from %s', config_json_path)
            app.config.from_json(config_json_path)
        else:
            log.warning('configuration from environment at %s does not exist', config_json_path)

    # Load config from function's kwargs
    app.config.update(kwargs)

    # Set defaults
    app.config.setdefault(SWAGGER, SWAGGER_CONFIG)
    app.config[SQLALCHEMY_DATABASE_URI] = app.config[PYBEL_CONNECTION]
    app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)
    app.config.setdefault(PYBEL_WEB_REGISTER_TRANSFORMATIONS, True)
    app.config.setdefault(PYBEL_WEB_REGISTER_USERS, True)
    app.config.setdefault(PYBEL_WEB_REGISTER_ADMIN, True)
    app.config.setdefault(PYBEL_WEB_REGISTER_EXAMPLES, False)
    app.config.setdefault(MAIL_DEFAULT_SENDER, ("BEL Commons", 'bel-commons@scai.fraunhofer.de'))

    log.info('database: %s', app.config.get(PYBEL_CONNECTION))

    # Add converters
    app.url_map.converters['intlist'] = IntListConverter
    app.url_map.converters['list'] = ListConverter

    # Initialize extensions
    bootstrap.init_app(app)
    swagger.init_app(app)

    celery_broker_url = app.config.get(CELERY_BROKER_URL)
    if celery_broker_url is not None:
        log.info('using celery broker: %s', celery_broker_url)
        celery.init_app(app)
    else:
        log.info('not using celery broker')

    mail_server = app.config.get(MAIL_SERVER)
    if mail_server is not None:
        log.info('using mail server: %s', mail_server)
        mail.init_app(app)
        _send_startup_mail(app)

    db = PyBELSQLAlchemy(app)
    user_datastore = db.manager.user_datastore
    security.init_app(app, user_datastore, register_form=ExtendedRegisterForm)

    sentry_dsn = app.config.get(SENTRY_DSN)
    if sentry_dsn is not None:
        log.info('initiating Sentry: %s', sentry_dsn)
        sentry = Sentry(app, dsn=sentry_dsn)
    else:
        sentry = None

    register_error_handlers(app, sentry)

    if app.config[PYBEL_WEB_REGISTER_TRANSFORMATIONS]:
        register_transformations(db.manager)

    if app.config[PYBEL_WEB_REGISTER_USERS]:
        register_users(app, db.manager)

    if app.config[PYBEL_WEB_REGISTER_EXAMPLES]:
        register_examples(db.manager, user_datastore)

    if app.config[PYBEL_WEB_REGISTER_ADMIN]:
        register_admin_service(app, db.manager)

    return app


class PyBELSQLAlchemy(PyBELSQLAlchemyBase):
    """An updated PyBELSQLAlchemy using the WebManager."""
    manager_cls = WebManager
