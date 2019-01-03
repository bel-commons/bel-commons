# -*- coding: utf-8 -*-

"""An extension to Flask-SQLAlchemy."""

import datetime
import json
import logging
import os
from typing import Dict, Iterable

from flask import Flask, g, render_template
from flask_admin import Admin
from flask_security import SQLAlchemyUserDatastore
from raven.contrib.flask import Sentry

from pybel import BELGraph, Manager
from pybel.examples import *
from pybel.manager.models import Author, Citation, Edge, Evidence, Namespace, NamespaceEntry, Network, Node
from pybel.struct.mutation import expand_node_neighborhood, expand_nodes_neighborhoods, infer_child_relations
from pybel.struct.pipeline import in_place_transformation, uni_in_place_transformation
from pybel_web.core.models import Assembly, Query
from .admin_model_views import (
    CitationView, EdgeView, EvidenceView, ExperimentView, ModelView, NamespaceView, NetworkView, NodeView, QueryView,
    ReportView, UserView, build_project_view,
)
from .constants import PYBEL_WEB_USER_MANIFEST, SENTRY_DSN
from .manager_utils import insert_graph
from .models import EdgeComment, EdgeVote, Experiment, NetworkOverlap, Report, Role, User, UserQuery
from .resources.users import default_users_path

log = logging.getLogger(__name__)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


def register_transformations(manager: Manager):
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
    def delete_nodes_by_ids(graph: BELGraph, node_hashes: list) -> None:
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


def register_users(app: Flask, user_datastore: SQLAlchemyUserDatastore) -> None:
    if os.path.exists(default_users_path):
        with open(default_users_path) as f:
            default_users_manifest = json.load(f)
        _register_users_from_manifest(user_datastore=user_datastore, manifest=default_users_manifest)

    pybel_config_user_manifest = app.config.get(PYBEL_WEB_USER_MANIFEST)
    if pybel_config_user_manifest is not None:
        _register_users_from_manifest(user_datastore=user_datastore, manifest=pybel_config_user_manifest)


def _register_users_from_manifest(user_datastore: SQLAlchemyUserDatastore, manifest: Dict) -> None:
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
            log.info('creating user: %s', email)
            user = user_datastore.create_user(
                confirmed_at=datetime.datetime.now(),
                email=email,
                password=user_manifest['password'],
                name=user_manifest['name']
            )

        for role_name in user_manifest.get('roles', []):
            if user_datastore.add_role_to_user(user, role_name):
                log.info('registered %s as %s', user, role_name)

    user_datastore.commit()


def register_error_handlers(app: Flask, sentry: Sentry) -> None:
    """Register the 500 and 403 error handlers."""

    @app.errorhandler(500)
    def internal_server_error(error):
        """Call this filter when there's an internal server error.

        Run a rollback and send some information to Sentry.
        """
        kwargs = {}
        if app.config.get(SENTRY_DSN):
            kwargs.update(dict(
                event_id=g.sentry_event_id,
                public_dsn=sentry.client.get_public_dsn('https')
            ))

        return render_template('errors/500.html', **kwargs)

    @app.errorhandler(403)
    def forbidden_error(error):
        """You must not cross this error"""
        return render_template('errors/403.html')


def register_examples(manager: Manager, user_datastore: SQLAlchemyUserDatastore) -> None:
    for graph in (sialic_acid_graph, egf_graph, statin_graph, homology_graph):
        if not manager.has_name_version(graph.name, graph.version):
            log.info('uploading public example graph: %s', graph)
            insert_graph(manager, graph, public=True)

    test_user = user_datastore.find_user(email='test@scai.fraunhofer.de')

    for graph in (braf_graph,):
        if not manager.has_name_version(graph.name, graph.version):
            log.info('uploading internal example graph: %s', graph)
            insert_graph(manager, graph, user=test_user, public=False)


def register_admin_service(app: Flask, manager: Manager, user_datastore: SQLAlchemyUserDatastore) -> Admin:
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
    admin.add_view(build_project_view(manager=manager, user_datastore=user_datastore))

    return admin
