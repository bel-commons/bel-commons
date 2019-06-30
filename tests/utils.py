# -*- coding: utf-8 -*-

"""Utilities for testing BEL Commons."""

from typing import Optional

from pybel.constants import INCREASES, PROTEIN
from pybel.manager import Edge, Network, Node
from pybel.testing.utils import n
from pybel_web.models import Report


def make_network(name: str = None) -> Network:
    """Make a network with a dummy name and version."""
    return Network(
        name=(str(name) if name is not None else n()),
        version=n(),
    )


def upgrade_network(network: Network) -> Network:
    """Make a new network with the same name and a new version."""
    return Network(
        name=network.name,
        version=n(),
    )


def make_report(network: Network) -> Report:
    """Make a report for the network."""
    return Report(network=network)


def make_node() -> Node:
    """Make a dummy node."""
    return Node(type=PROTEIN, bel=f'p(HGNC:{n()})')


def make_edge(source: Optional[Node] = None, target: Optional[Node] = None) -> Edge:
    """Make a dummy edge."""
    if source is None:
        source = make_node()
    if target is None:
        target = make_node()
    return Edge(
        source=source,
        target=target,
        relation=INCREASES,
        bel=f'{source.bel} increases {target.bel}',
    )
