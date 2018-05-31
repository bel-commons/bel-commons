# -*- coding: utf-8 -*-

"""Functions for checking the safety of the content"""

import logging
from functools import lru_cache

from flask_login import current_user
from werkzeug.exceptions import abort

from .get_or_404_with_proxy import get_network_or_404, get_project_or_404, get_query_or_404
from ..proxies import manager

__all__ = [
    'user_missing_query_rights',
    'safe_get_network',
    'safe_get_project',
    'safe_get_query',
]

log = logging.getLogger(__name__)


@lru_cache(maxsize=256)
def user_missing_query_rights(user, query):
    """Checks if the user does not have the rights to run the given query

    :param models.User user: A user object
    :param models.Query query: A query object
    :rtype: bool
    """
    return manager.user_missing_query_rights_abstract(user=user, query=query)


def user_has_project_rights(user, project):
    """Returns if the given user has rights to the given project

    :type user: User
    :type project: Project
    :rtype: bool
    """
    return user.is_authenticated and (user.is_admin or project.has_user(current_user))


def safe_get_network(network_id):
    """Aborts if the current user is not the owner of the network

    :param int network_id: The identifier of the network
    :rtype: Network
    :raises: HTTPException
    """
    network = get_network_or_404(network_id)

    if network.report and network.report.public:
        return network

    # FIXME what about networks in a project?

    if not current_user.owns_network(network):
        abort(403, 'User {} does not have permission to access Network {}'.format(current_user, network))

    return network


def safe_get_project(project_id):
    """Gets a project by identifier, aborts 404 if doesn't exist and aborts 403 if current user does not have rights

    :param int project_id: The identifier of the project
    :rtype: Project
    :raises: HTTPException
    """
    project = get_project_or_404(project_id)

    if not user_has_project_rights(current_user, project):
        abort(403, 'User {} does not have permission to access Project {}'.format(current_user, project))

    return project


def safe_get_query(query_id):
    """Gets a query by ite database identifier. Raises an HTTPException with 404 if the query does not exist or
    raises an HTTPException with 403 if the user does not have the appropriate permissions for all networks in the
    query's assembly

    :param int query_id: The database identifier for a query
    :rtype: Query
    :raises: werkzeug.exceptions.HTTPException
    """
    query = get_query_or_404(query_id)

    if user_missing_query_rights(current_user, query):
        abort(403, 'Insufficient rights to run query {}'.format(query_id))

    return query
