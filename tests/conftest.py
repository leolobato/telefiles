import logging

import pytest


def pytest_runtest_setup(item):
    """Clear pytest logging handlers for test_main.py to allow basicConfig to work."""
    if "test_main" in str(item.fspath):
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.NOTSET)


def pytest_runtest_call(item):
    """Ensure handlers are cleared just before test execution."""
    if "test_main" in str(item.fspath):
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.NOTSET)
