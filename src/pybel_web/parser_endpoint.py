# -*- coding: utf-8 -*-

import logging
import time
from getpass import getuser

import flask
from flask import jsonify, request

from pybel import BELGraph
from pybel.parser import BelParser
from .send_utils import serve_network

__all__ = [
    'build_parser_service',
]

log = logging.getLogger(__name__)

METADATA_TIME_ADDED = 'added'
METADATA_IP = 'ip'
METADATA_HOST = 'host'
METADATA_USER = 'user'


def build_parser_service(app, conversion_function=None):
    """Builds parser app for sending and receiving BEL statements
    
    :param flask.Flask app: A Flask app
    :param conversion_function: An optional function to convert the output of the parser before serializing to JSON
    :type conversion_function: types.FunctionType or types.LambdaType
    """
    graph = BELGraph(
        name='PyBEL Parser Results',
        version='1.0.0',
        authors=getuser(),
        description='This graph was produced using the PyBEL Parser API. It was instantiated at {}'.format(
            time.asctime())
    )

    parser = BelParser(graph)

    @app.route('/api/parser/status')
    def get_status():
        """Returns the status of the parser"""
        result = {
            'status': 'ok',
            'graph_number_nodes': graph.number_of_nodes(),
            'graph_number_edges': graph.number_of_edges(),

        }
        result.update(graph.document)
        return jsonify(result)

    @app.route('/api/parser/parse/<statement>', methods=['GET', 'POST'])
    def parse_bel(statement):
        """Parses a URL-encoded BEL statement"""
        parser.control_parser.clear()
        parser.control_parser.annotations.update({
            METADATA_TIME_ADDED: str(time.asctime()),
            METADATA_IP: request.remote_addr,
            METADATA_HOST: request.host,
            METADATA_USER: request.remote_user
        })
        parser.control_parser.annotations.update(request.args)

        try:
            res = parser.statement.parseString(statement)
            res_dict = res.asDict()

            if conversion_function:
                res_dict = conversion_function(res_dict)

            return jsonify(**res_dict)
        except Exception as e:
            return jsonify({
                'status': 'bad',
                'exception': str(e)
            })

    @app.route('/api/parser/download/')
    @app.route('/api/parser/download/<serve_format>')
    def download(serve_format=None):
        """Downloads the internal graph"""
        return serve_network(graph, serve_format)

    @app.route('/api/parser/clear')
    def clear():
        """Clears the content of the internal graph"""
        parser.clear()
        return jsonify({'status': 'ok'})

    log.info('Added parser endpoint to %s', app)
