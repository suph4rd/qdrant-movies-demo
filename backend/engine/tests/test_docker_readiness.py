import runpy
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from backend.engine.stores import factory


WAIT_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'wait_for_qdrant.py'


def mock_client(*, responses=None, error=None):
    context = MagicMock()
    client = context.__enter__.return_value
    client.get.side_effect = error if error is not None else responses
    return context, client


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.wait = runpy.run_path(str(WAIT_PATH))['wait_for_qdrant']

    def test_retries_errors_and_non_200_until_ready(self):
        context, client = mock_client(responses=[
            httpx.ConnectError('offline'),
            httpx.ReadTimeout('slow'),
            httpx.Response(503),
            httpx.Response(204),
            httpx.Response(200),
        ])
        with patch('httpx.Client', return_value=context) as factory:
            with patch.dict('os.environ', {}, clear=True), patch('time.sleep'):
                self.assertTrue(self.wait())
        factory.assert_called_once_with(follow_redirects=True)
        self.assertEqual(client.get.call_count, 5)
        context.__exit__.assert_called_once()

    def test_deadline_limits_requests_and_sleep(self):
        context, client = mock_client(error=httpx.ConnectError('offline'))
        with patch('httpx.Client', return_value=context):
            with patch.dict('os.environ', {}, clear=True), patch('time.monotonic', side_effect=[0, 59.5, 59.8, 60]):
                with patch('time.sleep') as sleep:
                    self.assertFalse(self.wait())
        client.get.assert_called_once_with('http://qdrant:6333/readyz', timeout=0.5)
        self.assertAlmostEqual(sleep.call_args.args[0], 0.2)
        context.__exit__.assert_called_once()

    def test_expired_deadline_skips_requests(self):
        context, client = mock_client()
        with patch('httpx.Client', return_value=context), patch('time.monotonic', side_effect=[0, 60]):
            with patch('time.sleep') as sleep:
                self.assertFalse(self.wait())
        client.get.assert_not_called()
        sleep.assert_not_called()
        context.__exit__.assert_called_once()

    def test_uses_configured_qdrant_url(self):
        context, client = mock_client(responses=[httpx.Response(200)])
        with patch('httpx.Client', return_value=context):
            with patch.dict('os.environ', QDRANT_URL='http://custom:7444/base/'):
                self.assertTrue(self.wait())
        client.get.assert_called_once_with('http://custom:7444/base/readyz', timeout=2)
        context.__exit__.assert_called_once()

    def test_uses_explicit_url(self):
        context, client = mock_client(responses=[httpx.Response(200)])
        with patch('httpx.Client', return_value=context):
            self.assertTrue(self.wait('http://explicit:6333/readyz'))
        client.get.assert_called_once_with('http://explicit:6333/readyz', timeout=2)
        context.__exit__.assert_called_once()


class HealthcheckTests(unittest.TestCase):
    def setUp(self):
        path = WAIT_PATH.with_name('healthcheck.py')
        self.check = runpy.run_path(str(path))['main']

    def test_status_and_client_closure(self):
        for status, expected in [(200, 0), (204, 1), (503, 1)]:
            with self.subTest(status=status):
                context, client = mock_client(responses=[httpx.Response(status)])
                with patch('httpx.Client', return_value=context) as factory:
                    self.assertEqual(self.check(), expected)
                factory.assert_called_once_with(follow_redirects=True)
                client.get.assert_called_once_with('http://127.0.0.1:18000/api/context', timeout=3)
                context.__exit__.assert_called_once()

    def test_connection_error_and_timeout_close_client(self):
        for error in [httpx.ConnectError('offline'), httpx.ConnectTimeout('slow'), httpx.ReadTimeout('slow')]:
            with self.subTest(error=error):
                context, client = mock_client(error=error)
                with patch('httpx.Client', return_value=context):
                    self.assertEqual(self.check(), 1)
                context.__exit__.assert_called_once()
