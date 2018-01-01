# -*- coding: utf-8 -*-

import logging
import os
import tempfile
import unittest

from pybel import Manager
from pybel.examples import sialic_acid_graph
from pybel.manager.models import Edge
from pybel_web.models import User
from pybel_web.utils import get_or_create_vote

log = logging.getLogger(__name__)


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
