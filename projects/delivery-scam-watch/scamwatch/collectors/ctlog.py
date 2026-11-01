"""Certificate Transparency log sampler (RFC 6962), reading Google's Argon 2026h2 log directly.

Every publicly trusted website certificate is published to CT logs, usually within minutes of
being issued, and a scam site needs one before it can show the padlock. So a new certificate
for `usps-redelivery-fee.top` is often the earliest public sign of a new scam site.

How it works:
  1. get-sth: the log's current size (number of certificates so far).
  2. get-entries: download entries in batches (the log returns up to about 20 per request).
  3. Decode each entry's binary MerkleTreeLeaf to reach the certificate, read its domain names
     (subjectAltName), keep the ones containing a brand keyword.
  4. Remember the position in collector_state so the next run continues where this one stopped.

The log grows by hundreds of certificates a second, more than one polite client should read,
so this is a SAMPLE: when the saved position falls further behind than `max_lag`, the run jumps
forward and records how many certificates it skipped. Results are reported as a sample.
"""

from __future__ import annotations

import base64
import struct
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from cryptography import x509

from ..config import load_brands
from ..http import Fetcher
from ..runlog import CollectorRun, log
from ..store import add_observation, upsert_domain
from . import keyword_pattern

LOG_URL = "https://ct.googleapis.com/logs/us1/argon2026h2/"
BATCH = 32  # ask for 32; the log may return fewer


@dataclass(frozen=True)
class CertEntry:
    index: int
    timestamp: datetime
    names: tuple[str, ...]


def _read_u24(buf: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(buf[pos : pos + 3], "big"), pos + 3


def parse_entry(index: int, leaf_input_b64: str, extra_data_b64: str) -> CertEntry | None:
    """Decode one get-entries item. Returns None for entries we cannot read (logged by caller).

    MerkleTreeLeaf: version(1) leaf_type(1) timestamp(8, ms) entry_type(2) then
      entry_type 0 (x509):    cert length(3) + DER certificate
      entry_type 1 (precert): issuer key hash(32) + TBS length(3) + TBS; the full pre-certificate
                              is the first item of extra_data: length(3) + DER
    """
    leaf = base64.b64decode(leaf_input_b64)
    if len(leaf) < 12 or leaf[0] != 0 or leaf[1] != 0:
        return None
    ts_ms = struct.unpack(">Q", leaf[2:10])[0]
    entry_type = struct.unpack(">H", leaf[10:12])[0]
    if entry_type == 0:
        length, pos = _read_u24(leaf, 12)
        der = leaf[pos : pos + length]
    elif entry_type == 1:
        extra = base64.b64decode(extra_data_b64)
        length, pos = _read_u24(extra, 0)
        der = extra[pos : pos + length]
    else:
        return None
    try:
        cert = x509.load_der_x509_certificate(der)
    except ValueError:
        return None
    names: list[str] = []
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        pass
    if not names:
        names = [a.value for a in cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)]
    clean = tuple(sorted({n.lower().removeprefix("*.") for n in names if isinstance(n, str)}))
    return CertEntry(index, datetime.fromtimestamp(ts_ms / 1000, tz=UTC), clean)


def _state(conn, source_id: int, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM collector_state WHERE source_id = %s AND key = %s", (source_id, key)
    ).fetchone()
    return row[0] if row else None


def _set_state(conn, source_id: int, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO collector_state (source_id, key, value) VALUES (%s, %s, %s)
           ON CONFLICT (source_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (source_id, key, value),
    )


def collect_ctlog(conn: psycopg.Connection, fetcher: Fetcher, minutes: float = 5.0, max_lag: int = 20_000) -> None:
    brands, kw = load_brands(), keyword_pattern()
    with CollectorRun(conn, "ctlog") as run:
        size = fetcher.get(LOG_URL + "ct/v1/get-sth").json()["tree_size"]
        saved = _state(conn, run.source_id, "next_index")
        pos = int(saved) if saved else size - 2_000
        if size - pos > max_lag:  # too far behind to catch up politely: sample from near the head
            skipped = size - max_lag // 2 - pos
            log("ct_jump", skipped=skipped, from_index=pos, to_index=size - max_lag // 2)
            pos = size - max_lag // 2
        deadline = time.monotonic() + minutes * 60
        unreadable = 0
        while pos < size and time.monotonic() < deadline:
            end = min(pos + BATCH, size) - 1
            entries = fetcher.get(LOG_URL + "ct/v1/get-entries", params={"start": pos, "end": end}).json()["entries"]
            if not entries:
                break
            for i, e in enumerate(entries):
                entry = parse_entry(pos + i, e["leaf_input"], e["extra_data"])
                if entry is None:
                    unreadable += 1
                    continue
                run.seen += 1
                for name in entry.names:
                    if not kw.search(name):
                        continue
                    dom_id = upsert_domain(conn, name, brands, entry.timestamp)
                    if add_observation(
                        conn,
                        source_id=run.source_id,
                        run_id=run.id,
                        source_ref=f"{entry.index}:{name}",
                        domain_id=dom_id,
                        source_time=entry.timestamp,
                        raw={"log_index": entry.index, "all_names": list(entry.names)[:50]},
                    ):
                        run.new += 1
            pos += len(entries)
            _set_state(conn, run.source_id, "next_index", str(pos))
            conn.commit()
        if unreadable:
            run.partial(f"{unreadable} entries could not be decoded")
        log("ct_progress", log_size=size, next_index=pos, behind=size - pos)
