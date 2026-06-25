import logging
from telefiles.__main__ import _configure_logging


def test_configure_logging_quiets_httpx():
    _configure_logging()
    # Successful long-poll requests log via httpx at INFO; raising the httpx
    # logger to WARNING silences them while still surfacing failures.
    assert logging.getLogger("httpx").level == logging.WARNING
