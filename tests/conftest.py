"""Root pytest fixtures — structural Mongo isolation via tests.db_guard."""

from __future__ import annotations

import pytest

from tests.db_guard import (
    assert_no_forbidden_test_imports,
    assert_prod_user_count_unchanged,
    bind_app_collections,
    get_prod_baseline,
    isolate_mongo_for_tests,
    rebind_active_test_db,
)


def pytest_collection_modifyitems(config, items):
    """Before any test runs: forbid direct DB imports; rebind; assert handles on test DB."""
    assert_no_forbidden_test_imports()
    bind_app_collections()


@pytest.fixture(scope="session", autouse=True)
def _isolate_mongo_db():
    """Hard-fail if targeting prod; run all suites against MONGO_TEST_DB_NAME; drop after."""
    yield from isolate_mongo_for_tests()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Late imports may capture Collection handles — re-bind before fixtures."""
    rebind_active_test_db()


@pytest.fixture(autouse=True)
def _rebind_mongo_before_each_test(_isolate_mongo_db):
    rebind_active_test_db()
    yield


def pytest_sessionfinish(session, exitstatus):
    """Outcome check: prod user set must be unchanged regardless of how a leak happened."""
    try:
        assert_prod_user_count_unchanged(get_prod_baseline())
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)
