"""Append-only JSONL log of applications, kept locally (it holds personal data).

Tsenta already rejects exact duplicates by job, but the same posting often appears
under several URLs (tracking parameters, board vs ATS link). The ledger dedupes on a
normalized URL and enforces a daily cap before anything is sent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_", "gh_src", "lever-source", "source", "ref", "src")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


@dataclass
class Entry:
    company: str
    title: str
    url: str = ""
    job_id: str = ""
    application_id: str = ""
    status: str = ""
    resume_sha256: str = ""
    note: str = ""
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def entries(self) -> list[Entry]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [Entry(**json.loads(line)) for line in f if line.strip()]

    def add(self, entry: Entry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def find(self, *, job_id: str = "", url: str = "") -> Entry | None:
        key = normalize_url(url) if url else ""
        for e in self.entries():
            if job_id and e.job_id == job_id:
                return e
            if key and e.url and normalize_url(e.url) == key:
                return e
        return None

    def count_on(self, day: date) -> int:
        return sum(
            1 for e in self.entries()
            if datetime.fromisoformat(e.at).astimezone().date() == day
        )
