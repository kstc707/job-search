"""Database connection and migrations.

Migrations are numbered SQL files in db/migrations, applied in order and recorded in the
`schema_migrations` table with a checksum. If an already-applied file is edited, `migrate`
refuses to run: a change to the database must always be a new numbered file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg

from .config import MIGRATIONS_DIR


class MigrationEdited(RuntimeError):
    """An applied migration file no longer matches what was applied."""


def connect(url: str) -> psycopg.Connection:
    if not url:
        raise RuntimeError("No database URL set. Put DATABASE_URL in your .env file (see .env.example).")
    return psycopg.connect(url)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(conn: psycopg.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every migration not yet applied. Returns the file names applied this time."""
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                         filename TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                         applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        cur.execute("SELECT filename, sha256 FROM schema_migrations")
        applied = dict(cur.fetchall())
    conn.commit()

    done = []
    for path in sorted(migrations_dir.glob("*.sql")):
        digest = _checksum(path)
        if path.name in applied:
            if applied[path.name] != digest:
                raise MigrationEdited(
                    f"{path.name} was changed after it was applied. "
                    "Undo the edit and put the change in a new migration file."
                )
            continue
        with conn.transaction():  # all of a migration applies, or none of it
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (filename, sha256) VALUES (%s, %s)", (path.name, digest))
        done.append(path.name)
    return done
