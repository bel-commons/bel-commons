# -*- coding: utf-8 -*-

"""
Resources:

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
from pybel.manager import BaseManager, Manager
from .application_utils import FlaskPyBEL
from .celery_utils import create_celery
from .constants import PYBEL_WEB_VERSION
from .forms import ExtendedRegisterForm

log = logging.getLogger(__name__)

bootstrap = Bootstrap()
pbx = FlaskPyBEL()
mail = Mail()
security = Security()
swagger = Swagger()
jquery2_cdn = WebCDN('//cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/')


class ListConverter(BaseConverter):
    def to_python(self, value):
        return value.split(',')

    def to_url(self, values):
        return ','.join(BaseConverter.to_url(self, value) for value in values)


class IntListConverter(ListConverter):
    def to_python(self, value):
        return [int(entry) for entry in ListConverter.to_python(self, value)]


def get_config_location(config_location=None):
    if config_location is not None:
        log.info('Getting configuration from user supplied argument: %s', config_location)
        return config_location

    if 'PYBEL_WEB_CONFIG_OBJECT' in os.environ:
        log.info('Getting configuration from environment PYBEL_WEB_CONFIG_OBJECT=%s',
                 os.environ['PYBEL_WEB_CONFIG_OBJECT'])
        return os.environ['PYBEL_WEB_CONFIG_OBJECT']

    config_location = 'pybel_web.config.Config'
    log.info('Getting configuration from default %s', config_location)
    return config_location


swagger_config = {
    'title': 'PyBEL Web API',
    'description': 'This exposes the functions of PyBEL as a RESTful API',
    'contact': {
        'responsibleOrganization': 'Fraunhofer SCAI',
        'responsibleDeveloper': 'Charles Tapley Hoyt',
        'email': 'charles.hoyt@scai.fraunhofer.de',
        'url': 'https://www.scai.fraunhofer.de/de/geschaeftsfelder/bioinformatik.html',
    },
    'version': '0.1.0',
}


def create_application(get_mail=False, config_location=None, **kwargs):
    """Builds a Flask app for the PyBEL web service
    
    1. Loads default config
    2. Updates with kwargs
    
    :param bool get_mail: Activate the return have a tuple of (Flask, Mail)
    :param str config_location: The path to the object that will get loaded for default configuration. Defaults to
                                :data:`'pybel_web.config.Config'`
    :param dict kwargs: keyword arguments to add to config
    :rtype: flask.Flask
    """
    app = Flask(__name__)
    app.config.from_object(get_config_location(config_location))
    app.config.update(pybel_config)

    if 'PYBEL_WEB_CONFIG_JSON' in os.environ:
        env_conf_path = os.path.expanduser(os.environ['PYBEL_WEB_CONFIG_JSON'])

        if not os.path.exists(env_conf_path):
            log.warning('configuration from environment at %s does not exist', env_conf_path)

        else:
            log.info('importing config from %s', env_conf_path)
            app.config.from_json(env_conf_path)

    app.config.update(kwargs)
    app.config.setdefault('SWAGGER', swagger_config)

    if not app.config.get(PYBEL_CONNECTION):
        app.config[PYBEL_CONNECTION] = get_cache_connection()

    app.config['SQLALCHEMY_DATABASE_URI'] = app.config[PYBEL_CONNECTION]
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)

    log.info('database: %s', app.config.get(PYBEL_CONNECTION))

    # Add converters
    app.url_map.converters['intlist'] = IntListConverter
    app.url_map.converters['list'] = ListConverter

    # Initialize extensions
    db = SQLAlchemy(app=app)
    bootstrap.init_app(app)
    create_celery(app)

    # TODO upgrade to jQuery 2?
    # See: https://pythonhosted.org/Flask-Bootstrap/faq.html#why-are-you-shipping-jquery-1-instead-of-jquery-2
    # app.extensions['bootstrap']['cdns']['jquery'] = jquery2_cdn

    if app.config.get('MAIL_SERVER'):
        mail.init_app(app)
        log.info('connected to mail server: %s', mail)

        notify = app.config.get('PYBEL_WEB_STARTUP_NOTIFY')

        if notify:
            with app.app_context():
                mail.send_message(
                    subject="PyBEL Web - Startup",
                    body="PyBEL Web v{} was started on {} by {} at {}.\n\nDeployed to: {}".format(
                        PYBEL_WEB_VERSION,
                        socket.gethostname(),
                        getuser(),
                        time.asctime(),
                        app.config.get('SERVER_NAME')
                    ),
                    sender=app.config.get('MAIL_DEFAULT_SENDER', ("PyBEL Web", 'pybel@scai.fraunhofer.de')),
                    recipients=[notify]
                )
            log.info('notified %s', notify)

    class WebBaseManager(BaseManager):
        def __init__(self, *args, **kwargs):
            self.session = db.session
            self.engine = db.engine

    class WebManager(Manager, WebBaseManager):
        """Killin it with the MRO"""

    manager = WebManager()

    pbx.init_app(app, manager)
    security.init_app(app, pbx.user_datastore, register_form=ExtendedRegisterForm)
    swagger.init_app(app)

    if not get_mail:
        return app

    return app, mail
