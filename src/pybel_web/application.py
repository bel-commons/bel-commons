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
from flask import (
    Flask,
)
from flask_bootstrap import Bootstrap, WebCDN
from flask_mail import Mail
from flask_security import Security
from flask_sqlalchemy import SQLAlchemy
from werkzeug.routing import BaseConverter

from pybel.constants import PYBEL_CONNECTION, config as pybel_config, get_cache_connection
from .application_utils import FlaskPyBEL
from .celery_utils import create_celery
from .constants import (
    CELERY_BROKER_URL, MAIL_DEFAULT_SENDER, MAIL_SERVER, PYBEL_WEB_CONFIG_JSON,
    PYBEL_WEB_STARTUP_NOTIFY, SERVER_NAME, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, SWAGGER,
    SWAGGER_CONFIG, VERSION,
)
from .forms import ExtendedRegisterForm
from .manager import WebManager

log = logging.getLogger(__name__)

_default_config_location = 'pybel_web.config.Config'

bootstrap = Bootstrap()
pbx = FlaskPyBEL()
mail = Mail()
security = Security()
swagger = Swagger()

# TODO upgrade to jQuery 2?
# See: https://pythonhosted.org/Flask-Bootstrap/faq.html#why-are-you-shipping-jquery-1-instead-of-jquery-2
# app.extensions['bootstrap']['cdns']['jquery'] = jquery2_cdn
jquery2_cdn = WebCDN('//cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/')


class ListConverter(BaseConverter):
    def to_python(self, value):
        return value.split(',')

    def to_url(self, values):
        return ','.join(BaseConverter.to_url(self, value) for value in values)


class IntListConverter(ListConverter):
    def to_python(self, value):
        return [int(entry) for entry in ListConverter.to_python(self, value)]


def get_config_object(config_location=None):
    """Get the application configuration

    :param Optional[str] config_location:
    :rtype: str
    """
    if config_location is not None:
        log.info('using configuration from user supplied argument: %s', config_location)
        return config_location

    pbw_conf_obj = os.environ.get('PYBEL_WEB_CONFIG_OBJECT')
    if pbw_conf_obj is not None:
        log.info('using configuration from environment: %s', pbw_conf_obj)
        return pbw_conf_obj

    log.info('using configuration from default %s', _default_config_location)
    return _default_config_location


def _send_startup_mail(app):
    mail_default_sender = app.config.get(MAIL_DEFAULT_SENDER)
    notify = app.config.get(PYBEL_WEB_STARTUP_NOTIFY)
    if notify:
        log.info('sending startup notification to %s', notify)
        with app.app_context():
            mail.send_message(
                subject="BEL Commons Startup",
                body="BEL Commons v{} was started on {} by {} at {}.\n\nDeployed to: {}".format(
                    VERSION,
                    socket.gethostname(),
                    getuser(),
                    time.asctime(),
                    app.config.get(SERVER_NAME)
                ),
                sender=mail_default_sender,
                recipients=[notify]
            )
        log.info('notified %s', notify)


def create_application(config_object_name=None, examples=None, **kwargs):
    """Build a Flask app.
    
    1. Loads default config
    2. Updates with kwargs
    
    :param str config_object_name: The path to the object that will get loaded for default configuration. Defaults to
     :data:`'pybel_web.config.Config'`
    :param Optional[bool] examples: Should examples be pre-loaded
    :param dict kwargs: keyword arguments to add to config
    :rtype: flask.Flask
    """
    app = Flask(__name__)
    app.config.from_object(get_config_object(config_object_name))
    app.config.update(pybel_config)

    pbw_config_json = os.environ.get(PYBEL_WEB_CONFIG_JSON)
    if pbw_config_json is not None:
        if os.path.exists(pbw_config_json):
            log.info('importing config from %s', pbw_config_json)
            app.config.from_json(pbw_config_json)
        else:
            log.warning('configuration from environment at %s does not exist', pbw_config_json)

    app.config.update(kwargs)
    app.config.setdefault(SWAGGER, SWAGGER_CONFIG)
    app.config.setdefault(PYBEL_CONNECTION, get_cache_connection())
    app.config[SQLALCHEMY_DATABASE_URI] = app.config[PYBEL_CONNECTION]
    app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)

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
        create_celery(app)

    app.config.setdefault(MAIL_DEFAULT_SENDER, ("BEL Commons", 'pybel@scai.fraunhofer.de'))

    mail_server = app.config.get(MAIL_SERVER)
    if mail_server is not None:
        log.info('using mail server: %s', mail_server)
        mail.init_app(app)
        _send_startup_mail(app)

    # Build a manager directly from the engine/session interface
    # TODO consider making PyBELFlask a subclass of SQLAlchemy?
    db = SQLAlchemy(app=app)
    manager = WebManager(engine=db.engine, session=db.session)
    pbx.init_app(app, manager, examples=examples)

    security.init_app(app, pbx.user_datastore, register_form=ExtendedRegisterForm)

    return app
