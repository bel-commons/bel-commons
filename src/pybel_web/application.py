# -*- coding: utf-8 -*-


"""
Resources:

1. https://citizen-stig.github.io/2016/02/17/using-celery-with-flask-factories.html
2. https://github.com/citizen-stig/celery-with-flask-factories
3. https://blog.miguelgrinberg.com/post/celery-and-the-flask-application-factory-pattern
4. http://flask.pocoo.org/docs/0.12/patterns/celery/
"""

import datetime
import logging
import socket
import time
from getpass import getuser

import os
from flasgger import Swagger
from flask import (
    Flask,
    g,
    render_template,
)
from flask_bootstrap import Bootstrap, WebCDN
from flask_mail import Mail
from flask_security import Security, SQLAlchemyUserDatastore
from flask_sqlalchemy import SQLAlchemy
from raven.contrib.flask import Sentry
from werkzeug.routing import BaseConverter

from pybel.constants import PYBEL_CONNECTION
from pybel.constants import config as pybel_config
from pybel.constants import get_cache_connection
from pybel.manager import Manager, BaseManager
from pybel_tools.api import DatabaseService
from pybel_tools.mutation import expand_nodes_neighborhoods, expand_node_neighborhood
from pybel_tools.pipeline import uni_in_place_mutator, in_place_mutator
from .constants import CHARLIE_EMAIL, DANIEL_EMAIL, ALEX_EMAIL, PYBEL_WEB_VERSION
from .forms import ExtendedRegisterForm
from .models import Base, Role, User

log = logging.getLogger(__name__)


class FlaskPyBEL:
    """Encapsulates the data needed for the PyBEL Web Application"""

    def __init__(self, app=None, manager=None):
        """
        :param flask.Flask app: A Flask app
        """
        self.app = app
        self.sentry = None
        self.manager = None
        self.user_datastore = None
        self.api = None
        self.admin_role = None
        self.scai_role = None

        if app is not None and manager is not None:
            self.init_app(app, manager)

    def init_app(self, app, manager):
        """
        :param flask.Flask app: A Flask app
        :param manager: A thing that has an engine and a session object
        """
        self.app = app
        self.manager = manager

        self.sentry = Sentry(
            app,
            dsn='https://0e311acc3dc7491fb31406f4e90b07d9:7709d72100f04327b8ef3b2ea673b7ee@sentry.io/183619'
        )

        Base.metadata.bind = self.manager.engine
        Base.query = self.manager.session.query_property()
        Base.metadata.create_all(self.manager.engine, checkfirst=True)

        self.api = DatabaseService(manager=self.manager)
        self.user_datastore = SQLAlchemyUserDatastore(self.manager, User, Role)

        self.admin_role = self.user_datastore.find_or_create_role(
            name='admin',
            description='Admin of PyBEL Web'
        )
        self.scai_role = self.user_datastore.find_or_create_role(
            name='scai',
            description='Users from SCAI'
        )

        self.user_datastore.commit()

        if app.config.get('PYBEL_DS_PRELOAD', False):
            log.info('preloading networks')
            self.api.cache_networks(
                force_reload=app.config.get('PYBEL_WEB_FORCE_RELOAD', False),
                eager=app.config.get('PYBEL_DS_EAGER', False)
            )
            log.info('pre-loaded the dict service')

        app.extensions = getattr(app, 'extensions', {})
        app.extensions['pybel'] = self

        @app.errorhandler(500)
        def internal_server_error(error):
            """Call this filter when there's an internal server error.

            Run a rollback and send some information to Sentry.
            """

            # Lets just assume everything went to shit
            self.manager.session.rollback()

            return render_template(
                '500.html',
                event_id=g.sentry_event_id,
                public_dsn=self.sentry.client.get_public_dsn('https')
            )

        @app.errorhandler(403)
        def forbidden_error(error):
            return render_template('403.html')

        # register functions from API
        @uni_in_place_mutator
        def expand_nodes_neighborhoods_by_ids(universe, graph, node_ids):
            """Expands around the neighborhoods of a list of nodes by idenitifer

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param list node_ids: A list of node hashes
            """
            nodes = self.api.get_nodes_by_hashes(node_ids)
            return expand_nodes_neighborhoods(universe, graph, nodes)

        @uni_in_place_mutator
        def expand_node_neighborhood_by_id(universe, graph, node_id):
            """Expands around the neighborhoods of a node by identifier

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param node_id: The node hash
            """
            node = self.api.get_node_tuple_by_hash(node_id)
            return expand_node_neighborhood(universe, graph, node)

        @in_place_mutator
        def delete_nodes_by_ids(graph, node_ids):
            """Removes a list of nodes by identifier

            :param pybel.BELGraph graph: A BEL graph
            :param list node_ids: A list of node hashes
            """
            nodes = self.api.get_nodes_by_hashes(node_ids)
            graph.remove_nodes_from(nodes)

        @in_place_mutator
        def delete_node_by_id(graph, node_id):
            """Removes a node by identifier

            :param pybel.BELGraph graph: A BEL graph
            :param node_id: A node hash
            """
            node = self.api.get_node_tuple_by_hash(node_id)
            graph.remove_node(node)

    def prepare_service(self):
        if self.app is None or self.manager is None:
            raise ValueError('not initialized')

        for email in (CHARLIE_EMAIL, DANIEL_EMAIL, ALEX_EMAIL):
            admin_user = self.user_datastore.find_user(email=email)

            if admin_user is None:
                admin_user = self.user_datastore.create_user(
                    email=email,
                    password='pybeladmin',
                    confirmed_at=datetime.datetime.now(),
                )

            self.user_datastore.add_role_to_user(admin_user, self.admin_role)
            self.user_datastore.add_role_to_user(admin_user, self.scai_role)
            self.manager.session.add(admin_user)

        test_scai_user = self.user_datastore.find_user(email='test@scai.fraunhofer.de')

        if test_scai_user is None:
            test_scai_user = self.user_datastore.create_user(
                email='test@scai.fraunhofer.de',
                password='pybeltest',
                confirmed_at=datetime.datetime.now(),
            )
            self.user_datastore.add_role_to_user(test_scai_user, self.scai_role)
            self.manager.session.add(test_scai_user)

        self.manager.session.commit()

    @staticmethod
    def get_state(app):
        """
        :param flask.Flask app: A Flask app
        :rtype: FlaskPyBEL
        """
        if 'pybel' not in app.extensions:
            raise ValueError('FlaskPyBEL has not been instantiated')

        return app.extensions['pybel']


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
    app.config.update(pybel_config)

    if config_location is not None:
        log.info('Getting configuration from user supplied argument: %s', config_location)

    elif 'PYBEL_WEB_CONFIG_OBJECT' in os.environ:
        config_location = os.environ['PYBEL_WEB_CONFIG_OBJECT']
        log.info('Getting configuration from environment PYBEL_WEB_CONFIG_OBJECT=%s', config_location)

    else:
        config_location = 'pybel_web.config.Config'
        log.info('Getting configuration from default %s', config_location)

    app.config.from_object(config_location)

    if 'PYBEL_WEB_CONFIG_JSON' in os.environ:
        env_conf_path = os.path.expanduser(os.environ['PYBEL_WEB_CONFIG_JSON'])

        if not os.path.exists(env_conf_path):
            log.warning('configuration from environment at %s does not exist', env_conf_path)

        else:
            log.info('importing config from %s', env_conf_path)
            app.config.from_json(env_conf_path)

    app.config.update(kwargs)
    app.config.setdefault('SWAGGER', {
        'title': 'PyBEL Web API',
        'description': 'This exposes the functions of PyBEL as a RESTful API',
        'contact': {
            'responsibleOrganization': 'Fraunhofer SCAI',
            'responsibleDeveloper': 'Charles Tapley Hoyt',
            'email': 'charles.hoyt@scai.fraunhofer.de',
            'url': 'https://www.scai.fraunhofer.de/de/geschaeftsfelder/bioinformatik.html',
        },
        'version': '0.1.0',
    })

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

    # TODO upgrade to jQuery 2?
    # See: https://pythonhosted.org/Flask-Bootstrap/faq.html#why-are-you-shipping-jquery-1-instead-of-jquery-2
    # app.extensions['bootstrap']['cdns']['jquery'] = jquery2_cdn

    if app.config.get('MAIL_SERVER'):
        mail.init_app(app)

        if app.config.get('PYBEL_WEB_STARTUP_NOTIFY'):
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
                    sender=("PyBEL Web", 'pybel@scai.fraunhofer.de'),
                    recipients=[app.config.get('PYBEL_WEB_STARTUP_NOTIFY')]
                )

    class WebBaseManager(BaseManager):
        def __init__(self, *args, **kwargs):
            self.session = db.session
            self.engine = db.engine

    class WebManager(WebBaseManager, Manager):
        """Killin it with the MRO"""

    manager = WebManager()

    pbx.init_app(app, manager)
    security.init_app(app, pbx.user_datastore, register_form=ExtendedRegisterForm)
    swagger.init_app(app)
    pbx.prepare_service()

    if not get_mail:
        return app

    return app, mail
