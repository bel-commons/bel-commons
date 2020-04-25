# -*- coding: utf-8 -*-

"""Extensions to the PyBEL manager to support PyBEL-Web."""

import datetime
import itertools as itt
import logging
import time
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

import werkzeug.datastructures
from flask_security import SQLAlchemyUserDatastore
from sqlalchemy import and_, func

from pybel import Manager
from pybel.manager.models import Edge, Namespace, Network
from .constants import AND
from .models import (
    Assembly, EdgeComment, EdgeVote, Experiment, NetworkOverlap, Omic, Project, Query, Report, Role,
    User,
)
from .tools_compat import min_tanimoto_set_similarity

__all__ = [
    'WebManagerBase',
    'iter_unique_networks',
    'iter_recent_public_networks',
]

logger = logging.getLogger(__name__)


def sanitize_annotation(annotation_list: List[str]) -> Mapping[str, List[str]]:
    """Convert an annotation (annotation:value) to tuple."""
    annotation_dict = defaultdict(list)

    for annotation_string in annotation_list:
        annotation, annotation_value = annotation_string.split(":")[0:2]
        annotation_dict[annotation].append(annotation_value)

    return dict(annotation_dict)


def iter_unique_networks(networks: Iterable[Network]) -> Iterable[Network]:
    """Yield only unique networks from an iterator."""
    seen_ids = set()

    for network in networks:
        if not network:
            continue

        if network.id not in seen_ids:
            seen_ids.add(network.id)
            yield network


def to_snake_case(function_name: str) -> str:
    """Convert method.__name__ from capital and spaced to lower and underscore separated."""
    return function_name.replace(" ", "_").lower()


class PyBELSQLAlchemyUserDataStore(SQLAlchemyUserDatastore):
    """Wraps :class:`flask_security.SQLAlchemyUserDatastore` with the BEL Commons User and Role models."""

    def __init__(self, db) -> None:  # noqa:D107
        super().__init__(db=db, user_model=User, role_model=Role)


class WebManagerBase(Manager):
    """Extensions to the PyBEL manager and :class:`SQLAlchemyUserDataStore` to support PyBEL-Web."""

    def __init__(self, *args, **kwargs) -> None:  # noqa:D107
        super().__init__(*args, **kwargs)
        self.user_datastore = PyBELSQLAlchemyUserDataStore(self)

    def iter_networks_with_permission(self, user: User) -> Iterable[Network]:
        """Get an iterator over all the networks from all the sources."""
        if not user.is_authenticated:
            logger.debug('getting only public networks for anonymous user')
            yield from iter_recent_public_networks(self)

        elif user.is_admin:
            logger.debug('getting all recent networks for admin')
            yield from self.list_recent_networks()

        else:
            logger.debug(f'getting all networks for user [{user}]')
            yield from user.iter_available_networks()
            yield from iter_recent_public_networks(self)

    def get_network_ids_with_permission(self, user: User) -> Set[int]:
        """Get the set of networks ids tagged as public or uploaded by the user."""
        return {
            network.id
            for network in self.iter_networks_with_permission(user)
        }

    def get_project_by_id(self, project_id) -> Optional[Project]:
        """Get a project by its database identifier, if it exists."""
        return self.session.query(Project).get(project_id)

    def get_experiment_by_id(self, experiment_id) -> Optional[Experiment]:
        """Get an experiment by its database identifier, if it exists."""
        return self.session.query(Experiment).get(experiment_id)

    def get_omic_by_id(self, omic_id) -> Optional[Omic]:
        """Get an -*omics* data set by its database identifier, if it exists."""
        return self.session.query(Omic).get(omic_id)

    def get_query_by_id(self, query_id) -> Optional[Query]:
        """Get a query by its database identifier, if it exists."""
        return self.session.query(Query).get(query_id)

    def get_user_by_id(self, user_id) -> Optional[User]:
        """Get a user by its database identifier, if it exists."""
        return self.session.query(User).get(user_id)

    def get_report_by_id(self, report_id) -> Optional[Report]:
        """Get a report by its database identifier, if it exists."""
        return self.session.query(Report).get(report_id)

    def count_reports(self) -> int:
        """Count the reports in the database."""
        return self._count_model(Report)

    def count_users(self) -> int:
        """Count the users in the database."""
        return self._count_model(User)

    def count_queries(self) -> int:
        """Count the queries in the database."""
        return self._count_model(Query)

    def count_assemblies(self) -> int:
        """Count the assemblies in the database."""
        return self._count_model(Assembly)

    def get_namespace_by_id(self, namespace_id) -> Optional[Namespace]:
        """Get a namespace by its identifier, if it exists."""
        return self.session.query(Namespace).get(namespace_id)

    def drop_queries_by_user_id(self, user_id: int) -> None:  # FIXME
        """Drop queries associated with the given user."""
        self.session.query(Query).filter(Query.user_id == user_id).delete()
        self.session.commit()

    def _network_has_permission(self, user: User, network_id: int) -> bool:
        return network_id in self.get_network_ids_with_permission(user)

    def get_edge_vote_by_user(self, edge: Edge, user: User) -> Optional[EdgeVote]:
        """Look up a vote by the edge and user.

        :param edge: The edge that is being evaluated
        :param user: The user making the vote
        """
        vote_filter = and_(EdgeVote.edge == edge, EdgeVote.user == user)
        return self.session.query(EdgeVote).filter(vote_filter).one_or_none()

    def get_or_create_vote(self, edge: Edge, user: User, agreed: Optional[bool] = None) -> EdgeVote:
        """Get a vote for the given edge and user.

        :param edge: The edge that is being evaluated
        :param user: The user making the vote
        :param agreed: Optional value of agreement to put into vote
        """
        vote = self.get_edge_vote_by_user(edge, user)

        if vote is None:
            vote = EdgeVote(
                edge=edge,
                user=user,
                agreed=agreed,
            )
            self.session.add(vote)
            self.session.commit()

        # If there was already a vote, and it's being changed
        elif agreed is not None:
            vote.agreed = agreed
            vote.changed = datetime.datetime.utcnow()
            self.session.commit()

        return vote

    def _help_get_edge_entry(self, edge: Edge, user: User) -> Mapping:
        """Get edge information by edge identifier."""
        data = edge.to_json()

        data['comments'] = [
            {
                'user': {
                    'id': edge_comment.user_id,
                    'email': edge_comment.user.email
                },
                'comment': edge_comment.comment,
                'created': edge_comment.created,
            }
            for edge_comment in self.session.query(EdgeComment).filter(EdgeComment.edge == edge)
        ]

        if user.is_authenticated:
            edge_vote = self.get_or_create_vote(edge, user)
            data['vote'] = (
                0 if (edge_vote is None or edge_vote.agreed is None) else
                1 if edge_vote.agreed else
                -1  # noqa: W503
            )

        return data

    def get_node_overlaps(self, network: Network) -> Mapping[int, Tuple[Network, float]]:
        """Calculate overlaps to all other networks in the database.

        :return: A dictionary from {int network_id: (network, float similarity)} for this network to all other networks
        """
        t = time.time()

        nodes = set(node.id for node in network.nodes)

        incoming_overlaps = (
            (ol.left_id, ol.left, ol.overlap)
            for ol in network.incoming_overlaps
        )
        outgoing_overlaps = (
            (ol.right_id, ol.right, ol.overlap)
            for ol in network.overlaps
        )

        rv = {
            other_network_id: (other_network, overlap)
            for other_network_id, other_network, overlap in itt.chain(incoming_overlaps, outgoing_overlaps)
        }

        uncached_networks = list(
            other_network
            for other_network in self.list_recent_networks()
            if other_network.id != network.id and other_network.id not in rv
        )

        if uncached_networks:
            logger.debug('caching overlaps for network [id=%s]', network)

            for other_network in uncached_networks:
                other_network_nodes = set(node.id for node in other_network.nodes)
                overlap = min_tanimoto_set_similarity(nodes, other_network_nodes)
                rv[other_network.id] = other_network, overlap
                no = NetworkOverlap.build(left=network, right=other_network, overlap=overlap)
                self.session.add(no)

            self.session.commit()

            logger.debug('cached overlaps for network [id=%s] in %.2f seconds', network, time.time() - t)

        return rv

    def get_top_overlaps(self, network: Network, user: User, n: Optional[int] = 10) -> List[Tuple[Network, float]]:
        """Get the top n most overlapping networks with the given network."""
        overlap_counter = self.get_node_overlaps(network)
        allowed_network_ids = self.get_network_ids_with_permission(user)

        overlaps = [
            (other_network, v)
            for network_id, (other_network, v) in sorted(overlap_counter.items(), key=lambda t: t[1][1], reverse=True)
            if network_id in allowed_network_ids and v > 0.0
        ]

        if n is not None:
            return overlaps[:n]
        return overlaps

    def get_recent_reports(self, weeks: int = 2) -> Iterable[str]:
        """Get reports from the last two weeks.

        :param weeks: The number of weeks to look backwards (builds :class:`datetime.timedelta`)
        :return: An iterable of the string that should be reported
        """
        now = datetime.datetime.utcnow()
        delta = datetime.timedelta(weeks=weeks)
        q = self.session.query(Report).filter(Report.created - now < delta).join(Network).group_by(Network.name)
        q1 = q.having(func.min(Report.created)).order_by(Network.name.asc()).all()
        q2 = q.having(func.max(Report.created)).order_by(Network.name.asc()).all()

        q3 = self.session.query(Report, func.count(Report.network)). \
            filter(Report.created - now < delta). \
            join(Network).group_by(Network.name). \
            order_by(Network.name.asc()).all()

        for a, b, (_, count) in zip(q1, q2, q3):
            yield a.network.name

            if a.network.version == b.network.version:
                yield f'\tUploaded only {a.network.version}'
                yield f'\tNodes: {a.number_nodes}'
                yield f'\tEdges: {a.number_edges}'
                yield f'\tWarnings: {a.number_warnings}'
            else:
                yield f'\tUploads: {count}'
                yield f'\tVersion: {a.network.version} -> {b.network.version}'
                yield f'\tNodes: {a.number_nodes} {b.number_nodes - a.number_nodes:+d} {b.number_nodes}'
                yield f'\tEdges: {a.number_edges} {b.number_edges - a.number_edges:+d} {b.number_edges}'
                yield f'\tWarnings: {a.number_warnings} {b.number_warnings - a.number_warnings:+d} {b.number_warnings}'

            yield ''

    def convert_seed_value(self, key: str, form: werkzeug.datastructures.ImmutableMultiDict, value: str):
        """Normalize the form to type:data format.

        :param key: seed method
        :param form: Form dictionary
        :param value: data (nodes, authors...)
        :return: Normalized data depending on the seeding method
        """
        if key == 'annotation':
            return {
                'annotations': sanitize_annotation(form.getlist(value)),
                'or': not form.get(AND),
            }

        if key in {'pubmed', 'authors'}:
            return form.getlist(value)

        node_hashes = form.getlist(value)
        return [
            self.get_dsl_by_hash(node_hash)
            for node_hash in node_hashes
        ]

    def query_form_to_dict(self, form: werkzeug.datastructures.ImmutableMultiDict) -> Dict:
        """Convert a request.form multidict to the query JSON format.

        :return: json representation of the query
        """
        query_dict = {}

        pairs = [
            ('pubmed', "pubmed_selection[]"),
            ('authors', 'author_selection[]'),
            ('annotation', 'annotation_selection[]'),
            (form["seed_method"], "node_selection[]"),
        ]

        query_dict['seeding'] = [
            {
                "type": seed_method,
                'data': self.convert_seed_value(seed_method, form, seed_data_argument),
            }
            for seed_method, seed_data_argument in pairs
            if form.getlist(seed_data_argument)
        ]

        query_dict["pipeline"] = [
            {
                'function': to_snake_case(function_name),
            }
            for function_name in form.getlist("pipeline[]")
            if function_name
        ]

        network_ids = form.getlist("network_ids[]", type=int)
        if network_ids:
            query_dict["network_ids"] = network_ids

        return query_dict


def iter_recent_public_networks(manager: Manager) -> Iterable[Network]:
    """Iterate over the recent networks from that have been made public."""
    for network in manager.list_recent_networks():
        if network.report and network.report.public:
            yield network
