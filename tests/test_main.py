import logging
from telefiles.__main__ import _configure_logging


def test_configure_logging_quiets_httpx():
    _configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    # the app's own logger still emits at INFO
    assert logging.getLogger("telefiles").getEffectiveLevel() == logging.INFO
