from pybel.constants import PROTEIN, INCREASES
from pybel.manager import Network, Node, Edge
from pybel.testing.utils import n
from pybel_web.models import Report, User


def make_network(name: str = None):
    return Network(
        name=(str(name) if name is not None else n()),
        version=n(),
    )


def upgrade_network(network: Network):
    return Network(
        name=network.name,
        version=n(),
    )


def make_report(network: Network) -> Report:
    return Report(network=network)


def make_node() -> Node:
    u = n()
    return Node(type=PROTEIN, bel='p(HGNC:{})'.format(u))


def make_edge(n1=None, n2=None) -> Edge:
    if n1 is None:
        n1 = make_node()
    if n2 is None:
        n2 = make_node()
    return Edge(source=n1, target=n2, relation=INCREASES, bel='{} increases {}'.format(n1.bel, n2.bel))


class MockAdminUser(User):

    @property
    def is_authenticated(self):
        return False

    @property
    def is_admin(self):
        return True