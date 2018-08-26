# -*- coding: utf-8 -*-

"""An extension to Flask-SQLAlchemy."""

import json
import logging
import os
from flask import g, render_template
from flask_admin import Admin
from flask_sqlalchemy import SQLAlchemy, get_state
from raven.contrib.flask import Sentry

from pybel.examples import *
from pybel.manager.models import Author, Citation, Edge, Evidence, Namespace, NamespaceEntry, Network, Node
from pybel.struct.mutation import expand_node_neighborhood, expand_nodes_neighborhoods, infer_child_relations
from pybel.struct.pipeline import in_place_transformation, uni_in_place_transformation
from pybel_tools.mutation import add_canonical_names
from .admin_model_views import (
    AnnotationView, CitationView, EdgeView, EvidenceView, ExperimentView, ModelView, NamespaceView, NetworkView,
    NodeView, QueryView, ReportView, UserView, build_project_view,
)
from .constants import (
    PYBEL_WEB_REGISTER_ADMIN, PYBEL_WEB_REGISTER_EXAMPLES, PYBEL_WEB_REGISTER_TRANSFORMATIONS,
    PYBEL_WEB_REGISTER_USERS, PYBEL_WEB_USER_MANIFEST, SENTRY_DSN,
)
from .manager import WebManager
from .manager_utils import insert_graph
from .models import Assembly, Base, EdgeComment, EdgeVote, Experiment, NetworkOverlap, Query, Report, Role, User
from .resources.users import default_users_path

__all__ = [
    'PyBELSQLAlchemy',
]

log = logging.getLogger(__name__)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


class PyBELSQLAlchemy(SQLAlchemy):
    """An extension of Flask-SQLAlchemy to support the PyBEL Web manager."""

    #: :type: pybel_web.manager.WebManager
    manager = None

    #: :type: Optional[raven.contrib.flask.Sentry]
    sentry = None

    def init_app(self, app):
        """
        :param flask.Flask app: A Flask app
        """
        super().init_app(app)

        self.manager = WebManager(engine=self.engine, session=self.session)

        self.app.config.setdefault(PYBEL_WEB_REGISTER_TRANSFORMATIONS, True)
        self.app.config.setdefault(PYBEL_WEB_REGISTER_USERS, True)
        self.app.config.setdefault(PYBEL_WEB_REGISTER_ADMIN, True)
        self.app.config.setdefault(PYBEL_WEB_REGISTER_EXAMPLES, False)

        sentry_dsn = self.app.config.get(SENTRY_DSN)
        if sentry_dsn is not None:
            log.info('initiating Sentry: %s', sentry_dsn)
            self.sentry = Sentry(self.app, dsn=sentry_dsn)

        Base.metadata.bind = self.engine
        Base.query = self.session.query_property()

        try:
            Base.metadata.create_all()
        except Exception:
            log.exception('Failed to create all')

        self._register_error_handlers()
        if app.config[PYBEL_WEB_REGISTER_TRANSFORMATIONS]:
            self._register_transformations()
        if app.config[PYBEL_WEB_REGISTER_USERS]:
            self._register_users()
        if app.config[PYBEL_WEB_REGISTER_ADMIN]:
            self._register_admin_service()
        if app.config[PYBEL_WEB_REGISTER_EXAMPLES]:
            self._register_examples()

    @property
    def user_datastore(self):
        """
        :rtype: flask_security.SQLAlchemyUserDatastore
        """
        return self.manager.user_datastore

    def _register_error_handlers(self):
        """Register the 500 and 403 error handlers."""

        @self.app.errorhandler(500)
        def internal_server_error(error):
            """Call this filter when there's an internal server error.

            Run a rollback and send some information to Sentry.
            """
            kwargs = {}

            if self.app.config.get(SENTRY_DSN):
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

    def _register_transformations(self):
        """Register all the transformation functions with PyBEL tools decorators."""

        @uni_in_place_transformation
        def expand_nodes_neighborhoods_by_ids(universe, graph, node_hashes):
            """Expand around the neighborhoods of a list of nodes by identifier.

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param list[str] node_hashes: A list of node hashes
            """
            nodes = [
                self.manager.get_node_tuple_by_hash(node_hash)
                for node_hash in node_hashes
            ]
            return expand_nodes_neighborhoods(universe, graph, nodes)

        @uni_in_place_transformation
        def expand_node_neighborhood_by_id(universe, graph, node_hash):
            """Expand around the neighborhoods of a node by identifier.

            :param pybel.BELGraph universe: A BEL graph
            :param pybel.BELGraph graph: A BEL graph
            :param str node_hash: The node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            return expand_node_neighborhood(universe, graph, node)

        @in_place_transformation
        def delete_nodes_by_ids(graph, node_hashes):
            """Remove a list of nodes by identifier.

            :param pybel.BELGraph graph: A BEL graph
            :param list[str] node_hashes: A list of node hashes
            """
            nodes = [
                self.manager.get_node_tuple_by_hash(node_hash)
                for node_hash in node_hashes
            ]
            graph.remove_nodes_from(nodes)

        @in_place_transformation
        def delete_node_by_id(graph, node_hash):
            """Remove a node by identifier.

            :param pybel.BELGraph graph: A BEL graph
            :param str node_hash: A node hash
            """
            node = self.manager.get_node_tuple_by_hash(node_hash)
            graph.remove_node(node)

        @in_place_transformation
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

        pybel_config_user_manifest = self.app.config.get(PYBEL_WEB_USER_MANIFEST)
        if pybel_config_user_manifest is not None:
            self.manager.register_users_from_manifest(pybel_config_user_manifest)

    def _register_admin_service(self):
        """Add a Flask-Admin database front-end.

        :rtype: flask_admin.Admin
        """
        admin = Admin(self.app, template_mode='bootstrap3')

        admin.add_view(UserView(User, self.session))
        admin.add_view(ModelView(Role, self.session))
        admin.add_view(NamespaceView(Namespace, self.session))
        admin.add_view(ModelView(NamespaceEntry, self.session))
        admin.add_view(NetworkView(Network, self.session))
        admin.add_view(NodeView(Node, self.session))
        admin.add_view(EdgeView(Edge, self.session))
        admin.add_view(CitationView(Citation, self.session))
        admin.add_view(EvidenceView(Evidence, self.session))
        admin.add_view(ModelView(Author, self.session))
        admin.add_view(ReportView(Report, self.session))
        admin.add_view(ExperimentView(Experiment, self.session))
        admin.add_view(QueryView(Query, self.session))
        admin.add_view(ModelView(Assembly, self.session))
        admin.add_view(ModelView(EdgeVote, self.session))
        admin.add_view(ModelView(EdgeComment, self.session))
        admin.add_view(ModelView(NetworkOverlap, self.session))
        admin.add_view(build_project_view(self.manager))

        return admin

    def _register_examples(self):
        """Add example BEL graphs that should always be present."""
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

    @staticmethod
    def get_manager(app):
        """
        :param flask.Flask app: A Flask app
        :rtype: pybel_web.manager.WebManager
        """
        return get_state(app).db.manager
