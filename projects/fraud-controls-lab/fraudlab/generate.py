"""Seeded synthetic parcel-carrier data with planted fraud schemes.

Nothing here is real company data. Every scheme below is planted on purpose so the
detection pipeline can be scored against a known answer (the `truth` table), the same
way a fraud team scores a new control against confirmed cases.

Planted schemes
  ATO    account takeover / theft of service: a real customer's account starts shipping
         from a new device to new addresses, mostly express, often to "drop" addresses,
         billed to the victim.
  UNDER  weight under-declaration (revenue leakage): the shipper declares well below the
         weight the hub scale measures, so the carrier under-bills.
  RING   claims-fraud ring: a few linked accounts share devices and recipient addresses and
         file "not received" claims with near-identical stories.
Plus ordinary noise that triggers naive rules: a November-December peak, honest new
devices, honest weighing errors and genuine claims.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MONTHS = 12
START = pd.Timestamp("2025-01-01")
RATE_PER_LB = 1.10            # billed dollars per declared pound, on top of the base charge
BASE_CHARGE = {"ground": 9.0, "express": 28.0, "overnight": 55.0}

LEGIT_CLAIM_TEMPLATES = [
    "box arrived {dmg} and the {item} inside was {state}",
    "package shows delivered but {who} cannot find it at the {place}",
    "tracking stopped updating {n} days ago and {who} is still waiting on the {item}",
    "carton was {dmg} on arrival, {item} {state}, photos attached",
    "delivered to the wrong {place}, a neighbour returned it {dmg}",
    "{item} missing from the box, outer packaging {dmg}",
    "{who} signed for it but the {item} was {state} when opened",
    "shipment came {n} days late and the {item} was {state}",
    "label was smudged and the parcel went to the {place} instead",
    "{who} says the driver left it at the {place} in the rain, {item} {state}",
    "only one of two boxes arrived, the one with the {item} is missing",
    "the {item} rattled when we picked it up, {state} inside, box {dmg}",
]
LEGIT_EXTRAS = [
    "we have shipped with you for years and this is the first problem",
    "the customer wants a replacement before friday",
    "invoice and packing slip attached",
    "this was a gift so the recipient is upset",
    "we packed it with foam and double boxing",
    "the driver note said left at side door",
    "please advise on next steps for the claim",
    "we can provide the original receipt",
    "the recipient checked with the building manager",
    "photos show the corner of the box crushed",
]
LEGIT_URGENT = ["please refund asap", "this is urgent for our customer", "high value item please expedite"]
RING_CLAIM_TEMPLATES = [
    "package never received high value {item} please refund full declared amount urgently",
    "never received my {item} package high value refund full declared amount asap",
]
WORDS = {
    "dmg": ["crushed", "torn", "wet", "dented", "open", "intact", "soaked", "ripped", "taped over", "split"],
    "item": ["laptop", "printer", "parts", "documents", "phone", "samples", "tools", "camera", "monitor",
             "medication", "artwork", "clothing", "speaker", "tablet", "watch", "books"],
    "state": ["broken", "cracked", "fine", "scratched", "unusable", "missing pieces", "bent", "water damaged",
              "shattered", "not working"],
    "who": ["the recipient", "our customer", "the office manager", "reception", "my client", "the buyer",
            "the warehouse team", "my mother"],
    "place": ["front desk", "loading dock", "mailroom", "porch", "suite", "back door", "garage",
              "apartment lobby", "parcel locker"],
    "n": ["3", "4", "5", "6", "8", "9", "11"],
}


def _legit_narrative(rng: np.random.Generator) -> str:
    text = _fill(str(rng.choice(LEGIT_CLAIM_TEMPLATES)), rng)
    if rng.random() < 0.7:
        text += ". " + str(rng.choice(LEGIT_EXTRAS))
    if rng.random() < 0.6:
        text += f". order {rng.integers(10**5, 10**6)}"
    if rng.random() < 0.08:
        text += ". " + str(rng.choice(LEGIT_URGENT))
    return text


@dataclass
class Dataset:
    accounts: pd.DataFrame
    shipments: pd.DataFrame
    claims: pd.DataFrame
    truth: pd.DataFrame  # one row per (account_id, month, scheme): the answer key


def _fill(template: str, rng: np.random.Generator) -> str:
    out = template
    for key, options in WORDS.items():
        while "{" + key + "}" in out:
            out = out.replace("{" + key + "}", str(rng.choice(options)), 1)
    return out


def generate(n_accounts: int = 3000, seed: int = 7) -> Dataset:
    rng = np.random.default_rng(seed)

    # ---- accounts -----------------------------------------------------------------
    acc = pd.DataFrame({
        "account_id": [f"A{i:05d}" for i in range(n_accounts)],
        "segment": rng.choice(["small_business", "mid_market", "individual"], n_accounts, p=[0.5, 0.2, 0.3]),
        "region": rng.choice(["NE", "SE", "MW", "SW", "W"], n_accounts),
        "opened_months_ago": rng.integers(1, 120, n_accounts),
    })
    base_volume = np.where(acc.segment == "mid_market", rng.gamma(4, 8, n_accounts),
                           np.where(acc.segment == "small_business", rng.gamma(3, 3, n_accounts),
                                    rng.gamma(1.5, 1.5, n_accounts)))
    acc["home_device"] = [f"D{i:05d}" for i in range(n_accounts)]
    n_dest = rng.integers(3, 40, n_accounts)
    dest_pool = {a: [f"R{a[1:]}_{j}" for j in range(k)] for a, k in zip(acc.account_id, n_dest)}

    drop_addresses = [f"DROP{j:02d}" for j in range(15)]
    ids = acc.account_id.to_numpy()
    # scheme sizes scale with the book (60 / 80 / 26 accounts at the default 3,000)
    n_ato, n_under = max(2, round(n_accounts * 0.02)), max(2, round(n_accounts * 0.0267))
    n_ring = max(8, round(n_accounts * 0.0087))
    ato = rng.choice(ids, n_ato, replace=False)
    rest = np.setdiff1d(ids, ato)
    under = rng.choice(rest, n_under, replace=False)
    rest = np.setdiff1d(rest, under)
    ring_members = rng.choice(rest, n_ring, replace=False)
    rings = np.array_split(ring_members, 4)  # 4 rings
    ato_month = {a: int(rng.integers(2, MONTHS)) for a in ato}
    under_start = {a: int(rng.integers(0, 6)) for a in under}
    ring_start = {i: int(rng.integers(3, 9)) for i in range(len(rings))}
    ring_of = {a: i for i, r in enumerate(rings) for a in r}

    truth = []
    ship_rows = []
    claim_rows = []
    sid = 0

    for idx, a in enumerate(ids):
        for m in range(MONTHS):
            season = 1.6 if m >= 10 else 1.0          # Nov-Dec peak: legit spikes
            n = rng.poisson(base_volume[idx] * season)
            frauds = []
            # ---- legitimate shipments (vectorised) ---------------------------------
            if n:
                measured = np.round(rng.lognormal(1.6, 0.7, n), 1)
                honest_err = rng.random(n) < 0.03
                declared = measured * np.where(honest_err, rng.uniform(0.6, 0.9, n), rng.uniform(0.97, 1.03, n))
                tmp = rng.random(n) < 0.04
                devices = np.where(tmp, [f"D_TMP{x}" for x in rng.integers(0, 10**6, n)], acc.home_device[idx])
                dests = rng.choice(dest_pool[a], n)
                services = rng.choice(["ground", "express", "overnight"], n, p=[0.75, 0.2, 0.05])
                days = rng.integers(0, 28, n)
                for j in range(n):
                    ship_rows.append((sid, a, m, int(days[j]), str(services[j]), str(devices[j]), str(dests[j]),
                                      float(measured[j]), float(declared[j]), False, ""))
                    sid += 1
            # ---- UNDER: under-declared weight --------------------------------------
            if a in under and m >= under_start[a]:
                frauds.append("UNDER")
                k = max(3, int(rng.poisson(base_volume[idx] * 0.8)))
                for _ in range(k):
                    measured = float(np.round(rng.lognormal(2.2, 0.5), 1))
                    declared = measured * rng.uniform(0.45, 0.7)
                    ship_rows.append((sid, a, m, int(rng.integers(0, 28)), "ground", acc.home_device[idx],
                                      str(rng.choice(dest_pool[a])), measured, declared, True, "UNDER"))
                    sid += 1
            # ---- ATO: theft of service on a hijacked account ------------------------
            if a in ato and m == ato_month[a]:
                frauds.append("ATO")
                bad_device = f"D_ATO{rng.integers(1e6)}"
                k = int(rng.integers(25, 80))
                day0 = int(rng.integers(0, 18))
                for _ in range(k):
                    dest = str(rng.choice(drop_addresses)) if rng.random() < 0.6 else f"RNEW{rng.integers(1e7)}"
                    measured = float(np.round(rng.lognormal(1.9, 0.5), 1))
                    ship_rows.append((sid, a, m, day0 + int(rng.integers(0, 10)),
                                      rng.choice(["express", "overnight"], p=[0.6, 0.4]), bad_device, dest,
                                      measured, measured, True, "ATO"))
                    sid += 1
            # ---- RING: linked accounts filing claims -------------------------------
            if a in ring_of and m >= ring_start[ring_of[a]]:
                frauds.append("RING")
                r = ring_of[a]
                ring_device = f"D_RING{r}"
                ring_dests = [f"RRING{r}_{j}" for j in range(3)]
                k = int(rng.integers(3, 8))
                for _ in range(k):
                    measured = float(np.round(rng.lognormal(1.5, 0.4), 1))
                    ship_rows.append((sid, a, m, int(rng.integers(0, 28)), "express", ring_device,
                                      str(rng.choice(ring_dests)), measured, measured, True, "RING"))
                    if rng.random() < 0.7:
                        claim_rows.append((sid, a, m, "not_received", float(np.round(rng.uniform(600, 2500), 2)),
                                           _fill(str(rng.choice(RING_CLAIM_TEMPLATES)), rng), True))
                    sid += 1
            for f in frauds:
                truth.append((a, m, f))

    ship = pd.DataFrame(ship_rows, columns=["shipment_id", "account_id", "month", "day", "service", "device_id",
                                            "dest_address", "measured_lb", "declared_lb", "is_fraud", "scheme"])
    ship["declared_lb"] = ship.declared_lb.round(1)
    ship["billed"] = ship.service.map(BASE_CHARGE) + RATE_PER_LB * ship.declared_lb
    ship["lost_revenue"] = np.where(ship.scheme == "UNDER", RATE_PER_LB * (ship.measured_lb - ship.declared_lb), 0.0)

    # ---- genuine claims on about 1.5% of legitimate shipments -------------------------
    legit = ship[~ship.is_fraud]
    pick = legit.sample(frac=0.015, random_state=seed)
    for row in pick.itertuples():
        claim_rows.append((row.shipment_id, row.account_id, row.month,
                           str(rng.choice(["damaged", "not_received", "late"], p=[0.5, 0.35, 0.15])),
                           float(np.round(rng.lognormal(4.2, 0.9), 2)),
                           _legit_narrative(rng), False))
    claims = pd.DataFrame(claim_rows, columns=["shipment_id", "account_id", "month", "claim_type",
                                               "amount", "narrative", "is_fraud"])
    claims.insert(0, "claim_id", [f"C{i:06d}" for i in range(len(claims))])

    truth_df = pd.DataFrame(truth, columns=["account_id", "month", "scheme"])
    return Dataset(acc, ship, claims, truth_df)
