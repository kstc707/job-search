"""Tests run against TEST_DATABASE_URL only (a Neon test branch or a local Postgres), never the
real data. Each test session starts from an empty database: every table is dropped first."""

from __future__ import annotations

import psycopg
import pytest

from scamwatch import db
from scamwatch.config import Settings, load_brands


@pytest.fixture(scope="session")
def db_url() -> str:
    url = Settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if url == Settings().database_url:
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL: tests drop every table.")
    return url


def _reset(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.commit()


@pytest.fixture()
def conn(db_url):
    """A freshly migrated, empty database for each test."""
    with psycopg.connect(db_url) as c:
        _reset(c)
        db.migrate(c)
        yield c


@pytest.fixture(scope="session")
def brands():
    return load_brands()
