"""Turn a domain name into the signals an analyst would look at.

Only the name itself is used (no page visits), so a domain can be scored the moment its
certificate or registration appears, which is the point of an early-warning monitor.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import pandas as pd

from ..store import split_domain

BRANDS = {"fedex": "FedEx", "usps": "USPS", "dhl": "DHL", "ups": "UPS"}
SERVICE_WORDS = [
    "track",
    "delivery",
    "deliver",
    "parcel",
    "package",
    "pkg",
    "ship",
    "post",
    "postal",
    "customs",
    "fee",
    "pay",
    "payment",
    "reschedule",
    "redeliver",
    "address",
    "update",
    "support",
    "help",
    "care",
    "notice",
    "hold",
    "express",
    "service",
    "verify",
    "secure",
    "login",
    "info",
]
# Free hosting and dynamic-DNS platforms: anyone can get a subdomain in minutes, no registration.
HOSTING = [
    "pages.dev",
    "workers.dev",
    "web.app",
    "firebaseapp.com",
    "appspot.com",
    "vercel.app",
    "netlify.app",
    "github.io",
    "duckdns.org",
    "glitch.me",
    "weebly.com",
    "wixsite.com",
    "blogspot.com",
    "r2.dev",
    "onrender.com",
    "herokuapp.com",
    "repl.co",
    "000webhostapp.com",
    "azurewebsites.net",
    "square.site",
    "godaddysites.com",
    "ngrok-free.app",
    "ngrok.io",
    "webflow.io",
    "framer.app",
    "surge.sh",
    "ddns.net",
    "no-ip.org",
    "my.id",
    "translate.goog",
    "ipfs.io",
    "dweb.link",
]
COMMON_TLDS = {
    "com",
    "org",
    "net",
    "edu",
    "gov",
    "us",
    "co.uk",
    "de",
    "ca",
    "io",
    "info",
    "biz",
    "fr",
    "it",
    "nl",
    "es",
    "au",
    "com.au",
    "in",
    "jp",
}


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def brand_token(fqdn: str) -> str | None:
    """The brand the name refers to as a word of its own, or None.

    'usps-track.top' -> USPS; 'track.ups.example' -> UPS; 'groups.com' -> None ('ups' is inside
    a word). fedex, usps and dhl rarely occur inside English words, so any occurrence counts;
    'ups' counts only when it is not glued to letters on both sides.
    """
    s = fqdn.lower()
    for kw in ("fedex", "usps", "dhl"):
        if kw in s:
            return BRANDS[kw]
    for m in re.finditer("ups", s):
        before = s[m.start() - 1] if m.start() > 0 else "."
        after = s[m.end()] if m.end() < len(s) else "."
        if not before.isalpha() or not after.isalpha():
            return "UPS"
    return None


def features(fqdn: str) -> dict:
    fqdn = fqdn.lower().rstrip(".")
    parts = split_domain(fqdn)
    registered_label = parts.registered_domain.split(".")[0]
    subdomain = fqdn[: -len(parts.registered_domain)].rstrip(".") if fqdn != parts.registered_domain else ""
    brand = brand_token(fqdn)
    kw = [k for k in BRANDS if k in fqdn]
    in_registered = any(k in registered_label for k in kw)
    tokens = re.split(r"[.\-_0-9]+", fqdn)
    near_brand = any(0 < _levenshtein(t, b) <= 1 for t in tokens if 3 <= len(t) <= 7 for b in ("fedex", "usps", "dhl"))
    longest = max(fqdn.split("."), key=len)
    vowels = sum(ch in "aeiou" for ch in longest)
    return {
        "length": len(fqdn),
        "n_labels": fqdn.count(".") + 1,
        "n_hyphens": fqdn.count("-"),
        "n_digits": sum(ch.isdigit() for ch in fqdn),
        "entropy_longest_label": _entropy(longest),
        "vowel_ratio_longest_label": vowels / max(1, len(longest)),
        "brand_token": int(brand is not None),
        "brand_only_in_subdomain": int(bool(kw) and not in_registered),
        "com_dash_trick": int(bool(re.search(r"(fedex|usps|ups|dhl)\.com[-.]", fqdn))),
        "service_words": sum(w in fqdn for w in SERVICE_WORDS),
        "near_brand_spelling": int(near_brand),
        "punycode": int("xn--" in fqdn),
        "hosting_platform": int(any(fqdn == h or fqdn.endswith("." + h) for h in HOSTING)),
        "common_tld": int(parts.tld in COMMON_TLDS),
        "subdomain_depth": subdomain.count(".") + 1 if subdomain else 0,
    }


FEATURES = list(features("example.com"))


def frame(domains: list[str]) -> pd.DataFrame:
    return pd.DataFrame([features(d) for d in domains], index=domains)
