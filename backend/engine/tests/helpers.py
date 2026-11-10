from contextlib import contextmanager
from types import SimpleNamespace

from backend.engine import errors


@contextmanager
def expected_error(test):
    result = SimpleNamespace(exception=None)
    with test.assertRaises(Exception) as raised:
        yield result
    result.exception = raised.exception
    test.assertTrue(errors.is_expected_error(result.exception))
