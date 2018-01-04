# -*- coding: utf-8 -*-

import logging
import os
import tempfile
import unittest

from pybel import Manager
from pybel.examples import sialic_acid_graph
from pybel.manager.models import Edge
from pybel_web.models import Query, User
from pybel_web.utils import get_or_create_vote

log = logging.getLogger(__name__)


class TemporaryCacheInstanceMixin(unittest.TestCase):
    def setUp(self):
        """Creates a temporary file to use as a persistent database throughout tests in this class. Subclasses of
        :class:`TemporaryCacheClsMixin` can extend :func:`TemporaryCacheClsMixin.setUpClass` to populate the database
        """
        self.fd, self.path = tempfile.mkstemp()
        self.connection = 'sqlite:///' + self.path
        log.info('test database at %s', self.connection)
        self.manager = Manager(connection=self.connection)
        self.manager.create_all()

    def tearDown(self):
        """Closes the connection to the database and removes the files created for it"""
        self.manager.session.close()
        os.close(self.fd)
        os.remove(self.path)

class TemporaryCacheClsMixin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Creates a temporary file to use as a persistent database throughout tests in this class. Subclasses of
        :class:`TemporaryCacheClsMixin` can extend :func:`TemporaryCacheClsMixin.setUpClass` to populate the database
        """
        cls.fd, cls.path = tempfile.mkstemp()
        cls.connection = 'sqlite:///' + cls.path
        log.info('test database at %s', cls.connection)
        cls.manager = Manager(connection=cls.connection)
        cls.manager.create_all()

    @classmethod
    def tearDownClass(cls):
        """Closes the connection to the database and removes the files created for it"""
        cls.manager.session.close()
        os.close(cls.fd)
        os.remove(cls.path)


class TestDrop(TemporaryCacheClsMixin):
    def test_drop_votes(self):  # TODO use mocks?
        network = self.manager.insert_graph(sialic_acid_graph)
        edges = list(network.edges.order_by(Edge.bel))
        edge = edges[0]
        user = User(email='test@example.com')
        vote = get_or_create_vote(self.manager, edge, user, agreed=True)
        self.assertIsNone(vote.changed)
        self.assertTrue(vote.agreed)

        vote = get_or_create_vote(self.manager, edge, user, agreed=False)
        self.assertIsNotNone(vote.changed)
        self.assertFalse(vote.agreed)


class TestDropInstance(TemporaryCacheInstanceMixin):
    def test_drop_query_cascade_to_parent(self):
        """Tests that dropping a query gets passed to its parent, and doesn't muck up anything else"""

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
