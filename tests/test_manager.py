# -*- coding: utf-8 -*-

"""Tests for the manager."""

import json
import logging
import time

from werkzeug.exceptions import HTTPException

from bel_commons.manager import iter_recent_public_networks
from bel_commons.models import Assembly, EdgeComment, EdgeVote, Query, User
from pybel.constants import INCREASES, PROTEIN, RELATION
from pybel.manager.models import Edge, Node
from pybel.testing.utils import n
from tests.cases import TemporaryCacheMethodMixin
from tests.utils import make_edge, make_network, make_report, upgrade_network

log = logging.getLogger(__name__)


def make_simple_edge(n1: Node, n2: Node, relation: str) -> Edge:
    """Make a simple edge between two nodes."""
    e1_data = {
        RELATION: relation,
    }
    bel = f'{n1.as_bel()} {relation} {n2.as_bel()}'
    return Edge(source=n1, target=n2, relation=relation, bel=bel, data=json.dumps(e1_data))


class TestManager(TemporaryCacheMethodMixin):
    """Test the BEL Commons WebManager class."""

    def test_manager_iter_recent_public_networks(self):
        """Test iteration of the latest public networks."""
        n1, n2, n3, n4 = networks = [make_network('Network {}'.format(i)) for i in range(1, 5)]

        self.add_all(networks)

        # skip making a report for the last one
        r1, r2, r3 = reports = [make_report(network) for network in (n1, n2, n3)]
        r1.public = True
        r2.public = True
        r3.public = False

        self.add_all_and_commit(reports)

        self.assertEqual(4, self.manager.count_networks())
        self.assertEqual(3, self.manager.count_reports())

        public_networks = list(iter_recent_public_networks(self.manager))
        self.assertIn(n1, public_networks)
        self.assertIn(n2, public_networks)
        self.assertEqual(2, len(public_networks))

        time.sleep(1)

        # add some updates

        n1v2 = upgrade_network(n1)
        r1v2 = make_report(n1v2)
        self.add_all_and_commit([n1v2, r1v2])

        self.assertEqual(5, self.manager.count_networks())
        self.assertEqual(4, self.manager.count_reports())

        public_networks = list(iter_recent_public_networks(self.manager))
        self.assertNotIn(n1, public_networks)
        self.assertIn(n1v2, public_networks)
        self.assertIn(n2, public_networks)
        self.assertEqual(2, len(public_networks))

    def test_user_iter_owned_networks(self):
        """Test getting networks owned by a given user."""

    def test_user_iter_shared_networks(self):
        """Test getting networks shared with a given user."""

    def test_user_iter_project_networks(self):
        """Test getting networks accessible to a given user through a project."""

    def test_safe_get_network(self):
        """Test getting a network as a given user."""
        u1 = User()
        u2 = User()
        self.add_all_and_commit([u1, u2])

        with self.assertRaises(HTTPException):
            self.manager.authenticated_get_network_by_id_or_404(user=u1, network_id=0)

        # TODO test conditions for admin, for report, and for actual permission

        n1, n2 = (make_network() for _ in range(2))
        r1 = make_report(n1)
        r1.user = u1
        r2 = make_report(n2)
        r2.user = u2
        self.add_all_and_commit([n1, r1, n2, r2])

        self.assertEqual(2, self.manager.count_users())
        self.assertEqual(2, self.manager.count_networks())
        self.assertEqual(2, self.manager.count_reports())

        self.manager.owner_get_network_by_id_or_404(user=u1, network_id=n1.id)

        with self.assertRaises(HTTPException):
            self.manager.owner_get_network_by_id_or_404(user=u2, network_id=n1.id)

    def test_create_votes(self):
        """Test creating votes for edges."""
        edge = make_edge()
        user = User(email='test@example.com')
        self.manager.session.add_all([edge, user])
        self.manager.session.commit()

        vote = self.manager.get_or_create_vote(edge, user, agreed=True)
        self.assertIsNotNone(vote.changed)
        self.assertTrue(vote.agreed)

        vote = self.manager.get_or_create_vote(edge, user, agreed=False)
        self.assertIsNotNone(vote.changed)
        self.assertFalse(vote.agreed)

    def test_drop_edge_cascade_to_vote(self):
        """Test the drop cascade from edge to votes."""
        n1 = Node(type=PROTEIN, bel='p(HGNC:A)')
        n2 = Node(type=PROTEIN, bel='p(HGNC:B)')
        n3 = Node(type=PROTEIN, bel='p(HGNC:C)')
        e1 = make_simple_edge(n1, n2, INCREASES)
        e2 = make_simple_edge(n2, n3, INCREASES)
        u1 = User()
        u2 = User()
        v1 = EdgeVote(user=u1, edge=e1)
        v2 = EdgeVote(user=u2, edge=e1)
        v3 = EdgeVote(user=u1, edge=e2)

        self.manager.session.add_all([n1, n2, n3, e1, e2, u1, v1, v2, v3])
        self.manager.session.commit()

        self.assertEqual(3, self.manager.session.query(Node).count())
        self.assertEqual(2, self.manager.session.query(Edge).count())
        self.assertEqual(2, self.manager.session.query(User).count())
        self.assertEqual(3, self.manager.session.query(EdgeVote).count())

        self.manager.session.delete(e1)
        self.manager.session.commit()

        self.assertEqual(1, self.manager.session.query(Edge).count())
        self.assertEqual(2, self.manager.session.query(User).count())
        self.assertEqual(1, self.manager.session.query(EdgeVote).count())

    def test_drop_edge_cascade_to_comment(self):
        """Test that dropping an edge cascades to all comments."""
        n1 = Node(type=PROTEIN, bel='p(HGNC:A)')
        n2 = Node(type=PROTEIN, bel='p(HGNC:B)')
        n3 = Node(type=PROTEIN, bel='p(HGNC:C)')
        e1 = make_simple_edge(n1, n2, INCREASES)
        e2 = make_simple_edge(n2, n3, INCREASES)
        u1 = User()
        u2 = User()
        v1 = EdgeComment(user=u1, edge=e1, comment=n())
        v2 = EdgeComment(user=u2, edge=e1, comment=n())
        v3 = EdgeComment(user=u1, edge=e1, comment=n())
        v4 = EdgeComment(user=u1, edge=e2, comment=n())

        self.manager.session.add_all([n1, n2, n3, e1, e2, u1, v1, v2, v3, v4])
        self.manager.session.commit()

        self.assertEqual(3, self.manager.session.query(Node).count())
        self.assertEqual(2, self.manager.session.query(Edge).count())
        self.assertEqual(2, self.manager.session.query(User).count())
        self.assertEqual(4, self.manager.session.query(EdgeComment).count())

        self.manager.session.delete(e1)
        self.manager.session.commit()

        self.assertEqual(1, self.manager.session.query(Edge).count())
        self.assertEqual(2, self.manager.session.query(User).count())
        self.assertEqual(1, self.manager.session.query(EdgeComment).count())

    def test_drop_query_cascade_to_parent(self):
        """Test that dropping a query gets passed to its parent, and doesn't muck up anything else."""
        q1 = Query()
        self.manager.session.add(q1)
        self.manager.session.commit()

        self.assertEqual(1, self.manager.session.query(Query).count(), msg='First query added unsuccessfully')

        q2 = Query(parent=q1)
        self.manager.session.add(q2)
        self.manager.session.commit()

        self.assertEqual(2, self.manager.session.query(Query).count(), msg='Second query added unsuccessfully')

        q3 = Query(parent=q2)
        self.manager.session.add(q3)
        self.manager.session.commit()

        self.assertEqual(3, self.manager.session.query(Query).count(), msg='Third query added unsuccessfully')

        q4 = Query()
        self.manager.session.add(q4)
        self.manager.session.commit()

        self.assertIsNotNone(self.manager.session.query(Query).get(q1.id))
        self.assertIsNotNone(self.manager.session.query(Query).get(q2.id))
        self.assertIsNotNone(self.manager.session.query(Query).get(q3.id))
        self.assertIsNotNone(self.manager.session.query(Query).get(q4.id))

        self.manager.session.delete(q1)
        self.manager.session.commit()

        self.assertIsNone(self.manager.session.query(Query).get(q1.id))
        self.assertIsNone(self.manager.session.query(Query).get(q2.id))
        self.assertIsNone(self.manager.session.query(Query).get(q3.id))
        self.assertIsNotNone(self.manager.session.query(Query).get(q4.id))

    def test_drop_all_queries(self):
        """Test dropping all queries."""
        q1 = Query()
        q2 = Query(parent=q1)
        q3 = Query(parent=q1)
        q4 = Query(parent=q3)
        q5 = Query()
        self.manager.session.add_all([q1, q2, q3, q4, q5])
        self.manager.session.commit()

        self.assertEqual(5, self.manager.count_queries())

        self.manager.session.query(Query).delete()
        self.manager.session.commit()

        self.assertEqual(0, self.manager.count_queries())

    def test_drop_assembly_cascade_query(self):
        """Test that dropping an assembly cascades to queries using it."""
        a1 = Assembly()
        a2 = Assembly()
        q1 = Query(assembly=a1)
        q2 = Query(assembly=a2)
        q3 = Query(assembly=a1)

        self.manager.session.add_all([a1, a2, q1, q2, q3])
        self.manager.session.commit()

        self.assertEqual(2, self.manager.count_assemblies())
        self.assertEqual(3, self.manager.count_queries())

        self.manager.session.delete(a1)
        self.manager.session.commit()

        self.assertEqual(1, self.manager.count_assemblies())
        self.assertEqual(1, self.manager.count_queries(), msg='Cascade to queries did not work')
