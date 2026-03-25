import os
import unittest
from importlib import reload

from fastapi.testclient import TestClient

import app.main as main_module


class ConsoleUiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main_module.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_console_page_and_assets_are_served(self):
        console_response = self.client.get('/console')
        self.assertEqual(console_response.status_code, 200)
        self.assertIn('text/html', console_response.headers['content-type'])
        self.assertIn('AI Coding Knowledge Console', console_response.text)
        self.assertIn('系统自评与验收', console_response.text)

        script_response = self.client.get('/static/console/main.js')
        self.assertEqual(script_response.status_code, 200)
        self.assertIn('javascript', script_response.headers['content-type'])
        self.assertIn('runDemo', script_response.text)

        style_response = self.client.get('/static/console/styles.css')
        self.assertEqual(style_response.status_code, 200)
        self.assertIn('text/css', style_response.headers['content-type'])
        self.assertIn('.hero-panel', style_response.text)

    def test_root_and_readyz_publish_console_entry(self):
        root_response = self.client.get('/')
        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(root_response.json()['console'], '/console')

        ready_response = self.client.get('/readyz')
        self.assertEqual(ready_response.status_code, 200)
        self.assertIn(ready_response.json()['status'], {'ok', 'degraded'})
        self.assertIn('schema', ready_response.json())
        self.assertIn('ok', ready_response.json()['schema'])


class ConsoleUiWithApiKeyTestCase(unittest.TestCase):
    def setUp(self):
        self.previous_api_key = os.environ.get('AICODING_API_KEY')
        os.environ['AICODING_API_KEY'] = 'console-secret'
        self.main_module = reload(main_module)
        self.client = TestClient(self.main_module.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        if self.previous_api_key is None:
            os.environ.pop('AICODING_API_KEY', None)
        else:
            os.environ['AICODING_API_KEY'] = self.previous_api_key
        reload(main_module)

    def test_console_and_health_routes_remain_accessible_without_api_key(self):
        for path in ('/healthz', '/readyz', '/console', '/static/console/main.js', '/favicon.ico'):
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 200 if path != '/favicon.ico' else 307)

    def test_protected_api_still_requires_api_key(self):
        response = self.client.get('/api/v1/audit/logs')
        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
