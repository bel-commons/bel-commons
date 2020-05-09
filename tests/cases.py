# -*- coding: utf-8 -*-

"""Test cases for BEL Commons."""
import logging
import tempfile
import unittest

from bel_commons.manager import WebManager
from pybel.testing.cases import TemporaryCacheMixin

__all__ = [
    'TemporaryCacheMethodMixin',
]

logger = logging.getLogger(__name__)


class TemporaryCacheMethodMixin(TemporaryCacheMixin):
    """Allows for testing with a consistent connection and creation of a manager class wrapping that connection."""

    def setUp(self):
        """Set up the class with the given manager and allows an optional populate hook to be overridden."""
        super().setUp()

        self.manager = WebManager(connection=self.connection)
        self.manager.create_all()
        self.populate()

    def tearDown(self):
        """Close the connection in the manager and deletes the temporary database."""
        self.manager.session.close()
        super().tearDown()

    def populate(self):
        """A stub that can be overridden to populate the manager."""

    def add_all(self, l):
        self.manager.session.add_all(l)

    def commit(self):
        self.manager.session.commit()

    def add_all_and_commit(self, l):
        """Add a list of models to the session and commit them.

        :param l: A list of models
        """
        self.add_all(l)
        self.commit()


class TemporaryCacheMixin(unittest.TestCase):
    """A test case that has a connection and a manager that is created for each test function."""

    def setUp(self):
        """Set up the test function with a connection and manager."""
        self.fd, self.path = tempfile.mkstemp()
        self.connection = 'sqlite:///' + self.path
        logger.info('Test generated connection string %s', self.connection)

        self.manager = WebManager(connection=self.connection, autoflush=True)
        self.manager.create_all()

    def tearDown(self):
        """Tear down the test function by closing the session and removing the database."""
        self.manager.session.close()
