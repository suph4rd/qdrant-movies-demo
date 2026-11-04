import runpy
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError


WAIT_PATH = Path(__file__).resolve().parents[2] / 'docker' / 'wait_for_qdrant.py'


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.wait = runpy.run_path(str(WAIT_PATH))['wait_for_qdrant']

    def test_retries_errors_and_non_200_until_ready(self):
        unavailable = MagicMock()
        unavailable.__enter__.return_value.status = 204
        ready = MagicMock()
        ready.__enter__.return_value.status = 200
        opener = MagicMock(side_effect=[URLError('offline'), unavailable, ready])
        with patch.dict(self.wait.__globals__, urlopen=opener):
            with patch.dict('os.environ', {}, clear=True), patch('time.sleep'):
                self.assertTrue(self.wait())
        self.assertEqual(opener.call_count, 3)
        unavailable.__exit__.assert_called_once()
        ready.__exit__.assert_called_once()

    def test_deadline_limits_requests_and_sleep(self):
        opener = MagicMock(side_effect=OSError('offline'))
        with patch.dict(self.wait.__globals__, urlopen=opener):
            with patch.dict('os.environ', {}, clear=True), patch('time.monotonic', side_effect=[0, 59.5, 59.8, 60]):
                with patch('time.sleep') as sleep:
                    self.assertFalse(self.wait())
        opener.assert_called_once_with('http://qdrant:6333/readyz', timeout=0.5)
        self.assertAlmostEqual(sleep.call_args.args[0], 0.2)

    def test_uses_configured_qdrant_url(self):
        ready = MagicMock()
        ready.__enter__.return_value.status = 200
        opener = MagicMock(return_value=ready)
        with patch.dict(self.wait.__globals__, urlopen=opener):
            with patch.dict('os.environ', QDRANT_URL='http://custom:7444/base/'):
                self.assertTrue(self.wait())
        opener.assert_called_once_with('http://custom:7444/base/readyz', timeout=2)
        ready.__exit__.assert_called_once()


class HealthcheckTests(unittest.TestCase):
    def setUp(self):
        path = WAIT_PATH.with_name('healthcheck.py')
        self.check = runpy.run_path(str(path))['main']

    def test_status_and_response_closure(self):
        for status, expected in [(200, 0), (204, 1), (503, 1)]:
            with self.subTest(status=status):
                response = MagicMock()
                response.__enter__.return_value.status = status
                opener = MagicMock(return_value=response)
                with patch.dict(self.check.__globals__, urlopen=opener):
                    self.assertEqual(self.check(), expected)
                opener.assert_called_once_with('http://127.0.0.1:5000/', timeout=3)
                response.__exit__.assert_called_once()

    def test_connection_error(self):
        for error in [URLError('offline'), OSError('offline')]:
            with self.subTest(error=error):
                with patch.dict(self.check.__globals__, urlopen=MagicMock(side_effect=error)):
                    self.assertEqual(self.check(), 1)

    def test_http_error_response_is_closed(self):
        body = MagicMock()
        error = HTTPError('http://127.0.0.1:5000/', 503, 'Unavailable', {}, body)
        with patch.dict(self.check.__globals__, urlopen=MagicMock(side_effect=error)):
            self.assertEqual(self.check(), 1)
        body.close.assert_called_once()
