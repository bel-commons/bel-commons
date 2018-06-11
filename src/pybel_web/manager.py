# -*- coding: utf-8 -*-

"""Extensions to the PyBEL manager to support PyBEL-Web."""

import datetime
import itertools as itt
import logging
from collections import defaultdict
from functools import lru_cache

import networkx
import time
from flask import abort, render_template
from flask_security import SQLAlchemyUserDatastore
from sqlalchemy import and_, func

from pybel.manager import Network
from pybel.manager.cache_manager import _Manager
from pybel.manager.models import Annotation, Citation, Evidence, Namespace
from pybel.struct.summary import count_namespaces
from pybel_tools.summary import count_variants
from pybel_tools.utils import min_tanimoto_set_similarity, prepare_c3, prepare_c3_time_series
from .constants import AND
from .manager_utils import get_network_summary_dict
from .models import EdgeComment, EdgeVote, Experiment, NetworkOverlap, Omic, Project, Query, Report, Role, User

__all__ = [
    'WebManager',
]

log = logging.getLogger(__name__)


def sanitize_annotation(annotation_list):
    """Converts annotation (Annotation:value) to tuple

    :param list[str] annotation_list:
    :return: annotation dictionary
    :rtype: dict[str,list[str]]
    """
    annotation_dict = defaultdict(list)

    for annotation_string in annotation_list:
        annotation, annotation_value = annotation_string.split(":")[0:2]
        annotation_dict[annotation].append(annotation_value)

    return dict(annotation_dict)


def unique_networks(networks):
    """Only yields unique networks

    :param iter[Network] networks: An iterable of networks
    :return: An iterable over the unique network identifiers in the original iterator
    :rtype: iter[Network]
    """
    seen_ids = set()

    for network in networks:
        if not network:
            continue

        if network.id not in seen_ids:
            seen_ids.add(network.id)
            yield network


def to_snake_case(function_name):
    """Converts method.__name__ from capital and spaced to lower and underscore separated

    :param str function_name:
    :return: function name sanitized
    :rtype: str
    """
    return function_name.replace(" ", "_").lower()


class WebManager(_Manager):
    """Extensions to the PyBEL manager and :class:`SQLAlchemyUserDataStore` to support PyBEL-Web."""

    def __init__(self, engine, session):
        super(_Manager, self).__init__(engine=engine, session=session)

        self.user_datastore = SQLAlchemyUserDatastore(self, User, Role)

    def iter_recent_public_networks(self):
        """List the recent networks from that have been made public.

        Wraps :meth:`pybel.manager.Manager.list_recent_networks()` and checks their associated reports.

        :rtype: iter[Network]
        """
        return (
            network
            for network in self.list_recent_networks()
            if network.report and network.report.public
        )

    def _iterate_networks_for_user(self, user):
        """
        :param models.User user: A user
        :rtype: iter[Network]
        """
        yield from self.iter_recent_public_networks()
        yield from user.iter_available_networks()

        # TODO reinvestigate how "organizations" are handled
        if user.is_scai:
            role = self.user_datastore.find_or_create_role(name='scai')
            for user in role.users:
                yield from user.iter_owned_networks()

    def iter_networks_with_permission(self, user):
        """Gets an iterator over all the networks from all the sources

        :param models.User user: A user
        :rtype: iter[Network]
        """
        if not user.is_authenticated:
            log.debug('getting only public networks for anonymous user')
            yield from self.iter_recent_public_networks()

        elif user.is_admin:
            log.debug('getting all recent networks for admin')
            yield from self.list_recent_networks()

        else:
            log.debug('getting all networks for user [%s]', self)
            yield from self._iterate_networks_for_user(user)

    def get_network_ids_with_permission(self, user):
        """Gets the set of networks ids tagged as public or uploaded by the user

        :param User user: A user
        :return: A list of all networks tagged as public or uploaded by the user
        :rtype: set[int]
        """
        networks = self.iter_networks_with_permission(user)
        return {network.id for network in networks}

    def register_users_from_manifest(self, manifest):
        """Register the users and roles in a manifest.

        :param dict manifest: A manifest dictionary, which contains two keys: ``roles`` and ``users``. The ``roles``
         key corresponds to a list of dictionaries containing ``name`` and ``description`` entries. The ``users`` key
         corresponds to a list of dictionaries containing ``email``, ``password``, and ``name`` entries
         as well as a optional ``roles`` entry with a corresponding list relational to the names in the ``roles``
         entry in the manifest.
        """
        for role in manifest['roles']:
            self.user_datastore.find_or_create_role(**role)

        for user_manifest in manifest['users']:
            email = user_manifest['email']
            user = self.user_datastore.find_user(email=email)
            if user is None:
                log.info('creating user: %s', email)
                user = self.user_datastore.create_user(
                    confirmed_at=datetime.datetime.now(),
                    email=email,
                    password=user_manifest['password'],
                    name=user_manifest['name']
                )

            for role_name in user_manifest.get('roles', []):
                if self.user_datastore.add_role_to_user(user, role_name):
                    log.info('registered %s as %s', user, role_name)

        self.user_datastore.commit()

    def get_project_by_id(self, project_id):
        return self.session.query(Project).get(project_id)

    def get_experiment_by_id(self, experiment_id):
        return self.session.query(Experiment).get(experiment_id)

    def get_omic_by_id(self, omic_id):
        return self.session.query(Omic).get(omic_id)

    def get_query_by_id(self, query_id):
        return self.session.query(Query).get(query_id)

    def get_user_by_id(self, user_id):
        return self.session.query(User).get(user_id)

    def get_report_by_id(self, report_id):
        return self.session.query(Report).get(report_id)

    def count_reports(self):
        return self.session.query(Report).count()

    def count_users(self):
        return self.session.query(User).count()

    def count_queries(self):
        return self.session.query(Query).count()

    def count_assemblies(self):
        return self.session.query(Assembly).count()

    def get_experiment_or_404(self, experiment_id):
        experiment = self.get_experiment_by_id(experiment_id)

        if experiment is None:
            abort(404, 'Experiment {} does not exist'.format(experiment_id))

        return experiment

    def safe_get_experiment(self, user, experiment_id):
        """Get an experiment by its databse identifier or 404 if it doesn't exist.

        :param User user:
        :param int experiment_id:
        :rtype: Experiment
        :raises: werkzeug.exceptions.HTTPException
        """
        experiment = self.get_experiment_or_404(experiment_id)

        if not user.has_experiment_rights(experiment):
            abort(403, 'You do not have rights to drop this experiment')

        return experiment

    def safe_get_experiments(self, user, experiment_ids):
        """Get a list of experiments by their database identifiers or abort 404 if any don't exist.

        :param User user:
        :param list[int] experiment_ids:
        :rtype: list[Experiment]
        """
        return [
            self.safe_get_experiment(user=user, experiment_id=experiment_id)
            for experiment_id in experiment_ids
        ]

    def get_namespace_by_id_or_404(self, namespace_id):
        """Get a namespace by its database identifier or abort 404 if it doesn't exist.

        :param namespace_id: The namespace's database identifier
        :rtype: pybel.manager.models.Namespace
        :raises: werkzeug.exceptions.HTTPException
        """
        namespace = self.session.query(Namespace).get(namespace_id)

        if namespace is None:
            abort(404)

        return namespace

    def get_annotation_or_404(self, annotation_id):
        """Get an annotation by its database identifier or abort 404 if it doesn't exist.

        :param annotation_id: The annotation's database identifier
        :rtype: pybel.manager.models.Annotation
        :raises: werkzeug.exceptions.HTTPException
        """
        annotation = self.session.query(Annotation).get(annotation_id)

        if annotation is None:
            abort(404)

        return annotation

    def get_citation_by_id_or_404(self, citation_id):
        """Get a citation by its database identifier or abort 404 if it doesn't exist.

        :param citation_id: The citation's database identifier
        :rtype: pybel.manager.models.Citation
        :raises: werkzeug.exceptions.HTTPException
        """
        citation = self.session.query(Citation).get(citation_id)
        if citation is None:
            abort(404)
        return citation

    def get_citation_by_pmid_or_404(self, pubmed_identifier):
        """Get a citation by its PubMed identifier or abort 404 if it doesn't exist.

        :param pubmed_identifier:
        :rtype: pybel.manager.models.Citation
        :raises: werkzeug.exceptions.HTTPException
        """
        citation = self.get_citation_by_pmid(pubmed_identifier=pubmed_identifier)

        if citation is None:
            abort(404)

        return citation

    def get_author_by_name_or_404(self, name):
        """Get an author by their name or abort 404 if they don't exist.

        :param str name: The author's name
        :rtype: pybel.manager.models.Author
        :raises: werkzeug.exceptions.HTTPException
        """
        author = self.get_author_by_name(name)

        if author is None:
            return abort(404)

        return author

    def get_evidence_by_id_or_404(self, evidence_id):
        """Get an evidence by its database identifier or abort 404 if it doesn't exist.

        :param int evidence_id: The evidence's database identifier
        :rtype: pybel.manager.models.Evidence
        :raises: werkzeug.exceptions.HTTPException
        """
        evidence = self.session.query(Evidence).get(evidence_id)

        if evidence is None:
            abort(404)

        return evidence

    def get_network_or_404(self, network_id):
        """Gets a network by its database identifier or aborts 404 if it doesn't exist.

        :param int network_id: The identifier of the network
        :rtype: Network
        :raises: werkzeug.exceptions.HTTPException
        """
        network = self.get_network_by_id(network_id)

        if network is None:
            abort(404, 'Network {} does not exist'.format(network_id))

        return network

    def get_query_or_404(self, query_id):
        """Get a query by its database identifier or abort 404 message if it doesn't exist.

        :param int query_id: The database identifier for a query
        :rtype: Query
        :raises: werkzeug.exceptions.HTTPException
        """
        query = self.get_query_by_id(query_id)

        if query is None:
            abort(404, 'Missing query: {}'.format(query_id))

        return query

    def get_node_by_hash_or_404(self, node_hash):
        """Gets a node's hash or sends a 404 missing message

        :param str node_hash: A PyBEL node hash
        :rtype: pybel.manager.models.Node
        :raises: werkzeug.exceptions.HTTPException
        """
        node = self.get_node_by_hash(node_hash)

        if node is None:
            abort(404, 'Node not found: {}'.format(node_hash))

        return node

    def get_edge_by_hash_or_404(self, edge_hash):
        """Gets an edge if it exists or sends a 404

        :param str edge_hash: A PyBEL edge hash
        :rtype: Edge
        :raises: werkzeug.exceptions.HTTPException
        """
        edge = self.get_edge_by_hash(edge_hash)

        if edge is None:
            abort(404, 'Edge not found: {}'.format(edge_hash))

        return edge

    def get_project_or_404(self, project_id):
        """Get a project by id and aborts 404 if doesn't exist

        :param int project_id: The identifier of the project
        :rtype: Project
        :raises: werkzeug.exceptions.HTTPException
        """
        project = self.get_project_by_id(project_id)

        if project is None:
            abort(404, 'Project {} does not exist'.format(project_id))

        return project

    def get_user_or_404(self, user_id):
        """

        :param user_id:
        :return: User
        :raises: werkzeug.exceptions.HTTPException
        """
        user = self.get_user_by_id(user_id)

        if user is None:
            abort(404)

        return user

    def drop_queries_by_user_id(self, user_id):
        self.session.query(Query).filter(Query.user_id == user_id).delete()
        self.session.commit()

    def _network_has_permission(self, user, network_id):
        """
        :param User user:
        :param int network_id:
        :rtype: bool
        """
        return network_id in self.get_network_ids_with_permission(user)

    def safe_get_network(self, user, network_id):
        """Get a network and abort if the user does not have permissions to view.

        :param User user:
        :param int network_id: The identifier of the network
        :rtype: Network
        :raises: werkzeug.exceptions.HTTPException
        """
        network = self.get_network_or_404(network_id)

        if user.is_authenticated and user.is_admin:
            return network

        if network.report and network.report.public:
            return network

        if self._network_has_permission(user=user, network_id=network.id):
            return network

        abort(403)

    def safe_get_graph(self, user, network_id):
        """Get the network as a BEL graph or aborts if the user does not have permission to view.

        :param User user:
        :type network_id: int
        :rtype: pybel.BELGraph
        """
        network = self.safe_get_network(user=user, network_id=network_id)

        if network is None:
            return

        return network.as_bel()

    def strict_get_network(self, user, network_id):
        """Get a network and abort if the user does not have super rights.

        :param User user:
        :param int network_id: The identifier of the network
        :rtype: Network
        :raises: werkzeug.exceptions.HTTPException
        """
        network = self.get_network_or_404(network_id)

        if user.is_authenticated and (user.is_admin or user.owns_network(network)):
            return network

        abort(403, 'User {} does not have super user rights to network {}'.format(user, network))

    def safe_get_project(self, user, project_id):
        """Get a project by identifier, aborts 404 if doesn't exist and aborts 403 if current user does not have rights.

        :param User user:
        :param int project_id: The identifier of the project
        :rtype: Project
        :raises: werkzeug.exceptions.HTTPException
        """
        project = self.get_project_or_404(project_id)

        if not user.has_project_rights(project):
            abort(403, 'User {} does not have permission to access Project {}'.format(user, project))

        return project

    def get_networks_with_permission(self, user):
        """Gets all networks tagged as public or uploaded by the current user

        :return: A list of all networks tagged as public or uploaded by the current user
        :rtype: list[Network]
        """
        if not user.is_authenticated:
            return list(self.iter_recent_public_networks())

        if user.is_admin:
            return self.list_recent_networks()

        return list(unique_networks(self.iter_networks_with_permission(user)))

    def get_edge_vote_by_user(self, edge, user):
        """Look up a vote by the edge and user.

        :param Edge edge: The edge that is being evaluated
        :param User user: The user making the vote
        :rtype: Optional[EdgeVote]
        """
        vote_filter = and_(EdgeVote.edge == edge, EdgeVote.user == user)
        return self.session.query(EdgeVote).filter(vote_filter).one_or_none()

    def get_or_create_vote(self, edge, user, agreed=None):
        """Get a vote for the given edge and user.

        :param Edge edge: The edge that is being evaluated
        :param User user: The user making the vote
        :param bool agreed: Optional value of agreement to put into vote
        :rtype: EdgeVote
        """
        vote = self.get_edge_vote_by_user(edge, user)

        if vote is None:
            vote = EdgeVote(
                edge=edge,
                user=user,
                agreed=agreed
            )
            self.session.add(vote)
            self.session.commit()

        # If there was already a vote, and it's being changed
        elif agreed is not None:
            vote.agreed = agreed
            vote.changed = datetime.datetime.utcnow()
            self.session.commit()

        return vote

    def help_get_edge_entry(self, edge, user):
        """Get edge information by edge identifier.

        :param Edge edge: The  given edge
        :param User user:
        :return: A dictionary representing the information about the given edge
        :rtype: dict
        """
        data = edge.to_json()

        data['comments'] = [
            {
                'user': {
                    'id': ec.user_id,
                    'email': ec.user.email
                },
                'comment': ec.comment,
                'created': ec.created,
            }
            for ec in self.session.query(EdgeComment).filter(EdgeComment.edge == edge)
        ]

        if user.is_authenticated:
            vote = self.get_or_create_vote(edge, user)
            data['vote'] = 0 if (vote is None or vote.agreed is None) else 1 if vote.agreed else -1

        return data

    def get_node_overlaps(self, network):
        """Calculate overlaps to all other networks in the database.

        :param Network network:
        :return: A dictionary from {int network_id: (network, float similarity)} for this network to all other networks
        :rtype: dict[int,tuple[Network,float]]
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
            log.debug('caching overlaps for network [id=%s]', network)

            for other_network in uncached_networks:
                other_network_nodes = set(node.id for node in other_network.nodes)
                overlap = min_tanimoto_set_similarity(nodes, other_network_nodes)
                rv[other_network.id] = other_network, overlap
                no = NetworkOverlap.build(left=network, right=other_network, overlap=overlap)
                self.session.add(no)

            self.session.commit()

            log.debug('cached overlaps for network [id=%s] in %.2f seconds', network, time.time() - t)

        return rv

    def get_top_overlaps(self, network, user, number=10):
        """

        :param Network network:
        :param User user:
        :param number:
        :return:
        """
        overlap_counter = self.get_node_overlaps(network)
        allowed_network_ids = self.get_network_ids_with_permission(user)

        overlaps = [
            (network, v)
            for network_id, (network, v) in sorted(overlap_counter.items(), key=lambda t: t[1][1], reverse=True)
            if network_id in allowed_network_ids and v > 0.0
        ]
        return overlaps[:number]

    def safe_render_network_summary(self, user, network, template):
        """Renders the graph summary page

        :param User user:
        :param Network network:
        :param str template:
        :rtype: flask.Response
        """
        graph = network.as_bel()

        try:
            er = network.report.get_calculations()
        except Exception:  # TODO remove this later
            log.warning('Falling back to on-the-fly calculation of summary of %s', network)
            er = get_network_summary_dict(graph)

            if network.report:
                network.report.dump_calculations(er)
                self.session.commit()

        citation_years = er['citation_years']
        function_count = er['function_count']
        relation_count = er['relation_count']
        error_count = er['error_count']
        transformations_count = er['modifications_count']
        hub_data = er['hub_data']
        disease_data = er['disease_data']
        overlaps = self.get_top_overlaps(user=user, network=network)
        network_versions = self.get_networks_by_name(graph.name)
        variants_count = count_variants(graph)
        namespaces_count = count_namespaces(graph)

        return render_template(
            template,
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
            **er
        )

    def render_network_summary_safe(self, network_id, user, template):
        """Renders a network if the current user has the necessary rights

        :param int network_id: The network to render
        :param User user:
        :param str template: The name of the template to render
        :rtype: flask.Response
        """
        network = self.safe_get_network(user=user, network_id=network_id)
        return self.safe_render_network_summary(user=user, network=network, template=template)

    def get_recent_reports(self, weeks=2):
        """Gets reports from the last two weeks

        :param pybel.manager.Manager self: A cache manager
        :param int weeks: The number of weeks to look backwards (builds :class:`datetime.timedelta`)
        :return: An iterable of the string that should be reported
        :rtype: iter[str]
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
                yield '\tUploaded only {}'.format(a.network.version)
                yield '\tNodes: {}'.format(a.number_nodes)
                yield '\tEdges: {}'.format(a.number_edges)
                yield '\tWarnings: {}'.format(a.number_warnings)
            else:
                yield '\tUploads: {}'.format(count)
                yield '\tVersion: {} -> {}'.format(a.network.version, b.network.version)
                yield '\tNodes: {} {:+d} {}'.format(a.number_nodes, b.number_nodes - a.number_nodes, b.number_nodes)
                yield '\tEdges: {} {:+d} {}'.format(a.number_edges, b.number_edges - a.number_edges, b.number_edges)
                yield '\tWarnings: {} {:+d} {}'.format(a.number_warnings, b.number_warnings - a.number_warnings,
                                                       b.number_warnings)
            yield ''

    def get_query_ancestor_id(self, query_id):  # TODO refactor this to be part of Query class
        """Gets the oldest ancestor of the given query

        :param int query_id: The original query database identifier
        :rtype: Query
        """
        query = self.get_query_by_id(query_id)

        if not query.parent_id:
            return query_id

        return self.get_query_ancestor_id(query.parent_id)

    @lru_cache(maxsize=256)
    def query_from_network_with_current_user(self, user, network_id, autocommit=True):
        """Makes a query from the given network

        :param User user: The user making the query
        :param int network_id: The network's database identifier
        :param bool autocommit: Should the query be committed immediately
        :rtype: Query
        """
        network = self.safe_get_network(user=user, network_id=network_id)
        query = Query.from_network(network, user=user)

        if autocommit:
            self.session.add(query)
            self.session.commit()

        return query

    def convert_seed_value(self, key, form, value):
        """ Normalize the form to type:data format

        :param str key: seed method
        :param ImmutableMultiDict form: Form dictionary
        :param str value: data (nodes, authors...)
        :return: Normalized data depending on the seeding method
        """
        if key == 'annotation':
            return {
                'annotations': sanitize_annotation(form.getlist(value)),
                'or': not form.get(AND)
            }

        if key in {'pubmed', 'authors'}:
            return form.getlist(value)

        node_hashes = form.getlist(value)

        return [
            self.get_node_tuple_by_hash(node_hash)
            for node_hash in node_hashes
        ]

    def query_form_to_dict(self, form):
        """Converts a request.form multidict to the query JSON format.

        :param pybel_web.manager.WebManager self:
        :param werkzeug.datastructures.ImmutableMultiDict form:
        :return: json representation of the query
        :rtype: dict
        """
        query_dict = {}

        pairs = [
            ('pubmed', "pubmed_selection[]"),
            ('authors', 'author_selection[]'),
            ('annotation', 'annotation_selection[]'),
            (form["seed_method"], "node_selection[]")
        ]

        query_dict['seeding'] = [
            {
                "type": seed_method,
                'data': self.convert_seed_value(seed_method, form, seed_data_argument)
            }
            for seed_method, seed_data_argument in pairs
            if form.getlist(seed_data_argument)
        ]

        query_dict["pipeline"] = [
            {
                'function': to_snake_case(function_name)
            }
            for function_name in form.getlist("pipeline[]")
            if function_name
        ]

        network_ids = form.getlist("network_ids[]", type=int)
        if network_ids:
            query_dict["network_ids"] = network_ids

        return query_dict

    def _safe_get_query_helper(self, user, query_id):
        """Checks if the user has the rights to run the given query

        :param models.User user: A user object
        :param models.Query query: A query object
        :rtype: Optional[Query]
        """
        query = self.get_query_or_404(query_id)

        log.debug('checking if user [%s] has rights to query [id=%s]', user, query_id)

        if user.is_authenticated and user.is_admin:
            log.debug('[%s] is admin and can access query [id=%d]', user, query_id)
            return query  # admins are never missing the rights to a query

        permissive_network_ids = self.get_network_ids_with_permission(user=user)

        if not any(network.id not in permissive_network_ids for network in query.assembly.networks):
            return query

    def safe_get_query(self, user, query_id):
        """Get a query by its database identifier.

        - Raises an HTTPException with 404 if the query does not exist.
        - Raises an HTTPException with 403 if the user does not have the appropriate permissions for all networks in
          the query's assembly.

        :param User user:
        :param int query_id: The database identifier for a query
        :rtype: Query
        :raises: werkzeug.exceptions.HTTPException
        """
        query = self._safe_get_query_helper(user, query_id)

        if query is None:
            abort(403, 'Insufficient rights to run query {}'.format(query_id))

        return query

    @lru_cache(maxsize=256)
    def safe_get_graph_from_query_id(self, user, query_id):
        """Process the GET request returning the filtered network.

        :param User user:
        :param int query_id: The database query identifier
        :rtype: Optional[pybel.BELGraph]
        :raises: werkzeug.exceptions.HTTPException
        """
        log.debug('getting query [id=%d] from database', query_id)
        t = time.time()
        query = self.safe_get_query(user=user, query_id=query_id)
        log.debug('got query [id=%d] in %.2f seconds', query_id, time.time() - t)

        log.debug('running query [id=%d]', query_id)
        t = time.time()
        try:
            result = query.run(self)
            log.debug('ran query [id=%d] in %.2f seconds', query_id, time.time() - t)
        except networkx.exception.NetworkXError as e:
            log.warning('query [id=%d] failed after %.2f seconds', query_id, time.time() - t)
            raise e

        return result
