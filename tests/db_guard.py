"""Structural Mongo guard for pytest — sole owner of test DB access.

Importing this module raises RuntimeError if MONGO_TEST_DB_NAME is missing or
equals production. Test code must import collections from here, never from
onereside_chatbot.database.collections.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from pymongo.collection import Collection
from pymongo.database import Database

from onereside_chatbot.utils.env_load import mongo_prod_db_name, mongo_test_db_name

# Attribute name on collections module -> Mongo collection name
_COLLECTION_MAP = {
    "idac": "users",
    "git_app": "git_bookings",
    "appoinments": "bookings",
    "pims_calls": "pims_calls",
    "pims_systems": "pims_systems",
    "company": "company",
    "product": "product",
    "payments": "payments",
    "orders": "orders",
    "refunds": "refunds",
    "enquiries": "enquiries",
    "webhook_idempotency": "webhook_idempotency",
    "messages": "messages",
    "admin_logs": "admin_logs",
}

_FORBIDDEN_IMPORT_PREFIXES = (
    "onereside_chatbot.database.collections",
    "onereside_chatbot.database.database",
)

# Allow-listed relative paths under tests/ that may touch app database modules
_ALLOWED_GUARD_FILES = frozenset(
    {
        "db_guard.py",
        "db_isolation.py",  # thin re-export wrapper only
    }
)

_active_test_db: Database | None = None
_prod_user_baseline: dict[str, Any] | None = None
_session_started: bool = False

PROD_DB_NAME = mongo_prod_db_name
TEST_DB_NAME = mongo_test_db_name


def _assert_test_db_name_safe() -> str:
    test = mongo_test_db_name
    prod = mongo_prod_db_name
    if not test:
        raise RuntimeError(
            "REFUSING TO RUN: MONGO_TEST_DB_NAME is not set. "
            "Tests must use a dedicated database, never production."
        )
    if test == prod:
        raise RuntimeError(
            f"REFUSING TO RUN: MONGO_TEST_DB_NAME={test!r} matches production "
            f"MONGO_PROD_DB_NAME={prod!r}. Point tests at a separate database."
        )
    if test == "OneReside":
        raise RuntimeError(
            "REFUSING TO RUN: MONGO_TEST_DB_NAME must not be 'OneReside' (production)."
        )
    return test


# Fail fast at import — before any test fixture can write
_assert_test_db_name_safe()

# Shared client (same cluster); collections below always target TEST_DB_NAME
from onereside_chatbot.database.database import client as _client  # noqa: E402

_test_db: Database = _client[_assert_test_db_name_safe()]

# Test-facing collection handles (rebound whenever bind_app_collections runs)
idac: Collection = _test_db["users"]
git_app: Collection = _test_db["git_bookings"]
appoinments: Collection = _test_db["bookings"]
pims_calls: Collection = _test_db["pims_calls"]
pims_systems: Collection = _test_db["pims_systems"]
company: Collection = _test_db["company"]
product: Collection = _test_db["product"]
payments: Collection = _test_db["payments"]
orders: Collection = _test_db["orders"]
refunds: Collection = _test_db["refunds"]
enquiries: Collection = _test_db["enquiries"]
webhook_idempotency: Collection = _test_db["webhook_idempotency"]
messages: Collection = _test_db["messages"]
admin_logs: Collection = _test_db["admin_logs"]


def _refresh_module_exports(target_db: Database) -> None:
    """Keep this module's public Collection attrs on target_db."""
    mod = sys.modules[__name__]
    for attr, coll_name in _COLLECTION_MAP.items():
        setattr(mod, attr, target_db[coll_name])


def bind_app_collections(target_db: Database | None = None) -> Database:
    """Point database/collections modules + every Collection in sys.modules at target_db.

    Matches by isinstance(Collection), not attribute name — catches aliases like
    ``product as pd`` / ``product_col``.
    """
    global _active_test_db

    db = target_db if target_db is not None else _active_test_db
    if db is None:
        db = _client[_assert_test_db_name_safe()]

    import onereside_chatbot.database.collections as col_mod
    import onereside_chatbot.database.database as db_mod

    db_mod.db = db
    col_mod.db = db

    for attr, coll_name in _COLLECTION_MAP.items():
        setattr(col_mod, attr, db[coll_name])

    # Indexes only on the dedicated test DB — never touch prod indexes here
    if db.name == TEST_DB_NAME:
        db["orders"].create_index("order_id", unique=True, sparse=True)
        db["webhook_idempotency"].create_index("created_at", expireAfterSeconds=86400)
        db["messages"].create_index([("phone_number", 1), ("timestamp", -1)])
        db["admin_logs"].create_index([("timestamp", -1)])

    expected = db.name
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            items = list(vars(mod).items())
        except TypeError:
            continue
        for attr, existing in items:
            if not isinstance(existing, Collection):
                continue
            # Retarget same collection name onto expected DB
            setattr(mod, attr, db[existing.name])

    _refresh_module_exports(db)
    _active_test_db = db

    # Verify no Collection handle still points elsewhere
    bad: list[str] = []
    for mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        try:
            items = list(vars(mod).items())
        except TypeError:
            continue
        for attr, existing in items:
            if isinstance(existing, Collection) and existing.database.name != expected:
                bad.append(f"{mod_name}.{attr} -> {existing.database.name!r}")
    if bad:
        raise RuntimeError(
            "REFUSING TO RUN: Collection handle(s) not on test DB "
            f"{expected!r}:\n  - " + "\n  - ".join(bad[:40])
        )

    return db


def rebind_active_test_db() -> None:
    """Re-apply test DB binding if the session has started isolation."""
    if _active_test_db is not None:
        bind_app_collections(_active_test_db)


def snapshot_prod_user_count() -> dict[str, Any]:
    """Read-only snapshot of production users (local handles only — never stored on modules)."""
    prod = _client[PROD_DB_NAME]
    phones = sorted(
        str(d.get("phone_number") or "")
        for d in prod["users"].find({}, {"phone_number": 1})
    )
    return {
        "count": len(phones),
        "phones": phones,
        "messages": prod["messages"].count_documents({}),
    }


def assert_prod_user_count_unchanged(baseline: dict[str, Any] | None) -> None:
    if baseline is None:
        return
    after = snapshot_prod_user_count()
    if after["count"] == baseline["count"] and after["phones"] == baseline["phones"]:
        return
    before_set = set(baseline["phones"])
    after_set = set(after["phones"])
    added = sorted(after_set - before_set)
    removed = sorted(before_set - after_set)
    raise RuntimeError(
        "PRODUCTION DB LEAK DETECTED: OneReside user set changed during tests.\n"
        f"  users before={baseline['count']} after={after['count']}\n"
        f"  messages before={baseline.get('messages')} after={after['messages']}\n"
        f"  added phones ({len(added)}): {added[:30]}\n"
        f"  removed phones ({len(removed)}): {removed[:30]}"
    )


def assert_no_forbidden_test_imports(tests_root: Path | None = None) -> None:
    """Fail if any tests/*.py (except guard modules) imports app database modules."""
    root = tests_root or Path(__file__).resolve().parent
    violations: list[str] = []
    for path in root.rglob("*.py"):
        if path.name in _ALLOWED_GUARD_FILES:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        rel = path.relative_to(root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == p or alias.name.startswith(p + ".") for p in _FORBIDDEN_IMPORT_PREFIXES):
                        violations.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(
                    node.module == p or node.module.startswith(p + ".")
                    for p in _FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(f"{rel}:{node.lineno}: from {node.module} import ...")
    if violations:
        raise RuntimeError(
            "REFUSING TO RUN: tests must import Mongo only via tests.db_guard. "
            "Forbidden imports:\n  - " + "\n  - ".join(violations)
        )


def isolate_mongo_for_tests() -> Iterator[None]:
    """Session-scoped: drop leftover test DB, bind, yield, drop again."""
    global _active_test_db, _prod_user_baseline, _session_started

    test_name = _assert_test_db_name_safe()
    # Baseline before any test mutation
    _prod_user_baseline = snapshot_prod_user_count()
    _session_started = True

    _client.drop_database(test_name)
    test_db = _client[test_name]
    bind_app_collections(test_db)

    try:
        yield
    finally:
        try:
            assert_prod_user_count_unchanged(_prod_user_baseline)
        finally:
            _active_test_db = None
            _session_started = False
            _client.drop_database(test_name)
            # Restore app handles to prod for any long-lived process sharing the interpreter
            bind_app_collections(_client[PROD_DB_NAME])


def get_prod_baseline() -> dict[str, Any] | None:
    return _prod_user_baseline
