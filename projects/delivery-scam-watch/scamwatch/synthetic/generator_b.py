"""Generator B: synthetic data calibrated to REAL training data.

Generator A guessed what scam domains look like. Generator B learns it: it takes real training
domains (never test domains), breaks each into a template, and fills the variable parts with
fresh random values of the same kind, so it keeps the real structure (which brand, which trick,
which ending, which hosting platform) without copying any real domain.

    usps.com-trackdqf.top  ->  template  usps.com-track{3 letters}.top  ->  usps.com-trackxkr.top
    wusps.xyz              ->  template  {1 letter}usps.xyz            ->  qusps.xyz
"""

from __future__ import annotations

import random
import re
import string

TOKEN = re.compile(r"[a-z]+|[0-9]+|[^a-z0-9]+")
KEEP_WORDS = {
    "fedex",
    "usps",
    "ups",
    "dhl",
    "com",
    "track",
    "tracking",
    "delivery",
    "parcel",
    "package",
    "post",
    "postal",
    "pay",
    "fee",
    "help",
    "support",
    "service",
    "express",
    "update",
    "secure",
    "login",
    "www",
}


def _mutate_token(rng: random.Random, tok: str, keep: set[str]) -> str:
    if not tok.isalnum():
        return tok  # dots and hyphens keep the structure
    if tok.isdigit():
        return "".join(rng.choices(string.digits, k=len(tok)))
    for word in sorted(keep, key=len, reverse=True):  # keep brand and service words, randomise the rest
        if word in tok:
            i = tok.index(word)
            left = "".join(rng.choices(string.ascii_lowercase, k=i))
            right = "".join(rng.choices(string.ascii_lowercase, k=len(tok) - i - len(word)))
            return left + word + right
    return "".join(rng.choices(string.ascii_lowercase, k=len(tok)))


def mutate(rng: random.Random, domain: str, suffix: str, keep: set[str] | None = None) -> str:
    """Re-fill the variable parts of `domain`; the public suffix (ending) is kept as is."""
    keep = keep or KEEP_WORDS
    head = domain[: -len(suffix) - 1] if suffix and domain.endswith("." + suffix) else domain
    new = "".join(_mutate_token(rng, t, keep) for t in TOKEN.findall(head))
    return f"{new}.{suffix}" if suffix else new


def generate(train: list[tuple[str, str, str]], n: int, seed: int = 20261102) -> list[tuple[str, str]]:
    """train: (domain, suffix, label) rows from the real TRAINING split. Returns (domain, label)."""
    rng = random.Random(seed)
    seen = {d for d, _, _ in train}
    out: list[tuple[str, str]] = []
    tries = 0
    while len(out) < n and tries < n * 20:
        tries += 1
        domain, suffix, label = rng.choice(train)
        new = mutate(rng, domain, suffix)
        if new not in seen:
            seen.add(new)
            out.append((new, label))
    return out
