"""Command-line entry point: `python -m scamwatch <command>`.

migrate      apply new migration files to the database in DATABASE_URL
hello        record one empty 'selftest' run, to prove the pipeline end to end
status       per source: enabled?, last run, its status and counts
purge-raw    clear raw source records older than 30 days
synth-a      write generator A's frozen synthetic data to data/synthetic/ (no database needed)
"""

from __future__ import annotations

import argparse

from . import db
from .config import Settings
from .runlog import CollectorRun, log
from .store import purge_raw


def cmd_migrate(conn) -> None:
    applied = db.migrate(conn)
    log("migrate", applied=applied or "nothing new")


def cmd_hello(conn) -> None:
    with CollectorRun(conn, "selftest") as run:
        run.seen = 0


def cmd_status(conn) -> None:
    rows = conn.execute(
        """SELECT s.name, s.enabled, r.started_at, r.status, r.items_seen, r.items_new, r.error
           FROM sources s
           LEFT JOIN LATERAL (SELECT * FROM collector_runs c WHERE c.source_id = s.id
                              ORDER BY started_at DESC LIMIT 1) r ON TRUE
           ORDER BY s.id"""
    ).fetchall()
    print(f"{'source':10} {'enabled':8} {'last run (UTC)':20} {'status':8} {'seen':>6} {'new':>6}  error")
    for name, enabled, started, status, seen, new, error in rows:
        when = started.strftime("%Y-%m-%d %H:%M") if started else "never"
        print(f"{name:10} {str(enabled):8} {when:20} {status or '-':8} {seen or 0:>6} {new or 0:>6}  {error or ''}")


def cmd_purge(conn) -> None:
    n = purge_raw(conn)
    conn.commit()
    log("purge_raw", cleared=n)


def cmd_synth_a(_conn) -> None:
    from .config import PROJECT_ROOT
    from .synthetic import generator_a

    paths = generator_a.write(PROJECT_ROOT / "data" / "synthetic")
    log("synth_a", files=[str(p.relative_to(PROJECT_ROOT)) for p in paths])


COMMANDS = {
    "migrate": cmd_migrate,
    "hello": cmd_hello,
    "status": cmd_status,
    "purge-raw": cmd_purge,
    "synth-a": cmd_synth_a,
}
NO_DATABASE = {"synth-a"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="scamwatch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args(argv)
    if args.command in NO_DATABASE:
        COMMANDS[args.command](None)
        return
    settings = Settings()
    with db.connect(settings.database_url) as conn:
        COMMANDS[args.command](conn)
