# -*- coding: utf-8 -*-

"""Utilities for testing BEL Commons."""

import hashlib
from typing import Optional

from bel_commons.models import Report
from pybel.constants import INCREASES, PROTEIN
from pybel.manager import Edge, Network, Node
from pybel.testing.utils import n


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
    bel = f'p(HGNC:{n()})'
    return Node(type=PROTEIN, bel=bel, md5=hashlib.md5(bel.encode('utf-8')).hexdigest(), data={})


def make_edge(source: Optional[Node] = None, target: Optional[Node] = None) -> Edge:
    """Make a dummy edge."""
    if source is None:
        source = make_node()
    if target is None:
        target = make_node()

    bel = f'{source.bel} increases {target.bel}'
    return Edge(
        source=source,
        target=target,
        relation=INCREASES,
        bel=bel,
        data={},
        md5=hashlib.md5(bel.encode('utf-8')).hexdigest(),
    )
