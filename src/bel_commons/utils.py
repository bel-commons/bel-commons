# -*- coding: utf-8 -*-

"""Utilities for BEL Commons."""

import logging
import socket
import time
from getpass import getuser
from typing import Dict, List, Optional, TypeVar

import flask_mail
from flask import Blueprint, Flask, abort, request
from flask.blueprints import BlueprintSetupState
from flask_security import login_required

from pybel import BELGraph
from pybel.struct.summary import get_annotation_values_by_annotation, get_annotations, get_pubmed_identifiers
from .constants import BEL_COMMONS_STARTUP_NOTIFY, MAIL_DEFAULT_SENDER, SERVER_NAME
from .version import get_version

__all__ = [
    'calculate_overlap_info',
    'get_tree_annotations',
    'add_edge_filter',
    'return_or_404',
    'send_startup_mail',
    'SecurityConfigurableBlueprint',
]

logger = logging.getLogger(__name__)


def calculate_overlap_info(g1: BELGraph, g2: BELGraph):
    """Calculate a summary over the overlaps between two graphs."""
    g1_nodes, g2_nodes = set(g1), set(g2)
    overlap_nodes = g1 & g2

    g1_edges, g2_edges = set(g1.edges()), set(g2.edges())
    overlap_edges = g1_edges & g2_edges

    g1_citations, g2_citations = get_pubmed_identifiers(g1), get_pubmed_identifiers(g2)
    overlap_citations = g1_citations & g2_citations

    g1_annotations, g2_annotations = get_annotations(g1), get_annotations(g2)
    overlap_annotations = g1_annotations & g2_annotations

    return {
        'nodes': (len(g1_nodes), len(overlap_nodes), len(g2_nodes)),
        'edges': (len(g1_edges), len(overlap_edges), len(g2_edges)),
        'citations': (len(g1_citations), len(overlap_citations), len(g2_citations)),
        'annotations': (len(g1_annotations), len(overlap_annotations), len(g2_annotations)),
    }


def get_tree_annotations(graph: BELGraph) -> List[Dict]:
    """Build a tree structure with annotation for a given graph.

    :return: The JSON structure necessary for building the tree box
    """
    return [
        {
            'text': annotation,
            'children': [
                {
                    'text': value,
                }
                for value in sorted(values)
            ],
        }
        for annotation, values in sorted(get_annotation_values_by_annotation(graph).items())
    ]


def add_edge_filter(edge_query, limit_default=None, offset_default=None):
    """Add a limit and/or offset to an edge query."""
    limit = request.args.get('limit', type=int, default=limit_default)
    offset = request.args.get('offset', type=int, default=offset_default)

    if limit is not None:
        edge_query = edge_query.limit(limit)

    if offset is not None:
        edge_query = edge_query.offset(offset)

    return edge_query


X = TypeVar('X')


def return_or_404(x: Optional[X], message: str) -> X:
    """Return the given argument or abort with the given message."""
    if x is None:
        abort(404, message)
    return x


def send_startup_mail(app: Flask) -> None:
    """Send an email upon the app's startup."""
    from bel_commons.ext import mail

    mail_default_sender = app.config.get(MAIL_DEFAULT_SENDER)
    notify = app.config.get(BEL_COMMONS_STARTUP_NOTIFY)
    if notify:
        logger.info(f'sending startup notification to {notify}')
        send_message(
            app=app,
            mail=mail,
            subject="BEL Commons Startup",
            body="BEL Commons v{} was started on {} by {} at {}.\n\nDeployed to: {}".format(
                get_version(),
                socket.gethostname(),
                getuser(),
                time.asctime(),
                app.config.get(SERVER_NAME),
            ),
            sender=mail_default_sender,
            recipients=[notify],
        )
        logger.info(f'notified {notify}')


def send_message(app: Flask, mail: flask_mail.Mail, *args, **kwargs) -> None:
    """Send a message."""
    with app.app_context():
        mail.send_message(*args, **kwargs)


class SecurityConfigurableBlueprint(Blueprint):
    """Makes it possible to lock it all down, if you have to."""

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        """Wrap :meth:`Flask.add_url_rule` to enable automatic application of :func:`flask_security.login_required`."""
        if endpoint:
            assert "." not in endpoint, "Blueprint endpoints should not contain dots"
        if view_func and hasattr(view_func, "__name__"):
            assert "." not in view_func.__name__, "Blueprint view function name should not contain dots"

        def _add_url_rule(s: BlueprintSetupState) -> None:
            if s.app.config['LOCKDOWN']:
                s.add_url_rule(rule, endpoint, login_required(view_func), **options)
            else:
                s.add_url_rule(rule, endpoint, view_func, **options)

        self.record(_add_url_rule)
