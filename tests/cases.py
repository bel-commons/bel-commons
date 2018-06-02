# -*- coding: utf-8 -*-

"""Test cases for PyBEL Web."""

from bio2bel.testing import TemporaryConnectionMethodMixin

from pybel_web.manager import WebManager

__all__ = [
    'TemporaryCacheMethodMixin',
]


class TemporaryCacheMethodMixin(TemporaryConnectionMethodMixin):
    """Allows for testing with a consistent connection and creation of a manager class wrapping that connection."""

    def setUp(self):
        """Set up the class with the given manager and allows an optional populate hook to be overridden."""
        super().setUp()

        self.manager = WebManager.from_connection(self.connection)
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
