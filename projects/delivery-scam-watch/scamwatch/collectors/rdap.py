"""RDAP enrichment: when was a domain registered, and by which registrar.

rdap.org redirects each query to the registry that runs the domain's ending (.com, .top ...).
Only brand-keyword domains that are not allowlisted are looked up, each registered domain
once, at most `limit` per run, with a polite gap between requests.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import psycopg

from ..http import Fetcher
from ..runlog import CollectorRun

RDAP_URL = "https://rdap.org/domain/{domain}"


def parse_rdap(doc: dict) -> tuple[datetime | None, str | None]:
    created = None
    for ev in doc.get("events", []):
        if ev.get("eventAction") == "registration" and ev.get("eventDate"):
            created = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
            break
    registrar = None
    for ent in doc.get("entities", []):
        if "registrar" in ent.get("roles", []):
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if item and item[0] == "fn":
                    registrar = item[3]
            break
    return created, registrar


def pending_domains(conn: psycopg.Connection, limit: int) -> list[str]:
    rows = conn.execute(
        """SELECT d.registered_domain, min(d.first_seen) AS first
           FROM domains d LEFT JOIN registrations r ON r.registered_domain = d.registered_domain
           WHERE d.brand_guess IS NOT NULL AND NOT d.allowlisted AND r.registered_domain IS NULL
           GROUP BY d.registered_domain ORDER BY first DESC LIMIT %s""",
        (limit,),
    ).fetchall()
    return [r[0] for r in rows]


def collect_rdap(conn: psycopg.Connection, fetcher: Fetcher, limit: int = 200, only: list[str] | None = None) -> None:
    with CollectorRun(conn, "rdap") as run:
        for domain in only or pending_domains(conn, limit):
            run.seen += 1
            try:
                resp = fetcher.get(RDAP_URL.format(domain=domain))
                created, registrar = parse_rdap(resp.json())
                status = "ok"
            except httpx.HTTPStatusError as exc:
                created = registrar = None
                status = "not_found" if exc.response.status_code == 404 else "unsupported"
            except (RuntimeError, ValueError):
                created = registrar = None
                status = "error"
            conn.execute(
                """INSERT INTO registrations (registered_domain, created_at, registrar, status)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (registered_domain) DO UPDATE SET created_at = EXCLUDED.created_at,
                     registrar = EXCLUDED.registrar, status = EXCLUDED.status, checked_at = now()""",
                (domain, created, registrar, status),
            )
            if status == "ok":
                run.new += 1
            conn.commit()
