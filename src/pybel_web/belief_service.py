# -*- coding: utf-8 -*-

"""This module contains integrations developed for BELIEF"""

from flask import (
    Blueprint,
    request,
)

from pybel import from_url
from pybel.struct import union
from .send_utils import serve_network
from .utils import manager

belief_blueprint = Blueprint('belief', __name__)


@belief_blueprint.route('/belief/merge', methods=["POST"])
def semantic_merge():
    """Performs a semantic merge on BEL documents

    This endpoint receives a list of URLs, parses them synchronously, performs a semantic merge, then serializes
    a BEL document as the response.
    ---
    parameters:
      - name: urls
        in: query
        description: A list of URLs to BEL documents
        required: true
        schema:
          type: array
          items:
            type: string
    responses:
      200:
        description: A merged BEL document
    """
    request_json = request.get_json()
    urls = request_json['urls']

    graphs = [
        from_url(url, manager=manager)
        for url in urls
    ]

    super_graph = union(graphs)

    return serve_network(super_graph, serve_format='bel')
