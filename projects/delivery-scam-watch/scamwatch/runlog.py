"""One `collector_runs` row per scraper run, plus one-line JSON logs.

    with CollectorRun(conn, "crtsh") as run:
        ...                       # do the work
        run.seen += 1             # count every item looked at
        run.new += 1              # count items that were new
        run.partial("crt.sh timed out on 1 of 6 keywords")   # optional: some work failed

The row is written as 'running' at the start (committed, so a crash still leaves a trace) and
closed as success, partial or failed at the end. An exception marks the run failed, saves the
error message and is re-raised so the scheduled job shows red.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime

import psycopg

from .store import source_id


def log(event: str, **fields) -> None:
    record = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)


class CollectorRun:
    def __init__(self, conn: psycopg.Connection, source: str) -> None:
        self.conn = conn
        self.source = source
        self.source_id = source_id(conn, source)
        self.id: int | None = None
        self.seen = 0
        self.new = 0
        self._problems: list[str] = []
        self._t0 = 0.0

    def partial(self, problem: str) -> None:
        self._problems.append(problem)
        log("run_problem", source=self.source, run_id=self.id, problem=problem)

    def __enter__(self) -> CollectorRun:
        self.id = self.conn.execute(
            "INSERT INTO collector_runs (source_id) VALUES (%s) RETURNING id", (self.source_id,)
        ).fetchone()[0]
        self.conn.commit()
        self._t0 = time.monotonic()
        log("run_start", source=self.source, run_id=self.id)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            self.conn.rollback()  # drop half-written items from the failed run
            status, error = "failed", f"{exc_type.__name__}: {exc}"
        elif self._problems:
            status, error = "partial", "; ".join(self._problems)
        else:
            status, error = "success", None
        self.conn.execute(
            """UPDATE collector_runs SET finished_at = now(), status = %s, items_seen = %s,
               items_new = %s, error = %s WHERE id = %s""",
            (status, self.seen, self.new, error, self.id),
        )
        self.conn.commit()
        log(
            "run_end",
            source=self.source,
            run_id=self.id,
            status=status,
            seen=self.seen,
            new=self.new,
            seconds=round(time.monotonic() - self._t0, 1),
            error=error,
        )
        return False  # never swallow the exception
