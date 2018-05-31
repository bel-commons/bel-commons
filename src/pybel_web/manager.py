# -*- coding: utf-8 -*-

"""Extensions to the PyBEL manager to support PyBEL-Web."""

import datetime
import logging

from flask_security import SQLAlchemyUserDatastore

from pybel.manager.cache_manager import _Manager
from .models import Role, User

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
        """Gets the set of networks ids tagged as public or uploaded by the current user

        :param User user: A user
        :return: A list of all networks tagged as public or uploaded by the current user
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
