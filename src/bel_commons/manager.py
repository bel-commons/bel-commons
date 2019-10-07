# -*- coding: utf-8 -*-

"""Extensions to the PyBEL manager to support BEL Commons."""

import logging
import time
from functools import lru_cache
from typing import Iterable, List, Optional

import networkx
from flask import Response, abort, current_app, render_template
from flask_security import current_user

import pybel.struct.query
from pybel import BELGraph
from pybel.manager.models import Author, Citation, Edge, Evidence, Namespace, Network, Node
from pybel_tools.utils import prepare_c3, prepare_c3_time_series
from .core.models import Query
from .manager_base import WebManagerBase, iter_recent_public_networks, iter_unique_networks
from .models import Experiment, Project, Report, User, UserQuery
from .utils import return_or_404

__all__ = [
    'WebManager',
]

log = logging.getLogger(__name__)


class _WebManager(WebManagerBase):
    """Extensions to the Web manager that entangle it with Flask."""

    def get_experiment_by_id_or_404(self, experiment_id: int) -> Experiment:
        """Get an experiment by its database identifier or 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_experiment_by_id(experiment_id),
            f'Experiment {experiment_id} does not exist',
        )

    def authenticated_get_experiment_by_id(self, user: User, experiment_id: int) -> Experiment:
        """Get an experiment by its database identifier, 404 if it doesn't exist, 403 if user doesn't have rights.

        :raises: werkzeug.exceptions.HTTPException
        """
        experiment = self.get_experiment_by_id_or_404(experiment_id)

        if experiment.public:
            return experiment

        if not user.is_authenticated:
            abort(403)

        if not user.has_experiment_rights(experiment):
            abort(403)

        return experiment

    def safe_get_experiments_by_ids(self, user: User, experiment_ids: Iterable[int]) -> List[Experiment]:
        """Get a list of experiments by their database identifiers or abort 404 if any don't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return [
            self.authenticated_get_experiment_by_id(user=user, experiment_id=experiment_id)
            for experiment_id in experiment_ids
        ]

    def get_namespace_by_id_or_404(self, namespace_id: int) -> Namespace:
        """Get a namespace by its database identifier or abort 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_namespace_by_id(namespace_id),
            f'namespace {namespace_id} does not exist',
        )

    def get_annotation_by_id_or_404(self, annotation_id: int) -> Namespace:
        """Get an annotation by its database identifier or abort 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return self.get_namespace_by_id_or_404(annotation_id)

    def get_citation_by_id_or_404(self, citation_id: int) -> Citation:
        """Get a citation by its database identifier or abort 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.session.query(Citation).get(citation_id),
            f'citation {citation_id} does not exist',
        )

    def get_citation_by_pmid_or_404(self, pubmed_identifier: str) -> Citation:
        """Get a citation by its PubMed identifier or abort 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_citation_by_pmid(pubmed_identifier=pubmed_identifier),
            f'citation with pmid:{pubmed_identifier} does not exist',
        )

    def get_author_by_name_or_404(self, name: str) -> Author:
        """Get an author by their name or abort 404 if they don't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_author_by_name(name),
            f'author named {name} does not exist',
        )

    def get_evidence_by_id_or_404(self, evidence_id: int) -> Evidence:
        """Get an evidence by its database identifier or abort 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.session.query(Evidence).get(evidence_id),
            f'evidence {evidence_id} does not exist',
        )

    def get_network_by_id_or_404(self, network_id: int) -> Network:
        """Get a network by its database identifier or aborts 404 if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_network_by_id(network_id),
            f'network {network_id} does not exist',
        )

    def authenticated_get_network_by_id_or_404(self, user: User, network_id: int) -> Network:
        """Get a network and abort if the user does not have permissions to view.

        :raises: werkzeug.exceptions.HTTPException
        """
        network = self.get_network_by_id_or_404(network_id)

        if user.is_authenticated and user.is_admin:
            return network

        if network.report and network.report.public:
            return network

        if self._network_has_permission(user=user, network_id=network.id):
            return network

        abort(403, f'{user} does not have access to network {network_id} ')

    @lru_cache(maxsize=256)
    def authenticated_query_from_network_by_id_or_404(self, user: User, network_id: int) -> Query:
        """Make a query from the given network."""
        network = self.authenticated_get_network_by_id_or_404(user=user, network_id=network_id)

        if isinstance(user, User):
            user_query = UserQuery.from_network(network, user=user if isinstance(user, User) else None)
            self.session.add(user_query)
            rv = user_query.query
        else:
            rv = Query.from_network(network)
            self.session.add(rv)

        self.session.commit()

        return rv

    def authenticated_get_graph_by_id_or_404(self, user: User, network_id: int) -> BELGraph:
        """Get the network as a BEL graph or aborts if the user does not have permission to view."""
        network = self.authenticated_get_network_by_id_or_404(user=user, network_id=network_id)
        return network.as_bel()

    def owner_get_network_by_id_or_404(self, user: User, network_id: int) -> Network:
        """Get a network and abort if the user does not have super rights.

        :raises: werkzeug.exceptions.HTTPException
        """
        network = self.get_network_by_id_or_404(network_id)

        if user.is_authenticated and (user.is_admin or user.owns_network(network)):
            return network

        abort(403, f'User {user} does own to network {network_id}')

    def authenticated_render_network_summary(self, user: User, network: Network, template: str) -> Response:
        """Render the graph summary page."""
        graph = network.as_bel()
        report: Report = network.report
        context = report.get_calculations()

        citation_years = context.citation_years
        function_count = context.function_count
        relation_count = context.relation_count
        error_count = context.error_count
        transformations_count = context.modifications_count
        hub_data = context.hub_data
        disease_data = context.disease_data
        variants_count = context.variants_count
        namespaces_count = context.namespaces_count

        overlaps = self.get_top_overlaps(user=user, network=network)
        network_versions = self.get_networks_by_name(network.name)

        return render_template(
            template,
            blueprints=set(current_app.blueprints),
            current_user=user,
            network=network,
            graph=graph,
            network_versions=network_versions,
            overlaps=overlaps,
            chart_1_data=prepare_c3(function_count, 'Entity Type'),
            chart_2_data=prepare_c3(relation_count, 'Relationship Type'),
            chart_3_data=prepare_c3(error_count, 'Error Type') if error_count else None,
            chart_4_data=prepare_c3(transformations_count) if transformations_count else None,
            number_transformations=sum(transformations_count.values()),
            chart_5_data=prepare_c3(variants_count, 'Node Variants'),
            number_variants=sum(variants_count.values()),
            chart_6_data=prepare_c3(namespaces_count, 'Namespaces'),
            number_namespaces=len(namespaces_count),
            chart_7_data=prepare_c3(hub_data, 'Top Hubs'),
            chart_9_data=prepare_c3(disease_data, 'Pathologies') if disease_data else None,
            chart_10_data=prepare_c3_time_series(citation_years, 'Number of articles') if citation_years else None,
            # **context
        )

    def authenticated_render_network_summary_or_404(self, network_id: int, user: User, template: str) -> Response:
        """Render a network if the current user has the necessary rights.

        :param network_id: The network to render
        :param user:
        :param template: The name of the template to render
        """
        network = self.authenticated_get_network_by_id_or_404(user=user, network_id=network_id)
        return self.authenticated_render_network_summary(user=user, network=network, template=template)

    def get_query_by_id_or_404(self, query_id: int) -> Query:
        """Get a query by its database identifier or abort 404 message if it doesn't exist.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_query_by_id(query_id),
            f'query {query_id} does not exist',
        )

    def authenticated_get_query_by_id_or_404(self, user: User, query_id: int) -> Query:
        """Get a query by its database identifier.

        - Raises an HTTPException with 404 if the query does not exist.
        - Raises an HTTPException with 403 if the user does not have the appropriate permissions for all networks in
          the query's assembly.

        :raises: werkzeug.exceptions.HTTPException
        """
        query = self._authenticated_get_query_by_id_or_404_helper(user=user, query_id=query_id)

        if query is None:
            abort(403, f'Insufficient rights to run query {query_id}')

        return query

    def _authenticated_get_query_by_id_or_404_helper(self, user: User, query_id: int) -> Optional[Query]:
        """Check if the user has the rights to run the given query."""
        query = self.get_query_by_id_or_404(query_id)

        log.debug('checking if user [%s] has rights to query [id=%s]', user, query_id)

        if user.is_authenticated and user.is_admin:
            log.debug('[%s] is admin and can access query [id=%d]', user, query_id)
            return query  # admins are never missing the rights to a query

        permissive_network_ids = self.get_network_ids_with_permission(user=user)

        if not any(network.id not in permissive_network_ids for network in query.assembly.networks):
            return query

    @lru_cache(maxsize=256)
    def authenticated_get_graph_from_query_id_or_404(self, user: User, query_id: int) -> BELGraph:
        """Process the GET request returning the filtered network.

        :raises: werkzeug.exceptions.HTTPException
        """
        log.debug(f'getting query [id={query_id}] from database')
        t = time.time()
        query = self.authenticated_get_query_by_id_or_404(user=user, query_id=query_id)
        log.debug(f'got query [id={query_id}] in {time.time() - t:.2f} seconds')

        log.debug(f'running query [id={query_id}]')
        t = time.time()
        try:
            result = query.run(self)
            log.debug(f'ran query [id={query_id}] in {time.time() - t:.2f} seconds')
        except networkx.exception.NetworkXError as e:
            log.warning(f'query [id={query_id}] failed after {time.time() - t:.2f} seconds')
            raise e

        return result

    def get_node_by_hash_or_404(self, node_hash: str) -> Node:
        """Get a node if it exists or send a 404.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_node_by_hash(node_hash),
            f'node {node_hash[:8]} does not exist',
        )

    def get_edge_by_hash_or_404(self, edge_hash: str) -> Edge:
        """Get an edge if it exists or send a 404.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_edge_by_hash(edge_hash),
            f'edge {edge_hash[:8]} does not exist',
        )

    def get_project_by_id_or_404(self, project_id: int) -> Project:
        """Get a project by its database identifier or send a 404.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_project_by_id(project_id),
            f'project {project_id} does not exist',
        )

    def authenticated_get_project_by_id_or_404(self, user: User, project_id: int) -> Project:
        """Get a project by identifier, aborts 404 if doesn't exist and aborts 403 if current user does not have rights.

        :raises: werkzeug.exceptions.HTTPException
        """
        project = self.get_project_by_id_or_404(project_id)

        if not user.has_project_rights(project):
            abort(403, f'User {user} does not have permission to access project {project}')

        return project

    def get_user_by_id_or_404(self, user_id: int) -> User:
        """Get a user by identifier if it exists or send a 404.

        :raises: werkzeug.exceptions.HTTPException
        """
        return return_or_404(
            self.get_user_by_id(user_id),
            f'user {user_id} does not exist',
        )


class WebManager(_WebManager):
    """A manager for BEL Commons that uses the current user for authentication."""

    def cu_query_from_network_by_id_or_404(self, network_id: int) -> Query:
        """Get a query for the given network or 404 if it doesn't exist while authenticated as the current user."""
        return self.authenticated_query_from_network_by_id_or_404(user=current_user, network_id=network_id)

    def cu_authenticated_get_graph_by_id_or_404(self, network_id: int) -> BELGraph:
        """Get a graph or 404 if it doesn't exist while authenticated as the current user."""
        return self.authenticated_get_graph_by_id_or_404(user=current_user, network_id=network_id)

    def cu_owner_get_network_by_id_or_404(self, network_id: int) -> Network:
        """Get a network if the current user is the owner."""
        return self.owner_get_network_by_id_or_404(user=current_user, network_id=network_id)

    def cu_get_network_by_id_or_404(self, network_id: int) -> Network:
        """Get a network or 404 if it doesn't exist while authenticated as the current user."""
        return self.authenticated_get_network_by_id_or_404(user=current_user, network_id=network_id)

    def cu_render_network_summary_or_404(self, network_id: int, template: str) -> Response:
        """Render the summary for a network while authenticated as the current user."""
        return self.authenticated_render_network_summary_or_404(
            user=current_user,
            network_id=network_id,
            template=template,
        )

    def cu_get_query_by_id_or_404(self, query_id: int) -> Query:
        """Get a query or 404 if it doesn't exist while authenticated as the current user."""
        return self.authenticated_get_query_by_id_or_404(user=current_user, query_id=query_id)

    def cu_get_graph_from_query_id_or_404(self, query_id: int) -> Optional[BELGraph]:
        """Get a BEL graph from the query or 404 if it doesn't exist while authenticated as the current user."""
        return self.authenticated_get_graph_from_query_id_or_404(user=current_user, query_id=query_id)

    def cu_authenticated_get_project_by_id_or_404(self, project_id: int) -> Project:
        """Get a project or 404 if it doesn't exist while authenticated as the current user."""
        return self.authenticated_get_project_by_id_or_404(user=current_user, project_id=project_id)

    def cu_list_networks(self) -> List[Network]:
        """List networks available to the current user."""
        return self.authenticated_list_networks(user=current_user)

    def authenticated_list_networks(self, user: User) -> List[Network]:
        """Get all networks tagged as public or uploaded by the current user.

        :return: A list of all networks tagged as public or uploaded by the current user
        """
        if not user.is_authenticated:
            return list(iter_recent_public_networks(self))

        if user.is_admin:
            return self.list_recent_networks()

        return list(iter_unique_networks(self.iter_networks_with_permission(user)))

    # FIXME needs more logic for what logged in users/admins/anonymous users see
    def list_queries(self) -> List[Query]:
        """List all user queries in the database."""
        q = self.session.query(UserQuery)

        if not (current_user.is_authenticated and current_user.is_admin):
            q = q.filter(UserQuery.public)

        q = q.order_by(UserQuery.created.desc())
        return q.all()

    def build_query(self, q: pybel.struct.query.Query) -> Query:
        """Build a query model from a PyBEL query."""
        if isinstance(current_user, User):
            user_query = UserQuery.from_query(manager=self, query=q, user=current_user)
            self.session.add(user_query)
            rv = user_query.query
        else:
            rv = Query.from_query(manager=self, query=q)
            self.session.add(rv)
        self.session.commit()
        return rv

    def build_query_from_project(self, project: Project) -> Query:
        """Build a query from a project."""
        user_query = UserQuery.from_project(project=project, user=current_user)
        user_query.query.assembly.name = f'{time.asctime()} query of {project.name}'
        self.session.add(user_query)
        self.session.commit()
        return user_query.query

    def build_query_from_node(self, node: Node) -> Query:
        """Build a query from a node model."""
        q = pybel.struct.query.Query([network.id for network in node.networks])
        q.append_seeding_neighbors(node.as_bel())
        return self.build_query(q)
