"""Generator A: "naive" synthetic delivery-scam data, built only from assumptions.

Written and frozen BEFORE any real scam data was collected or inspected. It encodes what we
*assume* delivery-scam domains and texts look like, so the experiment can later measure how
far those assumptions are from reality. Do not edit it: tests compare its output against the
checksums in FREEZE.md, and any change fails them. Improvements belong in generator B.

    python -m scamwatch synth-a        # writes data/synthetic/generator_a_*.csv
"""

from __future__ import annotations

import csv
import random
import string
from pathlib import Path

SEED = 20261101
N_DOMAINS = 5000
N_TEXTS = 1000
SCAM_SHARE = 0.40  # assumed: most keyword-matching domains in the wild are legitimate noise

BRAND_KEYWORD = {"FedEx": "fedex", "UPS": "ups", "USPS": "usps", "DHL": "dhl"}
OFFICIAL = {"FedEx": "fedex.com", "UPS": "ups.com", "USPS": "usps.com", "DHL": "dhl.com"}

SERVICE_WORDS = [
    "track",
    "tracking",
    "delivery",
    "redelivery",
    "parcel",
    "package",
    "shipping",
    "customs",
    "fee",
    "pay",
    "payment",
    "reschedule",
    "address",
    "update",
    "support",
    "help",
    "care",
    "notice",
    "hold",
    "express",
]

# assumed ending mix: .com about 30%, the rest cheap endings
TLDS = (
    ["com"] * 30
    + ["top"] * 12
    + ["xyz"] * 10
    + ["info"] * 8
    + ["online"] * 8
    + ["site"] * 8
    + ["icu"] * 6
    + ["shop"] * 6
    + ["live"] * 6
    + ["cc"] * 6
)

# assumed shares of the scam patterns (spec A.2)
SCAM_PATTERNS = [
    ("brand_service", 0.30),
    ("service_brand", 0.15),
    ("misspelled_brand", 0.15),
    ("brand_subdomain", 0.15),
    ("lookalike_chars", 0.10),
    ("brand_numbers", 0.10),
    ("random_with_brand_subdomain", 0.05),
]
LEGIT_PATTERNS = [("innocent_word", 0.45), ("brand_own_subdomain", 0.25), ("legit_use_of_name", 0.30)]

INNOCENT_UPS_WORDS = [
    "startups",
    "groups",
    "backups",
    "pickups",
    "cups",
    "setups",
    "popups",
    "lineups",
    "makeups",
    "checkups",
    "mashups",
    "roundups",
    "cleanups",
    "warmups",
    "meetups",
]
GENERIC_WORDS = [
    "hub",
    "school",
    "forum",
    "guide",
    "store",
    "world",
    "daily",
    "news",
    "club",
    "lab",
    "pro",
    "central",
    "online",
    "zone",
    "co",
    "media",
    "network",
    "academy",
    "studio",
    "works",
]
OFFICIAL_SUBDOMAINS = [
    "www",
    "tools",
    "tracking",
    "reg",
    "faq",
    "apps",
    "careers",
    "investors",
    "news",
    "developer",
    "local",
    "m",
    "help",
    "shipping",
]
LEGIT_USES = {
    "FedEx": ["fedexcup", "fedexforum", "fedexfield", "fedexstadium", "fedexmemphisjobs", "fedexretirees"],
    "UPS": ["theupsstore", "upsstorefranchise", "upsretirees", "upsfreightjobs", "upscareers"],
    "USPS": ["uspsoig", "uspis", "uspsretirees", "uspsunion", "uspspostalhistory"],
    "DHL": ["dhlparcel", "dhlexpressjobs", "dhlsupplychainjobs", "dhlretirees", "dhlhubleipzig"],
}
LEGIT_TLDS = ["com"] * 60 + ["org"] * 15 + ["net"] * 10 + ["co.uk"] * 5 + ["io"] * 5 + ["de"] * 5

QWERTY_NEIGHBOURS = {
    "a": "qs",
    "b": "vn",
    "c": "xv",
    "d": "sf",
    "e": "wr",
    "f": "dg",
    "g": "fh",
    "h": "gj",
    "i": "uo",
    "j": "hk",
    "k": "jl",
    "l": "k",
    "m": "n",
    "n": "bm",
    "o": "ip",
    "p": "o",
    "q": "w",
    "r": "et",
    "s": "ad",
    "t": "ry",
    "u": "yi",
    "v": "cb",
    "w": "qe",
    "x": "zc",
    "y": "tu",
    "z": "x",
}
DIGIT_LOOKALIKES = {"o": "0", "l": "1", "i": "1", "e": "3", "s": "5", "a": "4"}
CYRILLIC_LOOKALIKES = {"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х"}


def _pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    names, weights = zip(*weighted, strict=True)
    return rng.choices(names, weights=weights)[0]


def _misspell(rng: random.Random, word: str) -> str:
    i = rng.randrange(len(word))
    op = rng.choice(["add", "drop", "swap", "neighbour"])
    if op == "add":
        return word[:i] + word[i] + word[i:]
    if op == "drop" and len(word) > 3:
        return word[:i] + word[i + 1 :]
    if op == "swap" and i < len(word) - 1:
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    near = QWERTY_NEIGHBOURS.get(word[i], word[i])
    return word[:i] + rng.choice(near) + word[i + 1 :]


def _lookalike(rng: random.Random, word: str) -> str:
    if rng.random() < 0.7:  # digits that look like letters
        idx = [i for i, ch in enumerate(word) if ch in DIGIT_LOOKALIKES]
        if idx:
            i = rng.choice(idx)
            return word[:i] + DIGIT_LOOKALIKES[word[i]] + word[i + 1 :]
    idx = [i for i, ch in enumerate(word) if ch in CYRILLIC_LOOKALIKES]
    if not idx:
        return word + rng.choice("xz")
    i = rng.choice(idx)
    return (word[:i] + CYRILLIC_LOOKALIKES[word[i]] + word[i + 1 :]).encode("idna").decode()  # xn--...


def _join(rng: random.Random, parts: list[str]) -> str:
    return rng.choice(["-", "", "-"]).join(parts)


def scam_domain(rng: random.Random, brand: str) -> tuple[str, str]:
    kw = BRAND_KEYWORD[brand]
    tld = rng.choice(TLDS)
    svc = rng.sample(SERVICE_WORDS, rng.choice([1, 1, 2]))
    pattern = _pick(rng, SCAM_PATTERNS)
    if pattern == "brand_service":
        name = _join(rng, [kw, *svc])
    elif pattern == "service_brand":
        name = _join(rng, [*svc, kw]) if rng.random() < 0.5 else _join(rng, [svc[0], kw, *svc[1:]])
    elif pattern == "misspelled_brand":
        name = _join(rng, [_misspell(rng, kw), *svc]) if rng.random() < 0.7 else _misspell(rng, kw)
    elif pattern == "brand_subdomain":
        host = _join(rng, svc + [rng.choice(SERVICE_WORDS)])
        if rng.random() < 0.5:
            return f"{kw}.com-{host}.{tld}", pattern  # looks like fedex.com on a phone
        return f"{kw}.{host}.{tld}", pattern
    elif pattern == "lookalike_chars":
        name = _join(rng, [_lookalike(rng, kw), *svc])
    elif pattern == "brand_numbers":
        num = rng.choice([str(rng.randint(2024, 2027)), str(rng.randint(1, 999)), str(rng.randint(10, 99))])
        name = _join(rng, [kw, *svc, num])
    else:  # random_with_brand_subdomain
        junk = "".join(rng.choices(string.ascii_lowercase + string.digits, k=rng.randint(5, 9)))
        return f"{kw}.{junk}.{tld}", pattern
    return f"{name}.{tld}", pattern


def legit_domain(rng: random.Random, brand: str) -> tuple[str, str]:
    pattern = _pick(rng, LEGIT_PATTERNS)
    if pattern == "innocent_word":
        word = rng.choice(INNOCENT_UPS_WORDS)  # assumed: almost all innocent matches are on "ups"
        name = _join(rng, [word, rng.choice(GENERIC_WORDS)]) if rng.random() < 0.8 else word
        return f"{name}.{rng.choice(LEGIT_TLDS)}", pattern
    if pattern == "brand_own_subdomain":
        return f"{rng.choice(OFFICIAL_SUBDOMAINS)}.{OFFICIAL[brand]}", pattern
    base = rng.choice(LEGIT_USES[brand])
    if rng.random() < 0.3:
        base = _join(rng, [base, rng.choice(GENERIC_WORDS)])
    return f"{base}.{rng.choice(LEGIT_TLDS)}", pattern


SCAM_TEXTS = [
    "{brand}: Your package is on hold due to an incomplete address. Update within {hours}h: {link}",
    "{brand} Notice: we could not deliver your parcel. A ${fee} redelivery fee is required: {link}",
    "Final notice from {brand}: your shipment will be returned unless customs duty ${fee} is paid today {link}",
    "{brand}: your package #{track} is waiting. Confirm your details to schedule delivery: {link}",
    "Dear customer, {brand} attempted delivery. Reschedule now or the item is returned: {link}",
]
GENUINE_TEXTS = [
    "{brand}: Your package {track} is scheduled for delivery today between {start} and {end}. Track at {official}",
    "{brand}: Your package {track} was delivered at {start}. Details at {official}",
    "{brand}: Delivery exception for {track}. No action needed, we will try again tomorrow. {official}",
    "Your {brand} shipment {track} is out for delivery. Manage delivery at {official}",
]


def _texts(rng: random.Random, scam_domains: dict[str, list[str]]) -> list[dict]:
    rows = []
    for i in range(N_TEXTS):
        brand = rng.choice(list(BRAND_KEYWORD))
        track = "".join(rng.choices(string.digits, k=12))
        if i % 2 == 0:
            text = rng.choice(SCAM_TEXTS).format(
                brand=brand,
                hours=rng.choice([12, 24, 48]),
                fee=f"{rng.uniform(0.30, 3.00):.2f}",
                track=track,
                link="https://" + rng.choice(scam_domains[brand]) + "/" + rng.choice(["pay", "verify", "t"]),
            )
            rows.append({"text": text, "label": "scam", "brand": brand, "generator": "A", "seed": SEED})
        else:
            start = rng.randint(8, 14)
            text = rng.choice(GENUINE_TEXTS).format(
                brand=brand,
                track=track,
                start=f"{start}:00",
                end=f"{start + 4}:00",
                official="https://www." + OFFICIAL[brand],
            )
            rows.append({"text": text, "label": "legitimate", "brand": brand, "generator": "A", "seed": SEED})
    return rows


def generate() -> tuple[list[dict], list[dict]]:
    from ..config import load_brands
    from ..store import brand_match

    brands = load_brands()
    rng = random.Random(SEED)
    domains, seen = [], set()
    n_scam = int(N_DOMAINS * SCAM_SHARE)
    while len(domains) < N_DOMAINS:
        brand = rng.choice(list(BRAND_KEYWORD))
        is_scam = sum(d["label"] == "scam" for d in domains) < n_scam
        domain, pattern = scam_domain(rng, brand) if is_scam else legit_domain(rng, brand)
        # a typo of one brand can be another brand's real site ("usps" minus an "s" is ups.com)
        if domain in seen or (is_scam and brand_match(domain, brands)[1]):
            continue
        seen.add(domain)
        domains.append(
            {
                "domain": domain,
                "label": "scam" if is_scam else "legitimate",
                "brand": brand,
                "pattern": pattern,
                "generator": "A",
                "seed": SEED,
            }
        )
    rng.shuffle(domains)
    by_brand = {b: [d["domain"] for d in domains if d["label"] == "scam" and d["brand"] == b] for b in BRAND_KEYWORD}
    texts = _texts(rng, by_brand)
    return domains, texts


def write(out_dir: Path) -> list[Path]:
    domains, texts = generate()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, rows in (("generator_a_domains.csv", domains), ("generator_a_texts.csv", texts)):
        path = out_dir / name
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        paths.append(path)
    return paths
