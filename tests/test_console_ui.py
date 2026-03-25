import unittest

from fastapi.testclient import TestClient

from app.main import app


class ConsoleUiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_console_page_and_assets_are_served(self):
        console_response = self.client.get('/console')
        self.assertEqual(console_response.status_code, 200)
        self.assertIn('text/html', console_response.headers['content-type'])
        self.assertIn('AI Coding Knowledge Console', console_response.text)

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


if __name__ == '__main__':
    unittest.main()
