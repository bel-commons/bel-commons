# -*- coding: utf-8 -*-

import logging
import os
import tempfile
import unittest

from pybel import Manager

log = logging.getLogger(__name__)

dir_path = os.path.dirname(os.path.realpath(__file__))

test_bel_pickle_path = os.path.join(dir_path, 'test_bel.gpickle')

TEST_CONNECTION = os.environ.get('PYBEL_TEST_CONNECTION')


class TemporaryCacheInstanceMixin(unittest.TestCase):
    def setUp(self):
        """Creates a temporary file to use as a persistent database throughout tests in this class. Subclasses of
        :class:`TemporaryCacheClsMixin` can extend :func:`TemporaryCacheClsMixin.setUpClass` to populate the database
        """
        if TEST_CONNECTION:
            self.connection = TEST_CONNECTION
        else:
            self.fd, self.path = tempfile.mkstemp()
            self.connection = 'sqlite:///' + self.path
            log.info('Test generated connection string %s', self.connection)

        self.manager = Manager(connection=self.connection)
        self.manager.create_all()

    def tearDown(self):
        self.manager.session.close()

        if not TEST_CONNECTION:
            os.close(self.fd)
            os.remove(self.path)
        else:
            self.manager.drop_all()


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
