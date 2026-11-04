"""SQL Server connection and SQL file helpers.

Every SQL file in ``sql/`` uses Crystal Reports parameter syntax (``'{?StartDate}'``) so the same
text can be pasted into a Crystal "Add Command" dialog. ``load_command`` turns that into a
pymssql parameterized query (``%(StartDate)s``), so the harness never splices values into SQL.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pymssql

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

_PLACEHOLDER = re.compile(r"'\{\?(\w+)\}'")
_BARE_PLACEHOLDER = re.compile(r"\{\?\w+\}")


def settings() -> dict:
    return {
        "server": os.environ.get("PERMIT_DB_SERVER", "localhost"),
        "port": int(os.environ.get("PERMIT_DB_PORT", "1433")),
        "user": os.environ.get("PERMIT_DB_USER", "sa"),
        "password": os.environ.get("MSSQL_SA_PASSWORD", ""),
        "database": os.environ.get("PERMIT_DB_NAME", "PermitReporting"),
    }


def connect(database: str | None = None, autocommit: bool = False, timeout: int = 0):
    s = settings()
    if not s["password"]:
        raise RuntimeError("Set MSSQL_SA_PASSWORD (see .env.example).")
    return pymssql.connect(
        server=s["server"], port=s["port"], user=s["user"], password=s["password"],
        database=database or s["database"], autocommit=autocommit, login_timeout=5, timeout=timeout,
    )


def translate_command(text: str) -> tuple[str, list[str]]:
    """Crystal command text -> (pymssql SQL, parameter names it uses).

    Literal ``%`` must be doubled for pymssql's pyformat style. A placeholder that is not wrapped
    in single quotes is rejected: in Crystal it would be spliced in unquoted.
    """
    names = sorted(set(_PLACEHOLDER.findall(text)))
    sql = text.replace("%", "%%")
    sql = _PLACEHOLDER.sub(lambda m: f"%({m.group(1)})s", sql)
    leftover = _BARE_PLACEHOLDER.search(sql)
    if leftover:
        raise ValueError(f"unquoted Crystal placeholder {leftover.group(0)}; wrap it in single quotes")
    return sql, names


def load_command(relpath: str) -> tuple[str, list[str]]:
    return translate_command((SQL_DIR / relpath).read_text(encoding="utf-8"))


def split_batches(script: str) -> list[str]:
    """Split a T-SQL script on lines that contain only GO (what sqlcmd and SSMS do)."""
    batches, current = [], []
    for line in script.splitlines():
        if line.strip().upper() == "GO":
            batches.append("\n".join(current))
            current = []
        else:
            current.append(line)
    batches.append("\n".join(current))
    return [b for b in batches if b.strip() and not all(
        l.strip().startswith("--") or not l.strip() for l in b.splitlines())]


def run_script(conn, relpath: str) -> None:
    cur = conn.cursor()
    for batch in split_batches((SQL_DIR / relpath).read_text(encoding="utf-8")):
        cur.execute(batch)
    conn.commit()


def query(conn, sql: str, params: dict | None = None) -> tuple[list[str], list[tuple]]:
    cur = conn.cursor()
    cur.execute(sql, params or None)
    cols = [c[0] for c in cur.description]
    return cols, cur.fetchall()


def ensure_database() -> None:
    name = settings()["database"]
    if not re.fullmatch(r"\w+", name):
        raise ValueError(f"bad database name {name!r}")
    conn = connect(database="master", autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(f"IF DB_ID('{name}') IS NULL CREATE DATABASE [{name}]")
    finally:
        conn.close()


def reachable() -> bool:
    try:
        connect(database="master").close()
        return True
    except Exception:
        return False
