# -*- coding: utf-8 -*-

"""Functions for checking the safety of the content."""

import logging
from functools import lru_cache

from flask_login import current_user
from werkzeug.exceptions import abort

from ..proxies import manager

__all__ = [
    'user_missing_query_rights',
    'safe_get_network',
    'safe_get_project',
    'safe_get_query',
]

log = logging.getLogger(__name__)


def safe_get_network(network_id):
    """Abort if the current user is not the owner of the network.

    :param int network_id: The identifier of the network
    :rtype: Network
    :raises: HTTPException
    """
    return manager._safe_get_network(network_id, current_user)


def safe_get_project(project_id):
    """Get a project by identifier, aborts 404 if doesn't exist and aborts 403 if current user does not have rights.

    :param int project_id: The identifier of the project
    :rtype: Project
    :raises: HTTPException
    """
    return manager._safe_get_project(project_id, current_user)


@lru_cache(maxsize=256)
def user_missing_query_rights(user, query):
    """Check if the user does not have the rights to run the given query.

    :param models.User user: A user object
    :param models.Query query: A query object
    :rtype: bool
    """
    return manager.user_missing_query_rights_abstract(user=user, query=query)


def safe_get_query(query_id):
    """Get a query by its database identifier.

    Raises an HTTPException with 404 if the query does not exist or raises an HTTPException with 403 if the user does
    not have the appropriate permissions for all networks in the query's assembly.

    :param int query_id: The database identifier for a query
    :rtype: Query
    :raises: werkzeug.exceptions.HTTPException
    """
    query = manager.get_query_or_404(query_id)

    if user_missing_query_rights(current_user, query):
        abort(403, 'Insufficient rights to run query {}'.format(query_id))

    return query
