# -*- coding: utf-8 -*-

"""Extensions to the PyBEL manager to support PyBEL-Web."""

import datetime
import logging

from flask import abort
from flask_security import SQLAlchemyUserDatastore

from pybel.manager.cache_manager import _Manager
from pybel.manager.models import Annotation, Citation, Evidence, Namespace
from .models import Experiment, Omic, Project, Query, Role, User

__all__ = [
    'WebManager',
]

log = logging.getLogger(__name__)


class WebManager(_Manager):
    """Extensions to the PyBEL manager and :class:`SQLAlchemyUserDataStore` to support PyBEL-Web."""

    def __init__(self, engine, session):
        super(_Manager, self).__init__(engine=engine, session=session)

        self.user_datastore = SQLAlchemyUserDatastore(self, User, Role)

    def iter_public_networks(self):
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
        yield from self.iter_public_networks
        yield from user.get_owned_networks()
        yield from user.get_shared_networks()
        yield from user.get_project_networks()

        if user.is_scai:
            role = self.user_datastore.find_or_create_role(name='scai')
            for user in role.users:
                yield from user.get_owned_networks()

    def networks_with_permission_iter_helper(self, user):
        """Gets an iterator over all the networks from all the sources

        :param models.User user: A user
        :rtype: iter[Network]
        """
        if not user.is_authenticated:
            log.debug('getting only public networks for anonymous user')
            yield from self.iter_public_networks()

        elif user.is_admin:
            log.debug('getting all recent networks for admin')
            yield from self.list_recent_networks()

        else:
            log.debug('getting all networks for user [%s]', self)
            yield from self._iterate_networks_for_user(user)

    def get_network_ids_with_permission_helper(self, user):
        """Gets the set of networks ids tagged as public or uploaded by the user

        :param User user: A user
        :return: A list of all networks tagged as public or uploaded by the user
        :rtype: set[int]
        """
        networks = self.networks_with_permission_iter_helper(user)
        return {network.id for network in networks}

    def user_missing_query_rights_abstract(self, user, query):
        """Checks if the user does not have the rights to run the given query

        :param models.User user: A user object
        :param models.Query query: A query object
        :rtype: bool
        """
        log.debug('checking if user [%s] has rights to query [id=%s]', user, query.id)

        if user.is_authenticated and user.is_admin:
            log.debug('[%s] is admin and can access query [id=%d]', user, query.id)
            return False  # admins are never missing the rights to a query

        permissive_network_ids = self.get_network_ids_with_permission_helper(user=user)

        return any(
            network.id not in permissive_network_ids
            for network in query.assembly.networks
        )

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

    def get_experiment_or_404(self, experiment_id):
        experiment = self.get_experiment_by_id(experiment_id)

        if experiment is None:
            abort(404, 'Experiment {} does not exist'.format(experiment_id))

        return experiment

    def safe_get_experiment(self, experiment_id, user):
        """Get an experiment by its databse identifier or 404 if it doesn't exist.

        :param int experiment_id:
        :param User user:
        :rtype: Experiment
        :raises: werkzeug.exceptions.HTTPException
        """
        experiment = self.get_experiment_or_404(experiment_id)

        if not user.has_experiment_rights(experiment):
            abort(403, 'You do not have rights to drop this experiment')

        return experiment

    def safe_get_experiments(self, experiment_ids, user):
        """Get a list of experiments by their database identifiers or abort 404 if any don't exist.

        :param list[int] experiment_ids:
        :param User user:
        :rtype: list[Experiment]
        """
        return [
            self.safe_get_experiment(experiment_id, user)
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

    def _safe_get_network(self, network_id, user):
        """Abort if the current user is not the owner of the network.

        :param int network_id: The identifier of the network
        :param User user:
        :rtype: Network
        :raises: werkzeug.exceptions.HTTPException
        """
        network = self.get_network_or_404(network_id)

        if network.report and network.report.public:
            return network

        # FIXME what about networks in a project?

        if not user.owns_network(network):
            abort(403, 'User {} does not have permission to access Network {}'.format(user, network))

        return network

    def _safe_get_project(self, project_id, user):
        """Get a project by identifier, aborts 404 if doesn't exist and aborts 403 if current user does not have rights.

        :param int project_id: The identifier of the project
        :param User user:
        :rtype: Project
        :raises: werkzeug.exceptions.HTTPException
        """
        project = self.get_project_or_404(project_id)

        if not user.has_project_rights(project):
            abort(403, 'User {} does not have permission to access Project {}'.format(user, project))

        return project
