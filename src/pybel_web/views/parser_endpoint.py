# -*- coding: utf-8 -*-

import logging
import time
from uuid import uuid4

from flask import Flask, jsonify, request

from pybel import BELGraph
from pybel.parser import BELParser

__all__ = [
    'build_parser_service',
]

log = logging.getLogger(__name__)

METADATA_TIME_ADDED = 'added'
METADATA_IP = 'ip'
METADATA_HOST = 'host'
METADATA_USER = 'user'


def build_parser_service(app: Flask):
    """Add the parser app for sending and receiving BEL statements."""
    graph = BELGraph()
    parser = BELParser(graph, citation_clearing=False)

    @app.route('/api/parser/status')
    def get_status():
        """Return the status of the parser.

        ---
        tags:
            - parser
        """
        result = {
            'status': 'ok',
            'graph_number_nodes': graph.number_of_nodes(),
            'graph_number_edges': graph.number_of_edges(),
        }
        result.update(graph.document)
        return jsonify(result)

    @app.route('/api/parser/parse/<statement>', methods=['GET', 'POST'])
    def parse_bel(statement):
        """Parses a URL-encoded BEL statement.

        ---
        tags:
            - parser
        parameters:
          - name: statement
            in: query
            description: A BEL statement
            required: true
            type: string
        """
        parser.control_parser.clear()

        parser.control_parser.evidence = str(uuid4())
        parser.control_parser.citation = dict(type=str(uuid4()), reference=str(uuid4()))

        parser.control_parser.annotations.update({
            METADATA_TIME_ADDED: str(time.asctime()),
            METADATA_IP: request.remote_addr,
            METADATA_HOST: request.host,
            METADATA_USER: request.remote_user
        })
        parser.control_parser.annotations.update(request.args)

        try:
            res = parser.statement.parseString(statement)
            return jsonify(**res.asDict())

        except Exception as e:
            return jsonify({
                'status': 'bad',
                'exception': str(e),
                'input': statement,
            })
