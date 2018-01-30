# -*- coding: utf-8 -*-

import datetime
import logging
from itertools import chain

from flask import g, redirect, render_template, request
from flask_admin import Admin
from flask_admin.contrib.sqla.ajax import QueryAjaxModelLoader
from flask_admin.model.ajax import DEFAULT_PAGE_SIZE
from flask_security import SQLAlchemyUserDatastore, current_user, url_for_security
from raven.contrib.flask import Sentry
from sqlalchemy import or_

from pybel.examples import egf_graph, sialic_acid_graph
from pybel.manager.models import (
    Annotation, AnnotationEntry, Author, Citation, Edge, Evidence, Namespace,
    NamespaceEntry, Network, Node,
)
from pybel_tools.mutation import add_canonical_names, expand_node_neighborhood, expand_nodes_neighborhoods
from pybel_tools.pipeline import in_place_mutator, uni_in_place_mutator
from .admin_model_views import (
    AnnotationView, CitationView, EdgeView, EvidenceView, ExperimentView, ModelView,
    ModelViewBase, NamespaceView, NetworkView, NodeView, QueryView, ReportView, UserView,
)
from .constants import ALEX_EMAIL, CHARLIE_EMAIL, DANIEL_EMAIL
from .manager_utils import insert_graph
from .models import (
    Assembly, Base, EdgeComment, EdgeVote, Experiment, NetworkOverlap, Project, Query, Report, Role, User,
)

log = logging.getLogger(__name__)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


def iter_public_networks(manager_):
    """Lists the graphs that have been made public

    :param pybel.manager.Manager manager_:
    :rtype: list[Network]
    """
    return (
        network
        for network in manager_.list_recent_networks()
        if network.report and network.report.public
    )


def build_network_ajax_manager(manager, user_datastore):
    """

    :param pybel.manager.Manager manager: A PyBE manager
    :param flask_security.SQLAlchemyUserDatastore user_datastore: A flask security user datastore manager
    :rtype: QueryAjaxModelLoader
    """

    class NetworkAjaxModelLoader(QueryAjaxModelLoader):
        """Custom Network AJAX loader for Flask Admin"""

        def __init__(self):
            super(NetworkAjaxModelLoader, self).__init__('networks', manager.session, Network,
                                                         fields=[Network.name])

        def get_list(self, term, offset=0, limit=DEFAULT_PAGE_SIZE):
            """Overrides get_list to be lazy and tricky about only getting current user's networks"""
            query = self.session.query(self.model)

            filters = (field.ilike(u'%%%s%%' % term) for field in self._cached_fields)
            query = query.filter(or_(*filters))

            if not current_user.is_admin:
                network_chain = chain(
                    current_user.get_owned_networks(),
                    current_user.get_shared_networks(),
                    iter_public_networks(manager),
                )

                allowed_network_ids = {
                    network.id
                    for network in network_chain
                }

                if current_user.is_scai:
                    scai_role = user_datastore.find_or_create_role(name='scai')

                    for user in scai_role.users:
                        for network in user.get_owned_networks():
                            allowed_network_ids.add(network.id)

                if not allowed_network_ids:  # If the current user doesn't have any networks, then return nothing
                    return []

                query = query.filter(Network.id.in_(allowed_network_ids))

            return query.offset(offset).limit(limit).all()

    return NetworkAjaxModelLoader()


def build_project_view(manager, user_datastore):
    """

    :param manager:
    :param user_datastore:
    :rtype: type[ModelView]
    """

    class ProjectView(ModelViewBase):
        """Special view to allow users of given projects to manage them"""

        def is_accessible(self):
            """Checks the current user is logged in"""
            return current_user.is_authenticated

        def inaccessible_callback(self, name, **kwargs):
            """redirect to login page if user doesn't have access"""
            return redirect(url_for_security('login', next=request.url))

        def get_query(self):
            """Only show projects that the user is part of"""
            parent_query = super(ProjectView, self).get_query()

            if current_user.is_admin:
                return parent_query

            current_projects = {
                project.id
                for project in current_user.projects
            }

            return parent_query.filter(Project.id.in_(current_projects))

        def on_model_change(self, form, model, is_created):
            """Hacky - automatically add user when they create a project"""
            if current_user not in model.users:
                model.users.append(current_user)

        form_ajax_refs = {
            'networks': build_network_ajax_manager(manager, user_datastore)
        }

    return ProjectView


class FlaskPyBEL(object):
    """Encapsulates the data needed for the PyBEL Web Application"""

    #: The name in which this app is stored in the Flask.extensions dictionary
    APP_NAME = 'pbw'

    def __init__(self, app=None, manager=None):
        """
        :param Optional[flask.Flask] app: A Flask app
        :param Optional[pybel.manager.Manager] manager: A thing that has an engine and a session object
        """
        self.app = app
        self.manager = manager
        self.user_datastore = None

        if app is not None and manager is not None:
            self.init_app(app, manager)

        self.sentry = None

    def init_app(self, app, manager):
        """
        :param flask.Flask app: A Flask app
        :param pybel.manager.Manager manager: A thing that has an engine and a session object
        """
        self.app = app
        self.manager = manager

        sentry_dsn = app.config.get('SENTRY_DSN')

        if sentry_dsn:
            log.info('initiating Sentry: %s', sentry_dsn)
            self.sentry = Sentry(app, dsn=sentry_dsn)

        Base.metadata.bind = self.manager.engine
        Base.query = self.manager.session.query_property()

        try:
            Base.metadata.create_all()
        except Exception:
            log.exception('Failed to create all')

        self.user_datastore = SQLAlchemyUserDatastore(self.manager, User, Role)

        self.user_datastore.find_or_create_role(
            name='admin',
            description='Admin of PyBEL Web'
        )
        self.user_datastore.find_or_create_role(
            name='scai',
            description='Users from Fraunhofer SCAI'
        )

        self.user_datastore.commit()

        app.extensions = getattr(app, 'extensions', {})
        app.extensions[self.APP_NAME] = self

        @app.errorhandler(500)
        def internal_server_error(error):
            """Call this filter when there's an internal server error.

            Run a rollback and send some information to Sentry.
            """
            kwargs = {}

            if sentry_dsn:
                kwargs.update(dict(
                    event_id=g.sentry_event_id,
                    public_dsn=self.sentry.client.get_public_dsn('https')
                ))

            return render_template(
                '500.html',
                **kwargs
            )

        @app.errorhandler(403)
        def forbidden_error(error):
            """You must not cross this error"""
            return render_template('403.html')

        # register functions with decorator
        @uni_in_place_mutator
        def expand_nodes_neighborhoods_by_ids(universe, graph, node_hashes):
            """Expands around the neighborhoods of a list of nodes by identifier

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param list node_hashes: A list of node hashes
            """
            nodes = [
                self.manager.get_node_tuple_by_hash(node_hash)
                for node_hash in node_hashes
            ]
            return expand_nodes_neighborhoods(universe, graph, nodes)

        @uni_in_place_mutator
        def expand_node_neighborhood_by_id(universe, graph, node_hash):
            """Expands around the neighborhoods of a node by identifier

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param node_hash: The node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            return expand_node_neighborhood(universe, graph, node)

        @in_place_mutator
        def delete_nodes_by_ids(graph, node_hashes):
            """Removes a list of nodes by identifier

            :param pybel.BELGraph graph: A BEL graph
            :param list node_hashes: A list of node hashes
            """
            nodes = self.manager.get_node_tuples_by_hashes(node_hashes)
            graph.remove_nodes_from(nodes)

        @in_place_mutator
        def delete_node_by_id(graph, node_hash):
            """Removes a node by identifier

            :param pybel.BELGraph graph: A BEL graph
            :param node_hash: A node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            graph.remove_node(node)

        self._prepare_service()
        self._build_admin_service()
        self._ensure_graphs()

    def _prepare_service(self):
        """Adds the default users to the user datastore"""
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

            self.user_datastore.add_role_to_user(admin_user, 'admin')
            self.user_datastore.add_role_to_user(admin_user, 'scai')
            self.manager.session.add(admin_user)

        test_scai_user = self.user_datastore.find_user(email='test@scai.fraunhofer.de')

        if test_scai_user is None:
            test_scai_user = self.user_datastore.create_user(
                email='test@scai.fraunhofer.de',
                password='pybeltest',
                confirmed_at=datetime.datetime.now(),
            )
            self.user_datastore.add_role_to_user(test_scai_user, 'scai')
            self.manager.session.add(test_scai_user)

        self.manager.session.commit()

    def _build_admin_service(self):
        """Adds Flask-Admin database front-end

        :rtype: flask_admin.Admin
        """
        admin = Admin(self.app, template_mode='bootstrap3')
        manager = self.manager

        admin.add_view(UserView(User, manager.session))
        admin.add_view(ModelView(Role, manager.session))
        admin.add_view(NamespaceView(Namespace, manager.session))
        admin.add_view(ModelView(NamespaceEntry, manager.session))
        admin.add_view(AnnotationView(Annotation, manager.session))
        admin.add_view(ModelView(AnnotationEntry, manager.session))
        admin.add_view(NetworkView(Network, manager.session))
        admin.add_view(NodeView(Node, manager.session))
        admin.add_view(EdgeView(Edge, manager.session))
        admin.add_view(CitationView(Citation, manager.session))
        admin.add_view(EvidenceView(Evidence, manager.session))
        admin.add_view(ModelView(Author, manager.session))
        admin.add_view(ReportView(Report, manager.session))
        admin.add_view(ExperimentView(Experiment, manager.session))
        admin.add_view(QueryView(Query, manager.session))
        admin.add_view(ModelView(Assembly, manager.session))
        admin.add_view(ModelView(EdgeVote, manager.session))
        admin.add_view(ModelView(EdgeComment, manager.session))
        admin.add_view(ModelView(NetworkOverlap, manager.session))
        admin.add_view(build_project_view(self.manager, self.user_datastore)(Project, manager.session))

        return admin

    def _ensure_graphs(self):
        """Adds example BEL graphs that should always be present"""
        for graph in (sialic_acid_graph, egf_graph):
            if not self.manager.has_name_version(graph.name, graph.version):
                add_canonical_names(graph)
                log.info('uploading example graph: %s', graph)
                insert_graph(self.manager, graph, public=True)

    @classmethod
    def get_state(cls, app):
        """
        :param flask.Flask app: A Flask app
        :rtype: FlaskPyBEL
        """
        if cls.APP_NAME not in app.extensions:
            raise ValueError('FlaskPyBEL has not been instantiated')

        return app.extensions[cls.APP_NAME]


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


def get_manager(app):
    """Gets the cache manger from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: pybel.manager.Manager
    """
    return FlaskPyBEL.get_state(app).manager
