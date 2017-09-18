# -*- coding: utf-8 -*-

import datetime
import logging

from flask import (
    g,
    render_template,
)
from flask_security import SQLAlchemyUserDatastore
from raven.contrib.flask import Sentry

from pybel_tools.api import DatabaseService
from pybel_tools.mutation import expand_nodes_neighborhoods, expand_node_neighborhood
from pybel_tools.pipeline import uni_in_place_mutator, in_place_mutator
from .constants import CHARLIE_EMAIL, DANIEL_EMAIL, ALEX_EMAIL
from .models import Base, Role, User

log = logging.getLogger(__name__)


class FlaskPyBEL:
    """Encapsulates the data needed for the PyBEL Web Application"""

    #: The name in which this app is stored in the Flask.extensions dictionary
    APP_NAME = 'pbw'

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
        app.extensions[self.APP_NAME] = self

        @app.errorhandler(500)
        def internal_server_error(error):
            """Call this filter when there's an internal server error.

            Run a rollback and send some information to Sentry.
            """
            self.manager.session.rollback()  # Lets just assume everything went to shit

            return render_template(
                '500.html',
                event_id=g.sentry_event_id,
                public_dsn=self.sentry.client.get_public_dsn('https')
            )

        @app.errorhandler(403)
        def forbidden_error(error):
            """You must not cross this error"""
            return render_template('403.html')

        # register functions from API
        @uni_in_place_mutator
        def expand_nodes_neighborhoods_by_ids(universe, graph, node_ids):
            """Expands around the neighborhoods of a list of nodes by identifier

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

        scai_role = self.user_datastore.find_or_create_role(name='scai')

        for email in (CHARLIE_EMAIL, DANIEL_EMAIL, ALEX_EMAIL):
            admin_user = self.user_datastore.find_user(email=email)

            if admin_user is None:
                admin_user = self.user_datastore.create_user(
                    email=email,
                    password='pybeladmin',
                    confirmed_at=datetime.datetime.now(),
                )

            self.user_datastore.add_role_to_user(admin_user, self.admin_role)
            self.user_datastore.add_role_to_user(admin_user, scai_role)
            self.manager.session.add(admin_user)

        test_scai_user = self.user_datastore.find_user(email='test@scai.fraunhofer.de')

        if test_scai_user is None:
            test_scai_user = self.user_datastore.create_user(
                email='test@scai.fraunhofer.de',
                password='pybeltest',
                confirmed_at=datetime.datetime.now(),
            )
            self.user_datastore.add_role_to_user(test_scai_user, scai_role)
            self.manager.session.add(test_scai_user)

        self.manager.session.commit()

    @classmethod
    def get_state(cls, app):
        """
        :param flask.Flask app: A Flask app
        :rtype: FlaskPyBEL
        """
        if cls.APP_NAME not in app.extensions:
            raise ValueError('FlaskPyBEL has not been instantiated')

        return app.extensions[cls.APP_NAME]


def get_scai_role(app):
    """Gets the SCAI role from the Flask app

    :param flask.Flask app:
    :rtype: Role
    """
    return FlaskPyBEL.get_state(app).scai_role


def get_sentry(app):
    """Gets the User Data Store from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: raven.Sentry
    """
    return FlaskPyBEL.get_state(app).sentry


def get_user_datastore(app):
    """Gets the User Data Store from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: flask_security.DatabaseService
    """
    return FlaskPyBEL.get_state(app).user_datastore


def get_api(app):
    """Gets the dictionary service from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: DatabaseService
    """
    return FlaskPyBEL.get_state(app).api


def get_manager(app):
    """Gets the cache manger from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: pybel.manager.Manager
    """
    return FlaskPyBEL.get_state(app).manager
