# -*- coding: utf-8 -*-

"""Builds a Flask extension for PyBEL.

The following resources were really helpful in learning about this:

1. https://citizen-stig.github.io/2016/02/17/using-celery-with-flask-factories.html
2. https://github.com/citizen-stig/celery-with-flask-factories
3. https://blog.miguelgrinberg.com/post/celery-and-the-flask-application-factory-pattern
4. http://flask.pocoo.org/docs/0.12/patterns/celery/
"""

import json
import logging
import os
import socket
import time
from getpass import getuser
from typing import Optional

import bel_commons.core
import flasgger
import flask
import flask_bootstrap
import flask_mail
import flask_security
import raven.contrib.flask
from bel_commons.application_utils import (
    register_admin_service, register_error_handlers, register_examples, register_transformations,
    register_users_from_manifest,
)
from bel_commons.config import BELCommonsConfig
from bel_commons.constants import (
    CELERY_BROKER_URL, MAIL_DEFAULT_SENDER, MAIL_SERVER, BEL_COMMONS_CONFIG_JSON, BEL_COMMONS_CONFIG_OBJECT,
    BEL_COMMONS_STARTUP_NOTIFY, SENTRY_DSN, SERVER_NAME, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, SWAGGER,
    SWAGGER_CONFIG,
)
from bel_commons.converters import IntListConverter, ListConverter
from bel_commons.core import FlaskBio2BEL, PyBELSQLAlchemy as PyBELSQLAlchemyBase
from bel_commons.database_service import api_blueprint
from bel_commons.forms import ExtendedRegisterForm
from bel_commons.main_service import ui_blueprint
from bel_commons.manager import WebManager
from bel_commons.utils import get_version
from bel_commons.views import (
    curation_blueprint, experiment_blueprint, help_blueprint, receiving_blueprint, reporting_blueprint,
)

from pybel.constants import get_cache_connection

__all__ = [
    'create_application',
    'PyBELSQLAlchemy',
]

log = logging.getLogger(__name__)

_default_config_location = 'bel_commons.config.Config'

bootstrap = flask_bootstrap.Bootstrap()
mail = flask_mail.Mail()
security = flask_security.Security()
swagger = flasgger.Swagger()
celery = bel_commons.core.PyBELCelery()
flask_bio2bel = FlaskBio2BEL()


# TODO upgrade to jQuery 2?
# See: https://pythonhosted.org/Flask-Bootstrap/faq.html#why-are-you-shipping-jquery-1-instead-of-jquery-2
# app.extensions['bootstrap']['cdns']['jquery'] = flask_bootstrap.WebCDN('//cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/')


def create_application(
        *,
        bel_commons_config: Optional[BELCommonsConfig] = None,
) -> flask.Flask:
    """Build a Flask app."""
    app = flask.Flask(__name__)

    if bel_commons_config is None:
        bel_commons_config = BELCommonsConfig.load()

    # Load default config from object
    config_object_name = os.environ.get(BEL_COMMONS_CONFIG_OBJECT)
    if config_object_name is not None:
        app.config.from_object(config_object_name)
    else:
        app.config.from_object(_default_config_location)

    # Load config from JSON
    config_json_path = os.environ.get(BEL_COMMONS_CONFIG_JSON)
    if config_json_path is not None:
        if os.path.exists(config_json_path):
            log.info(f'importing config from {config_json_path}')
            app.config.from_json(config_json_path)
        else:
            log.warning(f'configuration from environment at {config_json_path} does not exist')

    # Set Swagger defaults
    app.config.setdefault(SWAGGER, SWAGGER_CONFIG)

    # Set SQLAlchemy defaults
    app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)
    app.config[SQLALCHEMY_DATABASE_URI] = get_cache_connection()
    log.info(f'database: {app.config.get(SQLALCHEMY_DATABASE_URI)}')

    # Set Mail defaults
    app.config.setdefault(MAIL_DEFAULT_SENDER, ("BEL Commons", 'bel-commons@scai.fraunhofer.de'))

    # Set Flask defaults
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

    # Add converters
    app.url_map.converters.update({
        'intlist': IntListConverter,
        'list': ListConverter,
    })

    # Initialize extensions
    bootstrap.init_app(app)
    swagger.init_app(app)
    flask_bio2bel.init_app(app)

    has_celery = CELERY_BROKER_URL in app.config
    if has_celery:
        celery.init_app(app)

    mail_server = app.config.get(MAIL_SERVER)
    if mail_server is not None:
        log.info(f'using mail server: {mail_server}')
        mail.init_app(app)
        send_startup_mail(app)

    db = PyBELSQLAlchemy(app)
    manager = db.manager
    user_datastore = manager.user_datastore
    security.init_app(app, user_datastore, register_form=ExtendedRegisterForm)

    sentry_dsn = app.config.get(SENTRY_DSN)
    if sentry_dsn is not None:
        log.info(f'initiating Sentry: {sentry_dsn}')
        sentry = raven.contrib.flask.Sentry(app, dsn=sentry_dsn)
    else:
        sentry = None

    register_error_handlers(app, sentry)

    if bel_commons_config.register_transformations:
        register_transformations(manager=manager)

    if bel_commons_config.register_users:
        with open(bel_commons_config.register_users) as file:
            manifest = json.load(file)
        register_users_from_manifest(user_datastore=user_datastore, manifest=manifest)

    if bel_commons_config.register_examples:
        register_examples(manager=manager, user_datastore=user_datastore)

    if bel_commons_config.register_admin:
        register_admin_service(app=app, manager=manager)

    app.register_blueprint(ui_blueprint)
    if bel_commons_config.enable_curation:
        app.register_blueprint(curation_blueprint)
    app.register_blueprint(help_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(reporting_blueprint)

    if has_celery:  # Requires celery!
        log.info('registering celery-specific apps')
        app.register_blueprint(receiving_blueprint)

        if bel_commons_config.enable_uploader:
            log.info('registering uploading app')
            from bel_commons.views import uploading_blueprint
            app.register_blueprint(uploading_blueprint)

        if bel_commons_config.enable_analysis:
            app.register_blueprint(experiment_blueprint)

    if bel_commons_config.enable_parser:
        log.info('registering parser app')
        from bel_commons.views import build_parser_service
        build_parser_service(app)

    return app


class PyBELSQLAlchemy(PyBELSQLAlchemyBase):
    """An updated PyBELSQLAlchemy using the WebManager."""

    manager_cls = WebManager


def send_startup_mail(app: flask.Flask) -> None:
    """Send an email upon the app's startup."""
    mail_default_sender = app.config.get(MAIL_DEFAULT_SENDER)
    notify = app.config.get(BEL_COMMONS_STARTUP_NOTIFY)
    if notify:
        log.info(f'sending startup notification to {notify}')
        with app.app_context():
            mail.send_message(
                subject="BEL Commons Startup",
                body="BEL Commons v{} was started on {} by {} at {}.\n\nDeployed to: {}".format(
                    get_version(),
                    socket.gethostname(),
                    getuser(),
                    time.asctime(),
                    app.config.get(SERVER_NAME),
                ),
                sender=mail_default_sender,
                recipients=[notify]
            )
        log.info(f'notified {notify}')
