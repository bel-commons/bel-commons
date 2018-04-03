# -*- coding: utf-8 -*-

from werkzeug.exceptions import abort

from pybel.manager import Network
from ..models import Project, Query
from ..proxies import manager

__all__ = [
    'get_network_or_404',
    'get_query_or_404',
    'get_node_by_hash_or_404',
    'get_edge_by_hash_or_404',
    'get_project_or_404'
]


def get_network_or_404(network_id):
    """Gets a network or aborts 404 if it doesn't exist

    :param int network_id: The identifier of the network
    :rtype: Network
    :raises: HTTPException
    """
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404, 'Network {} does not exist'.format(network_id))

    return network


def get_query_or_404(query_id):
    """Gets a query or returns a HTTPException with 404 message if it does not exist

    :param int query_id: The database identifier for a query
    :rtype: Query
    :raises: werkzeug.exceptions.HTTPException
    """
    query = manager.session.query(Query).get(query_id)

    if query is None:
        abort(404, 'Missing query: {}'.format(query_id))

    return query


def get_node_by_hash_or_404(node_hash):
    """Gets a node's hash or sends a 404 missing message

    :param str node_hash: A PyBEL node hash
    :rtype: pybel.manager.models.Node
    :raises: werkzeug.exceptions.HTTPException
    """
    node = manager.get_node_by_hash(node_hash)

    if node is None:
        abort(404, 'Node not found: {}'.format(node_hash))

    return node


def get_edge_by_hash_or_404(edge_hash):
    """Gets an edge if it exists or sends a 404

    :param str edge_hash: A PyBEL edge hash
    :rtype: Edge
    :raises: werkzeug.exceptions.HTTPException
    """
    edge = manager.get_edge_by_hash(edge_hash)

    if edge is None:
        abort(404, 'Edge not found: {}'.format(edge_hash))

    return edge


def get_project_or_404(project_id):
    """Get a project by id and aborts 404 if doesn't exist

    :param int project_id: The identifier of the project
    :rtype: Project
    :raises: HTTPException
    """
    project = manager.session.query(Project).get(project_id)

    if project is None:
        abort(404, 'Project {} does not exist'.format(project_id))

    return project
