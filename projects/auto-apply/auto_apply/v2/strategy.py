"""Score each application strategy by its outcomes and split the next run's applications.

A **strategy arm** is one combination of choices the job agent makes: which roles it targets, how the
resume is built, where jobs come from. Each tracker row the agent sends carries its arm in Notes as
`[arm:<id>]`; the arms themselves are defined in `runs/strategies.json`:

  {"arms": [{"id": "A1", "status": "active", "hypothesis": "...", "changes": "..."}, ...]}

The success measure is a **positive outcome**: a person or a next step answers (Interview Scheduled, Offer, or
an ASSESSMENT / RECRUITER_MESSAGE / INTERVIEW email stamped into Notes). Applications with no answer after
`silent_days` count as failures, like rejections; younger ones are pending and do not count yet.

Callbacks are rare, so arms are compared with a Beta(1, 1) prior: an arm with 0 of 3 is not yet known to be
worse than one with 0 of 30. The next run's slots are split by **Thompson sampling**: draw a plausible success
rate for every active arm from its Beta posterior, give the slot to the highest draw, repeat. Arms that look good
get most slots; arms with little data still get some, so they can prove themselves.

python -m auto_apply.v2.strategy runs/v2/tracker.json runs/strategies.json --slots 8 --today 2026-11-02
"""

from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import date

ARM = re.compile(r"\[arm:([A-Za-z0-9_-]+)\]")
POSITIVE_STATUS = {"Interview Scheduled", "Offer"}
POSITIVE_NOTE = re.compile(r"\b(INTERVIEW|ASSESSMENT|RECRUITER_MESSAGE|OFFER)\b")
SENT_STATUS = {"Applied", "Waiting", "Interview Scheduled", "Offer", "Rejected"}


@dataclass
class ArmStats:
    arm: str
    sent: int = 0
    positive: int = 0
    rejected: int = 0
    silent: int = 0
    pending: int = 0

    @property
    def decided(self) -> int:
        return self.positive + self.rejected + self.silent

    @property
    def mean(self) -> float:
        """Posterior mean success rate under a Beta(1, 1) prior."""
        return (self.positive + 1) / (self.decided + 2)


def _row_date(row: dict) -> date | None:
    raw = row.get("date:Date:start") or row.get("Date") or ""
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _status(row: dict) -> str:
    s = row.get("Status") or ""
    if isinstance(s, list):
        s = s[0] if s else ""
    if isinstance(s, str) and s.startswith("["):
        try:
            v = json.loads(s)
            s = v[0] if v else ""
        except ValueError:
            pass
    return s


def tally(rows: list[dict], today: date, silent_days: int = 21) -> dict[str, ArmStats]:
    stats: dict[str, ArmStats] = {}
    for row in rows:
        notes = row.get("Notes") or ""
        m = ARM.search(notes.replace("\\[", "[").replace("\\]", "]"))
        status = _status(row)
        if not m or status not in SENT_STATUS:
            continue
        s = stats.setdefault(m.group(1), ArmStats(m.group(1)))
        s.sent += 1
        if status in POSITIVE_STATUS or POSITIVE_NOTE.search(notes):
            s.positive += 1
        elif status == "Rejected":
            s.rejected += 1
        else:
            d = _row_date(row)
            if d and (today - d).days >= silent_days:
                s.silent += 1
            else:
                s.pending += 1
    return stats


def allocate(stats: dict[str, ArmStats], active: list[str], slots: int, seed: int = 0) -> dict[str, int]:
    """Thompson sampling over the active arms; arms with no data start at Beta(1, 1)."""
    rng = random.Random(seed)
    out = {a: 0 for a in active}
    for _ in range(slots):
        draws = {}
        for a in active:
            s = stats.get(a, ArmStats(a))
            draws[a] = rng.betavariate(s.positive + 1, s.decided - s.positive + 1)
        out[max(draws, key=draws.get)] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tracker")
    ap.add_argument("strategies")
    ap.add_argument("--slots", type=int, default=8)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--silent-days", type=int, default=21)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    rows = json.load(open(a.tracker, encoding="utf-8"))
    arms = json.load(open(a.strategies, encoding="utf-8"))["arms"]
    active = [x["id"] for x in arms if x.get("status", "active") == "active"]
    stats = tally(rows, date.fromisoformat(a.today), a.silent_days)
    plan = allocate(stats, active, a.slots, a.seed)
    print(json.dumps({
        "arms": [dict(asdict(stats.get(x["id"], ArmStats(x["id"]))), status=x.get("status", "active"),
                      mean=round(stats.get(x["id"], ArmStats(x["id"])).mean, 3)) for x in arms],
        "untagged_note": "rows without [arm:...] are not counted",
        "next_run_slots": plan,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
