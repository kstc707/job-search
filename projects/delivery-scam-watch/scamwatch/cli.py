"""Command-line entry point: `python -m scamwatch <command>`.

migrate      apply new migration files to the database in DATABASE_URL
hello        record one empty 'selftest' run, to prove the pipeline end to end
status       per source: enabled?, last run, its status and counts
purge-raw    clear raw source records older than 30 days
synth-a      write generator A's frozen synthetic data to data/synthetic/ (no database needed)
collect X    run one collector: phishingdb, phishingarmy, openphish, tranco, whoisds, ctlog, rdap
collect-all  run every keyless collector once, in a sensible order
report       recompute every result and chart into outputs/ from the database
watch        keep collecting for --hours: CT log sampling continuously, blocklist and OpenPhish
             snapshots every 30 minutes, new-registration list every 6 hours, RDAP as it goes
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


def _collect(conn, name: str, minutes: float) -> None:
    from .collectors import ctlog, lists, rdap
    from .http import Fetcher

    interval = conn.execute("SELECT min_interval_seconds FROM sources WHERE name = %s", (name,)).fetchone()
    fetcher = Fetcher(min_interval=float(interval[0]) if interval else 1.0)
    try:
        if name in ("phishingdb", "phishingarmy"):
            lists.collect_blocklist(conn, name, fetcher)
        elif name == "openphish":
            lists.collect_openphish(conn, fetcher)
        elif name == "tranco":
            lists.collect_tranco(conn, fetcher)
        elif name == "whoisds":
            lists.collect_whoisds(conn, fetcher)
        elif name == "ctlog":
            ctlog.collect_ctlog(conn, fetcher, minutes=minutes)
        elif name == "rdap":
            fetcher.max_tries = 1  # a rate limit ends the run at once instead of a long wait
            rdap.collect_rdap(conn, fetcher, limit=300)
        else:
            raise SystemExit(f"unknown collector {name!r}")
    finally:
        fetcher.close()


def _watch(hours: float, lists_only: bool = False, ct_only: bool = False) -> None:
    import time

    every = {} if ct_only else {"openphish": 30, "phishingdb": 30, "phishingarmy": 30, "whoisds": 360, "rdap": 15}
    last = {name: 0.0 for name in every}
    stop = time.monotonic() + hours * 3600
    while time.monotonic() < stop:
        with db.connect(Settings().database_url) as conn:
            for name, minutes in every.items():
                if time.monotonic() - last[name] >= minutes * 60:
                    try:
                        _collect(conn, name, 0)
                    except Exception as exc:  # noqa: BLE001
                        log("collector_failed", source=name, error=f"{type(exc).__name__}: {exc}")
                    last[name] = time.monotonic()
            if lists_only:
                time.sleep(60)
                continue
            try:
                _collect(conn, "ctlog", min(10.0, max(0.5, (stop - time.monotonic()) / 60)))
            except Exception as exc:  # noqa: BLE001
                log("collector_failed", source="ctlog", error=f"{type(exc).__name__}: {exc}")
            # the log publishes a new size only every few minutes: once caught up, wait
            time.sleep(60)


ORDER = ["phishingdb", "phishingarmy", "openphish", "tranco", "whoisds", "ctlog", "rdap"]


def cmd_report(conn) -> None:
    from .analysis import report

    res = report.run(conn)
    s = res["stream"]
    log(
        "report",
        labelled=res["labelled"]["brand_scope"],
        stream_keyword=s["keyword_domains"],
        stage1=s["after_stage1_rule"],
        flagged=s["after_stage2_model"],
    )


COMMANDS = {
    "report": cmd_report,
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
    parser.add_argument("command", choices=[*COMMANDS, "collect", "collect-all", "watch"])
    parser.add_argument("source", nargs="?", help="collector name for `collect`")
    parser.add_argument("--minutes", type=float, default=5.0, help="time budget for the CT log sampler")
    parser.add_argument("--hours", type=float, default=1.0, help="how long `watch` runs")
    parser.add_argument("--lists-only", action="store_true", help="watch: lists and RDAP, no CT sampling")
    parser.add_argument("--ct-only", action="store_true", help="watch: CT sampling only")
    args = parser.parse_args(argv)
    if args.command == "watch":
        _watch(args.hours, lists_only=args.lists_only, ct_only=args.ct_only)
        return
    if args.command in ("collect", "collect-all"):
        with db.connect(Settings().database_url) as conn:
            for name in [args.source] if args.command == "collect" else ORDER:
                try:
                    _collect(conn, name, args.minutes)
                except Exception as exc:  # noqa: BLE001  one failing source must not stop the others
                    log("collector_failed", source=name, error=f"{type(exc).__name__}: {exc}")
                    if args.command == "collect":
                        raise
        return
    if args.command in NO_DATABASE:
        COMMANDS[args.command](None)
        return
    settings = Settings()
    with db.connect(settings.database_url) as conn:
        COMMANDS[args.command](conn)
