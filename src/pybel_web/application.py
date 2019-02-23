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
import time
from getpass import getuser
from typing import Optional

from flasgger import Swagger
from flask import Flask
from flask_bootstrap import Bootstrap, WebCDN
from flask_mail import Mail
from flask_security import Security
from raven.contrib.flask import Sentry
from werkzeug.routing import BaseConverter

from pybel.constants import PYBEL_CONNECTION, config as pybel_config, get_cache_connection
from pybel_web.application_utils import (
    register_admin_service, register_error_handlers, register_examples, register_transformations, register_users,
)
from pybel_web.config import PyBELWebConfig
from pybel_web.constants import (
    CELERY_BROKER_URL, MAIL_DEFAULT_SENDER, MAIL_SERVER, PYBEL_WEB_CONFIG_JSON, PYBEL_WEB_CONFIG_OBJECT,
    PYBEL_WEB_STARTUP_NOTIFY, SENTRY_DSN, SERVER_NAME, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, SWAGGER,
    SWAGGER_CONFIG,
)
from pybel_web.core import PyBELSQLAlchemy as PyBELSQLAlchemyBase
from pybel_web.core.celery import PyBELCelery
from pybel_web.database_service import api_blueprint
from pybel_web.forms import ExtendedRegisterForm
from pybel_web.main_service import ui_blueprint
from pybel_web.manager import WebManager
from pybel_web.utils import get_version
from pybel_web.views import (
    curation_blueprint, experiment_blueprint, help_blueprint, receiving_blueprint,
    reporting_blueprint,
)

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


def create_application(config: Optional[PyBELWebConfig] = None) -> Flask:
    """Build a Flask app."""
    app = Flask(__name__)

    if config is None:
        config = PyBELWebConfig.load()

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

    # Set Swagger defaults
    app.config.setdefault(SWAGGER, SWAGGER_CONFIG)

    # Set SQLAlchemy defaults
    app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)
    app.config[SQLALCHEMY_DATABASE_URI] = app.config[PYBEL_CONNECTION]
    log.info('database: %s', app.config.get(PYBEL_CONNECTION))

    # Set Mail defaults
    app.config.setdefault(MAIL_DEFAULT_SENDER, ("BEL Commons", 'bel-commons@scai.fraunhofer.de'))

    # Set Flask defaults
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

    # Add converters
    app.url_map.converters['intlist'] = IntListConverter
    app.url_map.converters['list'] = ListConverter

    # Initialize extensions
    bootstrap.init_app(app)
    swagger.init_app(app)

    has_celery = CELERY_BROKER_URL in app.config
    if has_celery:
        celery.init_app(app)

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

    if config.register_transformations:
        register_transformations(manager=db.manager)

    if config.register_users:
        register_users(app, user_datastore=user_datastore)

    if config.register_examples:
        register_examples(manager=db.manager, user_datastore=user_datastore)

    if config.register_admin:
        register_admin_service(app=app, manager=db.manager, user_datastore=user_datastore)

    app.register_blueprint(ui_blueprint)
    if config.enable_curation:
        app.register_blueprint(curation_blueprint)
    app.register_blueprint(help_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(reporting_blueprint)

    if has_celery:  # Requires celery!
        if config.enable_uploader:
            log.info('registering uploading app')
            from pybel_web.views import uploading_blueprint
            app.register_blueprint(uploading_blueprint)

        if config.enable_analysis:
            app.register_blueprint(experiment_blueprint)

        app.register_blueprint(receiving_blueprint)

    if config.enable_parser:
        log.info('registering parser app')
        from pybel_web.views import build_parser_service
        build_parser_service(app)

    return app


class PyBELSQLAlchemy(PyBELSQLAlchemyBase):
    """An updated PyBELSQLAlchemy using the WebManager."""

    manager_cls = WebManager
