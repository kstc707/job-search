"""Pick which jobs get a target profile, and tally callbacks for tagged tracker rows.

Every submitted resume is built from Sai's real record (arm A). For about half the jobs,
chosen by `assign` from a hash of the normalized apply URL (random with respect to the job,
and stable across reruns), the seeker also builds a target profile (arm B): the resume the
posting describes, stamped "not for submission", with a plan for closing each gap. It is
never sent; it exists so Sai can see what postings want that his record does not show yet.

`tally` counts outcomes for tracker rows whose Notes carry `[seeker ... arm=<A|B>]`, using
the stamps the v2 sync adds ("Evidence: <date> <CATEGORY>: <subject>").
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from math import comb

from auto_apply.ledger import normalize_url

ARMS = ("A", "B")
_TAG = re.compile(r"\[seeker\b[^\]]*?\barm=([AB])\b", re.I)
_PERSON = re.compile(r"\b(INTERVIEW|RECRUITER_MESSAGE|OFFER)\b")
_ASSESS = re.compile(r"\bASSESSMENT\b")
SILENT_DAYS = 21


def assign(url: str, salt: str = "seeker-2026-10") -> str:
    digest = hashlib.sha256(f"{salt}|{normalize_url(url)}".encode()).digest()
    return ARMS[digest[0] % 2]


def outcome(row: dict, today: date) -> str:
    """callback (a person: interview, recruiter, offer) > assessment > rejected > silent > pending."""
    notes, status = row.get("Notes") or "", row.get("Status") or ""
    if status in ("Interview Scheduled", "Offer") or _PERSON.search(notes):
        return "callback"
    if _ASSESS.search(notes):
        return "assessment"
    if status == "Rejected":
        return "rejected"
    try:
        sent = date.fromisoformat((row.get("date:Date:start") or "")[:10])
    except ValueError:
        return "pending"
    return "silent" if (today - sent).days >= SILENT_DAYS else "pending"


@dataclass
class ArmStats:
    sent: int = 0
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(
        ("callback", "assessment", "rejected", "silent", "pending"), 0))

    @property
    def callback_rate(self) -> float:
        return self.counts["callback"] / self.sent if self.sent else 0.0


def tally(rows: list[dict], today: date) -> dict[str, ArmStats]:
    stats = {a: ArmStats() for a in ARMS}
    for row in rows:
        m = _TAG.search(row.get("Notes") or "")
        if not m:
            continue
        s = stats[m.group(1).upper()]
        s.sent += 1
        s.counts[outcome(row, today)] += 1
    return stats


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Fisher's exact test for [[a, b], [c, d]] (callbacks / no callbacks per arm)."""
    n, row1, col1 = a + b + c + d, a + b, a + c
    if n == 0:
        return 1.0

    def p(x: int) -> float:
        return comb(col1, x) * comb(n - col1, row1 - x) / comb(n, row1)

    observed = p(a)
    lo, hi = max(0, row1 + col1 - n), min(row1, col1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= observed * (1 + 1e-9)))


def report(stats: dict[str, ArmStats]) -> str:
    lines = ["arm  sent  callback  assessment  rejected  silent  pending  callback rate"]
    for arm in ARMS:
        s, c = stats[arm], stats[arm].counts
        lines.append(f"{arm:4} {s.sent:5} {c['callback']:9} {c['assessment']:11} {c['rejected']:9} "
                     f"{c['silent']:7} {c['pending']:8}  {s.callback_rate:6.1%}")
    a, b = stats["A"], stats["B"]
    pval = fisher_two_sided(a.counts["callback"], a.sent - a.counts["callback"],
                            b.counts["callback"], b.sent - b.counts["callback"])
    lines.append(f"Fisher exact p (callback A vs B) = {pval:.3f}"
                 + ("  (fewer than 30 per arm: read as a hint, not a result)" if min(a.sent, b.sent) < 30 else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.arms")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("assign", help="arm for a job (from its apply URL)")
    s.add_argument("url")
    t = sub.add_parser("tally", help="callback rates per arm from tracker rows")
    t.add_argument("--tracker", required=True)
    t.add_argument("--today", help="YYYY-MM-DD (default: today)")
    a = p.parse_args(argv)
    if a.cmd == "assign":
        print(assign(a.url))
        return 0
    today = date.fromisoformat(a.today) if a.today else date.today()
    print(report(tally(json.load(open(a.tracker)), today)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
