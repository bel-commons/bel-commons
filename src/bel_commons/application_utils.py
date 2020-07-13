# -*- coding: utf-8 -*-

"""An extension to Flask-SQLAlchemy."""

import datetime
import logging
from typing import Dict, Iterable, Optional

from flask import Flask, g, render_template
from flask_admin import Admin
from flask_security import SQLAlchemyUserDatastore
from raven.contrib.flask import Sentry

from pybel import BELGraph, Manager
from pybel.examples import braf_graph, egf_graph, homology_graph, sialic_acid_graph, statin_graph
from pybel.manager.models import Author, Citation, Edge, Evidence, Namespace, NamespaceEntry, Network, Node
from pybel.struct.mutation import expand_node_neighborhood, expand_nodes_neighborhoods, infer_child_relations
from pybel.struct.pipeline import in_place_transformation, uni_in_place_transformation
from .admin_model_views import (
    CitationView, EdgeView, EvidenceView, ExperimentView, ModelView, NamespaceView, NetworkView, NodeView, QueryView,
    ReportView, UserView, build_project_view,
)
from .constants import SENTRY_DSN
from .manager_utils import insert_graph
from .models import Assembly, EdgeComment, EdgeVote, Experiment, NetworkOverlap, Query, Report, Role, User, UserQuery

logger = logging.getLogger(__name__)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


def register_transformations(manager: Manager) -> None:  # noqa: D202
    """Register several manager-based PyBEL transformation functions."""

    @uni_in_place_transformation
    def expand_nodes_neighborhoods_by_ids(universe: BELGraph, graph: BELGraph, node_hashes: Iterable[str]) -> None:
        """Expand around the neighborhoods of a list of nodes by identifier."""
        nodes = [
            manager.get_dsl_by_hash(node_hash)
            for node_hash in node_hashes
        ]
        return expand_nodes_neighborhoods(universe, graph, nodes)

    @uni_in_place_transformation
    def expand_node_neighborhood_by_id(universe: BELGraph, graph: BELGraph, node_hash: str) -> None:
        """Expand around the neighborhoods of a node by identifier."""
        node = manager.get_dsl_by_hash(node_hash)
        return expand_node_neighborhood(universe, graph, node)

    @in_place_transformation
    def delete_nodes_by_ids(graph: BELGraph, node_hashes: Iterable[str]) -> None:
        """Remove a list of nodes by identifier."""
        nodes = [
            manager.get_dsl_by_hash(node_hash)
            for node_hash in node_hashes
        ]
        graph.remove_nodes_from(nodes)

    @in_place_transformation
    def delete_node_by_id(graph: BELGraph, node_hash: str) -> None:
        """Remove a node by its SHA512."""
        node = manager.get_dsl_by_hash(node_hash)
        graph.remove_node(node)

    @in_place_transformation
    def propagate_node_by_hash(graph: BELGraph, node_hash: str) -> None:
        """Infer relationships from a node by its SHA512."""
        node = manager.get_dsl_by_hash(node_hash)
        infer_child_relations(graph, node)


def register_users_from_manifest(user_datastore: SQLAlchemyUserDatastore, manifest: Dict) -> None:
    """Register the users and roles in a manifest.

    :param user_datastore: A user data store
    :param dict manifest: A manifest dictionary, which contains two keys: ``roles`` and ``users``. The ``roles``
     key corresponds to a list of dictionaries containing ``name`` and ``description`` entries. The ``users`` key
     corresponds to a list of dictionaries containing ``email``, ``password``, and ``name`` entries
     as well as a optional ``roles`` entry with a corresponding list relational to the names in the ``roles``
     entry in the manifest.
    """
    for role in manifest['roles']:
        user_datastore.find_or_create_role(**role)

    for user_manifest in manifest['users']:
        email = user_manifest['email']
        user = user_datastore.find_user(email=email)
        if user is None:
            logger.info(f'creating user: {email}')
            user = user_datastore.create_user(
                confirmed_at=datetime.datetime.now(),
                email=email,
                password=user_manifest['password'],
                name=user_manifest['name'],
            )

        for role_name in user_manifest.get('roles', []):
            if user_datastore.add_role_to_user(user, role_name):
                logger.info(f'registered {user} as {role_name}')

    user_datastore.commit()


def register_error_handlers(app: Flask, *, sentry: Optional[Sentry] = None) -> None:  # noqa: D202
    """Register the 500 and 403 error handlers."""

    @app.errorhandler(500)
    def internal_server_error(_):
        """Call this filter when there's an internal server error.

        Run a rollback and send some information to Sentry.
        """
        if sentry is not None and SENTRY_DSN in app.config:
            kwargs = dict(
                event_id=g.sentry_event_id,
                public_dsn=sentry.client.get_public_dsn('https'),
            )
        else:
            kwargs = {}

        return render_template('errors/500.html', **kwargs)

    @app.errorhandler(403)
    def forbidden_error(error):
        """You must not cross this error."""
        return render_template('errors/403.html')


def register_examples(
    manager: Manager,
    user_datastore: SQLAlchemyUserDatastore,
    user_id: int,
    ground: bool = False,
) -> None:
    """Insert example graphs."""
    for graph in (sialic_acid_graph, egf_graph, statin_graph, homology_graph):
        if ground:
            graph = graph.ground()
        if not manager.has_name_version(graph.name, graph.version):
            logger.info('[user=%s] uploading public example graph: %s', user_id, graph)
            insert_graph(manager, graph, user=user_id, public=True)

    test_user = user_datastore.find_user(email='test@example.com')
    if test_user:
        for graph in (braf_graph,):
            if ground:
                graph = graph.ground()
            if not manager.has_name_version(graph.name, graph.version):
                logger.info('[user=%s] uploading internal example graph: %s', test_user.id, graph)
                insert_graph(manager, graph, user=test_user, public=False)


def register_admin_service(app: Flask, manager: Manager) -> Admin:
    """Add a Flask-Admin database front-end."""
    admin = Admin(app, template_mode='bootstrap3')

    admin.add_view(UserView(User, manager.session))
    admin.add_view(ModelView(Role, manager.session))
    admin.add_view(NamespaceView(Namespace, manager.session, category='Terminology'))
    admin.add_view(ModelView(NamespaceEntry, manager.session, category='Terminology'))
    admin.add_view(NetworkView(Network, manager.session, category='Network'))
    admin.add_view(NodeView(Node, manager.session))
    admin.add_view(EdgeView(Edge, manager.session, category='Edge'))
    admin.add_view(CitationView(Citation, manager.session, category='Provenance'))
    admin.add_view(EvidenceView(Evidence, manager.session, category='Provenance'))
    admin.add_view(ModelView(Author, manager.session, category='Provenance'))
    admin.add_view(ReportView(Report, manager.session, category='Network'))
    admin.add_view(ExperimentView(Experiment, manager.session))
    admin.add_view(QueryView(Query, manager.session, category='Query'))
    admin.add_view(ModelView(UserQuery, manager.session, category='Query'))
    admin.add_view(ModelView(Assembly, manager.session))
    admin.add_view(ModelView(EdgeVote, manager.session, category='Edge'))
    admin.add_view(ModelView(EdgeComment, manager.session, category='Edge'))
    admin.add_view(ModelView(NetworkOverlap, manager.session, category='Network'))
    admin.add_view(build_project_view(manager=manager))

    return admin
