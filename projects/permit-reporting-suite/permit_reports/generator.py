"""Seeded synthetic data: 40,000 permits + 30,000 fees + 30,000 inspections = 100,000 records.

Nothing here is real. Distributions are chosen so every report has something to show: processing
times scatter around each permit type's target, about 1 in 8 fees is unpaid, some are partly paid
or voided, a few valuations are NULL, and inspections fail often enough to matter.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .params import DISTRICTS

START = date(2023, 1, 1)
AS_OF = date(2025, 12, 31)          # the "today" of the synthetic system
N_PERMITS, N_FEES, N_INSPECTIONS = 40_000, 30_000, 30_000

DISTRICT_ROWS = [
    (i + 1, code, name) for i, (code, name) in enumerate(zip(DISTRICTS, (
        "Central", "North", "South", "East", "West", "Harbor", "University", "Industrial")))
]
# code, name, target days, valuation range, weight
PERMIT_TYPES = [
    ("RESNEW", "Residential New", 45, (180_000, 650_000), 8),
    ("RESALT", "Residential Alteration", 20, (8_000, 120_000), 22),
    ("COMNEW", "Commercial New", 90, (600_000, 6_000_000), 3),
    ("COMALT", "Commercial Alteration", 45, (25_000, 900_000), 9),
    ("ELEC", "Electrical", 7, (500, 40_000), 18),
    ("PLMB", "Plumbing", 7, (500, 30_000), 14),
    ("MECH", "Mechanical", 10, (1_500, 60_000), 10),
    ("DEMO", "Demolition", 14, (5_000, 150_000), 3),
    ("ROOF", "Re-roof", 5, (6_000, 45_000), 10),
    ("SIGN", "Sign", 15, (800, 25_000), 3),
]
FEE_TYPES = [("PLN", "Plan Review"), ("BLD", "Building Permit"), ("ELE", "Electrical"),
             ("PLB", "Plumbing"), ("MEC", "Mechanical"), ("IMP", "Impact"), ("REI", "Reinspection")]
FEE_WEIGHTS = [20, 30, 14, 12, 10, 6, 8]
INSPECTION_TYPES = [("FTG", "Footing"), ("FRM", "Framing"), ("ELR", "Electrical Rough"),
                    ("PLR", "Plumbing Rough"), ("MEC", "Mechanical"), ("INS", "Insulation"),
                    ("FNL", "Final")]
SURNAMES = ["Rivera", "Chen", "Okafor", "Nguyen", "Patel", "Kowalski", "Haddad", "Silva",
            "Moreau", "Tanaka", "Jensen", "Alvarez", "Mensah", "Novak", "Brennan", "Sato",
            "Khan", "Duarte", "Lindqvist", "Abara", "Ferreira", "Iyer", "Mazur", "Quinn"]

CENT = Decimal("0.01")


def _money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def generate(seed: int = 2026) -> dict[str, list[tuple]]:
    rng = random.Random(seed)
    span = (AS_OF - START).days

    inspectors = []
    for i, name in enumerate(SURNAMES):
        inspectors.append((i + 1, f"{chr(65 + (i * 7) % 26)}. {name}", (i % len(DISTRICTS)) + 1))
    by_home: dict[int, list[int]] = {}
    for iid, _, home in inspectors:
        by_home.setdefault(home, []).append(iid)

    type_weights = [t[4] for t in PERMIT_TYPES]
    permits = []
    for pid in range(1, N_PERMITS + 1):
        t_idx = rng.choices(range(len(PERMIT_TYPES)), weights=type_weights)[0]
        code, _, target, (vlo, vhi), _ = PERMIT_TYPES[t_idx]
        district_id = rng.choices(range(1, 9), weights=[18, 14, 14, 12, 12, 8, 10, 12])[0]
        applied = START + timedelta(days=rng.randrange(span + 1))
        valuation = None if rng.random() < 0.005 else _money(rng.uniform(vlo, vhi))

        issued = finaled = None
        if rng.random() < 0.04:
            status = "Withdrawn"
        else:
            days = max(0, round(rng.lognormvariate(0, 0.55) * target * 0.85))
            if applied + timedelta(days=days) <= AS_OF:
                issued = applied + timedelta(days=days)
                fin = issued + timedelta(days=rng.randint(20, 300))
                if fin <= AS_OF and rng.random() < 0.85:
                    finaled, status = fin, "Finaled"
                elif (AS_OF - issued).days > 365:
                    status = "Expired"
                else:
                    status = "Issued"
            else:
                status = "Applied" if (AS_OF - applied).days < 10 else "In Review"
        permits.append((pid, f"BP{applied.year % 100:02d}-{pid:06d}", t_idx + 1, district_id, status,
                        applied, issued, finaled, valuation))

    fee_eligible = [p for p in permits if p[4] != "Withdrawn"]
    fees = []
    while len(fees) < N_FEES:
        p = rng.choice(fee_eligible)
        assessed = p[5] + timedelta(days=rng.randint(0, 14))
        if assessed > AS_OF:
            continue
        ft = rng.choices(range(len(FEE_TYPES)), weights=FEE_WEIGHTS)[0]
        base = float(p[8]) if p[8] is not None else 20_000.0
        if FEE_TYPES[ft][0] == "BLD":
            amount = max(75.0, base * 0.008)
        elif FEE_TYPES[ft][0] == "PLN":
            amount = max(50.0, base * 0.0045)
        elif FEE_TYPES[ft][0] == "IMP":
            amount = rng.uniform(1_500, 12_000)
        elif FEE_TYPES[ft][0] == "REI":
            amount = 95.0
        else:
            amount = rng.uniform(60, 650)
        amount = _money(amount)
        paid, paid_date = Decimal("0.00"), None
        r = rng.random()
        if r < 0.88:
            pd_ = assessed + timedelta(days=rng.randint(0, 75))
            if pd_ <= AS_OF:
                paid = amount if r < 0.82 else _money(float(amount) * rng.uniform(0.4, 0.9))
                paid_date = pd_
        voided = 1 if rng.random() < 0.02 else 0
        fees.append((len(fees) + 1, p[0], ft + 1, assessed, assessed + timedelta(days=30),
                     amount, paid, paid_date, voided))

    insp_eligible = [p for p in permits if p[6] is not None]
    inspections = []
    while len(inspections) < N_INSPECTIONS:
        p = rng.choice(insp_eligible)
        sched = p[6] + timedelta(days=rng.randint(2, 200))
        if sched > AS_OF + timedelta(days=14):
            continue
        if sched > AS_OF:
            result = "Pending"
        else:
            result = rng.choices(["Pass", "Fail", "Partial", "Canceled", "Pending"],
                                 weights=[63, 22, 6, 7, 2])[0]
            if result == "Pending" and (AS_OF - sched).days > 14:
                result = "Pass"
        completed = sched + timedelta(days=rng.randint(0, 1)) if result in ("Pass", "Fail", "Partial") else None
        if completed and completed > AS_OF:
            completed = sched
        pool = by_home[p[3]] if rng.random() < 0.8 else [i[0] for i in inspectors]
        inspections.append((len(inspections) + 1, p[0], rng.randrange(len(INSPECTION_TYPES)) + 1,
                            rng.choice(pool), sched, completed, result))

    return {
        "District": DISTRICT_ROWS,
        "PermitType": [(i + 1, t[0], t[1], t[2]) for i, t in enumerate(PERMIT_TYPES)],
        "FeeType": [(i + 1, c, n) for i, (c, n) in enumerate(FEE_TYPES)],
        "InspectionType": [(i + 1, c, n) for i, (c, n) in enumerate(INSPECTION_TYPES)],
        "Inspector": inspectors,
        "Permit": permits,
        "Fee": fees,
        "Inspection": inspections,
    }


LOAD_ORDER = ["District", "PermitType", "FeeType", "InspectionType", "Inspector",
              "Permit", "Fee", "Inspection"]


def load(conn, data: dict[str, list[tuple]], batch: int = 1000) -> dict[str, int]:
    """Insert with multi-row parameterized INSERTs (portable; no bcp or file share needed)."""
    cur = conn.cursor()
    for table in reversed(LOAD_ORDER):
        cur.execute(f"DELETE FROM dbo.{table}")
    counts = {}
    for table in LOAD_ORDER:
        rows = data[table]
        width = len(rows[0])
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            values = ",".join("(" + ",".join(["%s"] * width) + ")" for _ in chunk)
            flat = [v for row in chunk for v in row]
            cur.execute(f"INSERT INTO dbo.{table} VALUES {values}", tuple(flat))
        counts[table] = len(rows)
    conn.commit()
    return counts


def write_csv(data: dict[str, list[tuple]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in data.items():
        with open(out_dir / f"{table}.csv", "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
