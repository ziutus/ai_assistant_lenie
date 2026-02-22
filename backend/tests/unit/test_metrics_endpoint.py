import unittest
import os
import sys
from unittest.mock import MagicMock

# This test requires Flask and other server dependencies.
# Skip gracefully when run in minimal uvx environment without --with flags.
#
# NOTE: sys.modules mocking at module level is required because server.py
# instantiates WebsitesDBPostgreSQL at import time. This means psycopg2 must
# be mocked BEFORE the import. Run unit and integration tests separately
# (pytest tests/unit/ vs tests/integration/) to avoid mock contamination.
try:
    # Mock psycopg2 module in sys.modules before any import tries to load it
    _mock_psycopg2 = MagicMock()
    _mock_conn = MagicMock()
    _mock_psycopg2.connect.return_value = _mock_conn
    _mock_cursor = MagicMock()
    _mock_cursor.fetchone.return_value = (0,)
    _mock_conn.cursor.return_value = _mock_cursor
    _mock_conn.__enter__ = MagicMock(return_value=_mock_conn)
    _mock_conn.__exit__ = MagicMock(return_value=False)
    sys.modules.setdefault('psycopg2', _mock_psycopg2)
    sys.modules.setdefault('psycopg2.sql', MagicMock())
    sys.modules.setdefault('psycopg2.extras', MagicMock())

    # Set required environment variables for server module initialization
    _env_defaults = {
        'ENV_DATA': 'test',
        'LLM_PROVIDER': 'openai',
        'OPENAI_ORGANIZATION': 'test-org',
        'OPENAI_API_KEY': 'test-key',
        'AI_MODEL_SUMMARY': 'test-model',
        'BACKEND_TYPE': 'postgresql',
        'POSTGRESQL_HOST': 'localhost',
        'POSTGRESQL_DATABASE': 'testdb',
        'POSTGRESQL_USER': 'testuser',
        'POSTGRESQL_PASSWORD': 'testpass',
        'POSTGRESQL_PORT': '5432',
        'EMBEDDING_MODEL': 'test-model',
        'PORT': '5000',
        'STALKER_API_KEY': 'test-api-key',
    }
    for _key, _value in _env_defaults.items():
        os.environ.setdefault(_key, _value)

    from server import app
    _server_available = True
except ImportError:
    _server_available = False


@unittest.skipUnless(_server_available, "Requires Flask and server dependencies (use uvx --with flags)")
class TestMetricsEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.api_key = os.environ.get('STALKER_API_KEY', 'test-api-key')

    def test_metrics_returns_200(self):
        response = self.client.get('/metrics', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)

    def test_metrics_contains_prometheus_help_and_type(self):
        response = self.client.get('/metrics', headers={'x-api-key': self.api_key})
        self.assertIn(b'# HELP lenie_app_info', response.data)
        self.assertIn(b'# TYPE lenie_app_info gauge', response.data)

    def test_metrics_contains_app_info_metric_with_version(self):
        response = self.client.get('/metrics', headers={'x-api-key': self.api_key})
        self.assertIn(b'lenie_app_info{version="', response.data)
        self.assertIn(b'} 1', response.data)

    def test_metrics_content_type_is_text_plain(self):
        response = self.client.get('/metrics', headers={'x-api-key': self.api_key})
        self.assertIn('text/plain', response.content_type)

    def test_healthz_not_affected(self):
        response = self.client.get('/healthz', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
