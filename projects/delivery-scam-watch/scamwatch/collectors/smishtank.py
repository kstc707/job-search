"""SmishTank: real scam text messages reported by the public.

Two parts, both public and allowed by robots.txt:
  - Dataset I: the CSV the SmishTank researchers publish for research use (cite Timko & Rahman, 2024).
    About 1,000 texts reported in 2022-2023, with sender, link and the brand each one impersonates.
  - The feed: the newest 100 reported texts, the same list the site's home page shows. Polling it
    over time builds a fresh, dated collection.

Texts go into `reports`. Every link found in a text is also stored as a URL, domain and observation
(source 'smishtank'), so message links join the same tables the domain monitor uses.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

import psycopg

from ..analysis.texts import extract_urls
from ..config import load_brands
from ..http import Fetcher
from ..runlog import CollectorRun
from ..store import add_observation, upsert_url

DATASET_URL = "https://smishtank.com/analysisdataset.csv"
FEED_URL = "https://l0sry40g26.execute-api.us-west-1.amazonaws.com/prod/getsmish?type=smish"


# ---------------------------------------------------------------- parsing (pure) ----
def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "null") else None


def parse_dataset(raw: bytes) -> list[dict]:
    """Dataset I CSV -> report dicts. The file is Latin-1, not UTF-8."""
    out = []
    for r in csv.DictReader(io.StringIO(raw.decode("latin-1"))):
        text = _clean(r.get("MainText")) or _clean(r.get("Fulltext"))
        if not text:
            continue
        posted = None
        if t := _clean(r.get("timeReceived")):
            try:
                posted = datetime.strptime(t, "%m/%d/%Y, %H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                posted = None
        extra = [
            u
            for u in (
                extract_urls(_clean(r.get("Url")) or "") + extract_urls(_clean(r.get("FullyQualifiedDomain")) or "")
            )
        ]
        out.append(
            {
                "external_id": f"d1:{r['messageid']}",
                "posted_at": posted,
                "text": text,
                "sender": _clean(r.get("Sender")),
                "sender_type": _clean(r.get("SenderType")),
                "brand_claimed": _clean(r.get("Brand")),
                "urls": list(dict.fromkeys(extract_urls(text) + extra)),
            }
        )
    return out


def parse_feed(payload: dict) -> list[dict]:
    out = []
    for s in payload.get("smishes", []):
        text = _clean(s.get("messageContent")) or _clean(s.get("rawText"))
        ref = _clean(s.get("messageID")) or _clean(s.get("request_id"))
        if not text or not ref:
            continue
        ms = s.get("timeReceived")
        posted = datetime.fromtimestamp(ms / 1000, tz=UTC) if isinstance(ms, (int, float)) else None
        out.append(
            {
                "external_id": f"feed:{ref}",
                "posted_at": posted,
                "text": text,
                "sender": _clean(s.get("sender")),
                "sender_type": None,
                "brand_claimed": None,
                "urls": list(dict.fromkeys(extract_urls(text) + extract_urls(_clean(s.get("url")) or ""))),
            }
        )
    return out


# ---------------------------------------------------------------- storing ----------
def _store(conn: psycopg.Connection, run: CollectorRun, reports: list[dict]) -> None:
    brands = load_brands()
    for r in reports:
        run.seen += 1
        row = conn.execute(
            """INSERT INTO reports (source_id, run_id, external_id, posted_at, text, extracted_urls,
                                    sender, sender_type, brand_claimed)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (source_id, external_id) DO NOTHING RETURNING id""",
            (run.source_id, run.id, r["external_id"], r["posted_at"], r["text"], r["urls"],
             r["sender"], r["sender_type"], r["brand_claimed"]),
        ).fetchone()  # fmt: skip
        if row is None:
            continue
        run.new += 1
        for url in r["urls"]:
            try:
                url_id, dom_id = upsert_url(conn, url, brands, r["posted_at"])
            except ValueError:
                continue
            add_observation(
                conn,
                source_id=run.source_id,
                run_id=run.id,
                source_ref=f"{r['external_id']}|{url}",
                domain_id=dom_id,
                url_id=url_id,
                source_time=r["posted_at"],
            )
    conn.commit()


def collect_smishtank(conn: psycopg.Connection, fetcher: Fetcher, dataset: bool | None = None) -> None:
    """The feed every run; the published dataset only until it is stored once (it does not change)."""
    with CollectorRun(conn, "smishtank") as run:
        if dataset is None:
            dataset = not conn.execute(
                "SELECT 1 FROM reports WHERE source_id = %s AND external_id LIKE 'd1:%%' LIMIT 1", (run.source_id,)
            ).fetchone()
        if dataset:
            _store(conn, run, parse_dataset(fetcher.get(DATASET_URL).content))
        _store(conn, run, parse_feed(fetcher.get(FEED_URL).json()))
