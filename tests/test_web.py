# -*- coding: utf-8 -*-

"""
Reference for testing Flask

- Flask Documentation http://flask.pocoo.org/docs/0.12/testing/
- Flask Cookbook: http://flask.pocoo.org/docs/0.12/tutorial/testing/
"""

import json
import logging
import os
import tempfile
import unittest

from pybel.constants import PYBEL_CONNECTION
from pybel_web.application import FlaskPybel, create_application
from pybel_web.database_service import api_blueprint
from pybel_web.main_service import build_main_service
from pybel_web.upload_service import upload_blueprint
from tests.constants import test_bel_pickle_path

log = logging.getLogger(__name__)
log.setLevel(10)

TEST_USER_USERNAME = 'test@example.com'
TEST_USER_PASSWORD = 'password'
TEST_SECRET_KEY = 'pybel_web_tests'


class WebTest(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_file = tempfile.mkstemp()

        config = {
            'SECRET_KEY': TEST_SECRET_KEY,
            PYBEL_CONNECTION: 'sqlite:///' + self.db_file,
            'SECURITY_REGISTERABLE': True,
            'SECURITY_CONFIRMABLE': False,
            'SECURITY_SEND_REGISTER_EMAIL': False,
            'SECURITY_PASSWORD_HASH': 'pbkdf2_sha512',
            'SECURITY_PASSWORD_SALT': 'abcdefghijklmnopqeureasaggwdgs',
            'PYBEL_DS_CHECK_VERSION': True,
            'PYBEL_DS_EAGER': True,
            'PYBEL_DS_PRELOAD': True,
        }

        config.update(dict(
            CELERY_ALWAYS_EAGER=True,
            CELERY_RESULT_BACKEND='cache',
            CELERY_CACHE_BACKEND='memory',
            CELERY_EAGER_PROPAGATES_EXCEPTIONS=True
        ))

        self.app_instance = create_application(**config)

        build_main_service(self.app_instance)
        self.app_instance.register_blueprint(api_blueprint)
        self.app_instance.register_blueprint(upload_blueprint)

        self.pybel_app = FlaskPybel(self.app_instance)
        self.manager = self.pybel_app.manager
        self.api = self.pybel_app.api
        self.user_datastore = self.pybel_app.user_datastore
        self.user_datastore.create_user(email=TEST_USER_USERNAME, password=TEST_USER_PASSWORD)
        self.user_datastore.commit()

        self.app = self.app_instance.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_file)

    def login(self, username, password):
        return self.app.post(
            '/login',
            data=dict(
                username=username,
                password=password
            ),
            follow_redirects=True)

    def logout(self):
        return self.app.get('/logout', follow_redirects=True)

    def test_login(self):
        rv = self.login(TEST_USER_USERNAME, TEST_USER_PASSWORD)
        log.warning('%s', rv)
        self.assertTrue(rv.data)

    def test_upload(self):
        self.assertEqual(0, self.manager.count_networks())

        self.login(TEST_USER_USERNAME, TEST_USER_PASSWORD)

        f = open(test_bel_pickle_path, 'rb')

        response = self.app.post(
            '/upload',
            data={
                'file': (f, 'test_bel.gpickle')
            },
            follow_redirects=True,
        )

        log.warning('Response: %s', response)

        self.assertEqual(1, self.manager.count_networks())

    @unittest.skip
    def test_pipeline_view(self):
        pipeline_query = {
            'network_ids[]': ['1', '2'],
            'pubmed_selection[]': ['102323', '123023'],
            'node_selection[]': ['1', '2'],
            'seed_method': 'induction',
            'pipeline[]': ['function1']
        }

        self.login(TEST_USER_USERNAME, TEST_USER_PASSWORD)
        response = self.app.post(
            '/api/pipeline/query',
            data=pipeline_query,
        )

        response_data = json.loads(response.get_data())

        query_id = response_data['id']

        query = self.api.queries[query_id]

        self.assertEquals(pipeline_query['network_ids[]'], query.to_json()['network_ids'])
        self.assertEquals(pipeline_query['pipeline[]'], query.to_json()['pipeline'])
        self.assertEquals(pipeline_query['pubmed_selection[]'], query.to_json()['seeding'][0]['data'])
        self.assertEquals('pubmed', query.to_json()['seeding'][0]['type'])
        self.assertEquals(pipeline_query['node_selection[]'], query.to_json()['seeding'][1]['data'])
        self.assertEquals(pipeline_query['seed_method'], query.to_json()['seeding'][1]['type'])

    @unittest.skip
    def test_pipeline_view_2(self):
        pipeline_query = {
            'network_ids[]': ['1', '2'],
            'node_selection[]': ['1', '2'],
            'pubmed_selection[]': ['102323', '123023'],
            'author_selection[]': ['Bajorath', 'Hofmann-Apitius'],
            'seed_method': 'shortest_path',
            'pipeline[]': ['function1', 'function2']
        }

        self.login(TEST_USER_USERNAME, TEST_USER_PASSWORD)
        response = self.app.post(
            '/api/pipeline/query',
            data=pipeline_query,
        )

        response_data = json.loads(response.get_data())

        query_id = response_data['id']

        query = self.api.queries[query_id]

        self.assertEquals(pipeline_query['network_ids[]'], query.to_json()['network_ids'])
        self.assertEquals(pipeline_query['pipeline[]'], query.to_json()['pipeline'])
        self.assertEquals(pipeline_query['pubmed_selection[]'], query.to_json()['seeding'][0]['data'])
        self.assertEquals('pubmed', query.to_json()['seeding'][0]['type'])
        self.assertEquals(pipeline_query['author_selection[]'], query.to_json()['seeding'][1]['data'])
        self.assertEquals('authors', query.to_json()['seeding'][1]['type'])
        self.assertEquals(pipeline_query['node_selection[]'], query.to_json()['seeding'][2]['data'])
        self.assertEquals(pipeline_query['seed_method'], query.to_json()['seeding'][2]['type'])


if __name__ == '__main__':
    unittest.main()
