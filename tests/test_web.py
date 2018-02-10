# -*- coding: utf-8 -*-

"""
Reference for testing Flask

- Flask Documentation http://flask.pocoo.org/docs/0.12/testing/
- Flask Cookbook: http://flask.pocoo.org/docs/0.12/tutorial/testing/
"""

import datetime
import json
import logging
import os
import tempfile
import unittest

from flask import url_for
from flask_security import current_user

from pybel.constants import PYBEL_CONNECTION
from pybel_web.application import FlaskPyBEL, create_application
from pybel_web.curation_service import curation_blueprint
from pybel_web.database_service import api_blueprint
from pybel_web.main_service import ui_blueprint
from pybel_web.parser_async_service import parser_async_blueprint

log = logging.getLogger(__name__)
log.setLevel(10)

TEST_USER_EMAIL = 'test@example.com'
TEST_USER_PASSWORD = 'password'
TEST_SECRET_KEY = 'pybel_web_tests'


def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)

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
            CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
            WTF_CSRF_ENABLED=False,
        ))

        self.app_instance = create_application(**config)

        self.app_instance.config.update({
            'LOGIN_DISABLED': False,
            'SERVER_NAME': 'localhost'

        })

        self.app_instance.register_blueprint(ui_blueprint)
        self.app_instance.register_blueprint(api_blueprint)
        self.app_instance.register_blueprint(parser_async_blueprint)
        self.app_instance.register_blueprint(curation_blueprint)

        self.pybel = FlaskPyBEL.get_state(self.app_instance)

        self.manager = self.pybel.manager

        self.pybel.user_datastore.create_user(
            email=TEST_USER_EMAIL,
            password=TEST_USER_PASSWORD,
            confirmed_at=datetime.datetime.now(),
        )
        self.pybel.user_datastore.commit()

        self.app = self.app_instance.test_client()

        with self.app_instance.app_context():
            self.manager.create_all()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_file)

    def login(self, email, password):
        """Logs a user in to the test application

        :type email: str
        :type password: str
        """
        with self.app_instance.app_context():
            return self.app.post(
                '/login',
                data=dict(
                    email=email,
                    password=password
                ),
                follow_redirects=True
            )

    def logout(self):
        """Logs a user out of the test application"""
        with self.app_instance.app_context():
            return self.app.get(
                '/logout',
                follow_redirects=True
            )

    @unittest.skip
    def test_login(self):
        """Test a user can be properly logged in then back out"""
        with self.app_instance.app_context():
            self.assertFalse(current_user.authenticated)

            self.login(TEST_USER_EMAIL, TEST_USER_PASSWORD)

            self.assertTrue(current_user.authenticated)
            self.assertEqual(TEST_USER_EMAIL, current_user.email)

            self.logout()
            self.assertFalse(current_user.authenticated)

    def test_ui_pages(self):
        """This test should visit each UI page and minimally, not error"""

        with self.app_instance.app_context():
            for rule in self.app_instance.url_map.iter_rules():
                # Filter out rules we can't navigate to in a browser
                # and rules that require parameters
                if "GET" in rule.methods and has_no_empty_params(rule):
                    # log.warning('getting rule %s: ', rule.endpoint)

                    if not rule.endpoint.startswith('ui'):
                        # log.warning('skipping %s', rule)
                        continue

                    url = url_for(rule.endpoint, **(rule.defaults or {}))

                    response = self.app.get(url, follow_redirects=True)

                    self.assertEqual(200, response.status_code)

    def test_api_count_users(self):
        with self.app_instance.app_context():
            response = self.app.get('/api/user/count')
            r = json.loads(response.data)
            self.assertIn('count', r)
            self.assertEqual(5, r['count'])

    @unittest.skip
    def test_pipeline_view(self):
        pipeline_query = {
            'network_ids[]': ['1', '2'],
            'pubmed_selection[]': ['102323', '123023'],
            'node_selection[]': ['1', '2'],
            'seed_method': 'induction',
            'pipeline[]': ['function1']
        }

        self.login(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        response = self.app.post(
            '/api/pipeline/query',
            data=pipeline_query,
        )

        response_data = json.loads(response.get_results_df())

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

        self.login(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        response = self.app.post(
            '/api/pipeline/query',
            data=pipeline_query,
        )

        response_data = json.loads(response.get_results_df())

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
