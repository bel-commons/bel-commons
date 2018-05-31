# -*- coding: utf-8 -*-

import json
import logging
import os

from flask import g, render_template
from flask_admin import Admin
from raven.contrib.flask import Sentry

from pybel.constants import config
from pybel.examples import *
from pybel.manager.models import (
    Annotation, AnnotationEntry, Author, Citation, Edge, Evidence, Namespace,
    NamespaceEntry, Network, Node,
)
from pybel.struct.mutation import infer_child_relations
from pybel_tools.mutation import add_canonical_names, expand_node_neighborhood, expand_nodes_neighborhoods
from pybel_tools.pipeline import in_place_mutator, uni_in_place_mutator
from .admin_model_views import (
    AnnotationView, CitationView, EdgeView, EvidenceView, ExperimentView, ModelView,
    NamespaceView, NetworkView, NodeView, QueryView, ReportView, UserView, build_project_view,
)
from .constants import PYBEL_WEB_EXAMPLES, PYBEL_WEB_USER_MANIFEST, SENTRY_DSN
from .manager_utils import insert_graph
from .models import (
    Assembly, Base, EdgeComment, EdgeVote, Experiment, NetworkOverlap, Query, Report, Role, User,
)
from .resources.users import default_users_path

__all__ = [
    'FlaskPyBEL',
    'get_manager',
]

log = logging.getLogger(__name__)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


class FlaskPyBEL(object):
    """Encapsulates the data needed for the application"""

    #: The name in which this app is stored in the Flask.extensions dictionary
    APP_NAME = 'pbw'

    def __init__(self, app=None, manager=None, examples=None):
        """
        :param Optional[flask.Flask] app: A Flask app
        :param Optional[pybel.manager.Manager] manager: A thing that has an engine and a session object
        :param bool examples: Should the example subgraphs be loaded on startup? Warning: takes a while. Defaults to
        """
        self.app = app
        self.manager = manager

        if app is not None and manager is not None:
            self.init_app(app, manager, examples=examples)

        self.sentry_dsn = None
        self.sentry = None

    @property
    def user_datastore(self):
        """
        :rtype: flask_security.SQLAlchemyUserDatastore
        """
        return self.manager.user_datastore

    def init_app(self, app, manager, examples=None, register_mutators=True, register_users=True, register_admin=True):
        """
        :param flask.Flask app: A Flask app
        :param pybel_web.manager.WebManager manager: A thing that has an engine and a session object
        :param bool examples: Should the example subgraphs be loaded on startup? Warning: takes a while.
        """
        self.app = app
        self.manager = manager

        self.sentry_dsn = app.config.get(SENTRY_DSN)
        if self.sentry_dsn:
            log.info('initiating Sentry: %s', self.sentry_dsn)
            self.sentry = Sentry(app, dsn=self.sentry_dsn)

        Base.metadata.bind = self.manager.engine
        Base.query = self.manager.session.query_property()

        try:
            Base.metadata.create_all()
        except Exception:
            log.exception('Failed to create all')

        self.app.extensions = getattr(app, 'extensions', {})
        self.app.extensions[self.APP_NAME] = self

        self._register_error_handlers()

        if register_mutators:
            self._register_mutators()
        if register_users:
            self._register_users()
        if register_admin:
            self._build_admin_service()

        if examples or app.config.get(PYBEL_WEB_EXAMPLES, False):
            self._ensure_graphs()

    def _register_error_handlers(self):
        """Register the 500 and 403 error handlers."""

        @self.app.errorhandler(500)
        def internal_server_error(error):
            """Call this filter when there's an internal server error.

            Run a rollback and send some information to Sentry.
            """
            kwargs = {}

            if self.sentry_dsn:
                kwargs.update(dict(
                    event_id=g.sentry_event_id,
                    public_dsn=self.sentry.client.get_public_dsn('https')
                ))

            return render_template(
                'errors/500.html',
                **kwargs
            )

        @self.app.errorhandler(403)
        def forbidden_error(error):
            """You must not cross this error"""
            return render_template('errors/403.html')

    def _register_mutators(self):
        """Register all the mutator functions with PyBEL tools decorators"""

        @uni_in_place_mutator
        def expand_nodes_neighborhoods_by_ids(universe, graph, node_hashes):
            """Expands around the neighborhoods of a list of nodes by identifier

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param list[str] node_hashes: A list of node hashes
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
            :param str node_hash: The node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            return expand_node_neighborhood(universe, graph, node)

        @in_place_mutator
        def delete_nodes_by_ids(graph, node_hashes):
            """Removes a list of nodes by identifier

            :param pybel.BELGraph graph: A BEL graph
            :param list[str] node_hashes: A list of node hashes
            """
            nodes = self.manager.get_node_tuples_by_hashes(node_hashes)
            graph.remove_nodes_from(nodes)

        @in_place_mutator
        def delete_node_by_id(graph, node_hash):
            """Remove a node by identifier.

            :param pybel.BELGraph graph: A BEL graph
            :param str node_hash: A node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            graph.remove_node(node)

        @in_place_mutator
        def propagate_node_by_hash(graph, node_hash):
            """Infer relationships from a node.

            :param pybel.BELGraph graph: A BEL graph
            :param str node_hash: A node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            infer_child_relations(graph, node)

    def _register_users(self):
        """Add the default users to the user datastore."""
        if os.path.exists(default_users_path):
            with open(default_users_path) as f:
                default_users_manifest = json.load(f)
            self.manager.register_users_from_manifest(default_users_manifest)

        pybel_config_user_manifest = config.get(PYBEL_WEB_USER_MANIFEST)
        if pybel_config_user_manifest is not None:
            self.manager.register_users_from_manifest(pybel_config_user_manifest)

    def _build_admin_service(self):
        """Add a Flask-Admin database front-end.

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
        admin.add_view(build_project_view(self.manager, self.user_datastore))

        return admin

    def _ensure_graphs(self):
        """Add  example BEL graphs that should always be present."""
        for graph in (sialic_acid_graph, egf_graph, statin_graph, homology_graph):
            if not self.manager.has_name_version(graph.name, graph.version):
                add_canonical_names(graph)
                log.info('uploading public example graph: %s', graph)
                insert_graph(self.manager, graph, public=True)

        test_user = self.user_datastore.find_user(email='test@scai.fraunhofer.de')

        for graph in (braf_graph,):
            if not self.manager.has_name_version(graph.name, graph.version):
                add_canonical_names(graph)
                log.info('uploading internal example graph: %s', graph)
                insert_graph(self.manager, graph, user=test_user, public=False)

    @classmethod
    def get_state(cls, app):
        """
        :param flask.Flask app: A Flask app
        :rtype: FlaskPyBEL
        """
        if cls.APP_NAME not in app.extensions:
            raise ValueError('{} has not been instantiated'.format(cls.__name__))

        return app.extensions[cls.APP_NAME]


def get_manager(app):
    """Get the cache manger from a Flask app.

    :param flask.Flask app: A Flask app
    :rtype: pybel_web.manager.WebManager
    """
    return FlaskPyBEL.get_state(app).manager
