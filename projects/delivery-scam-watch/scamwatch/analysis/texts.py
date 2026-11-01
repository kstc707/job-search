"""Text mining of real scam text messages (smishing).

What a fraud analyst wants from a pile of reported texts:
  1. the links in them, even when written to dodge filters ('shm.to/ IRSDocs', 'hxxps://x[.]com');
  2. which ones impersonate a delivery company, and what story (lure) they tell;
  3. which messages come from the same script (a campaign), even when the link, the amount
     or the tracking number changes;
  4. how those links relate to the domains our domain monitor watches.

Everything here is pure (no database) so it can be tested on fixed examples.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd
import tldextract
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .features import BRANDS, brand_token

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)  # bundled list, no network

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "shm.to", "rb.gy", "cutt.ly", "t.ly",
    "tiny.cc", "s.id", "shorturl.at", "rebrand.ly", "bl.ink", "short.gy", "u.to", "v.gd", "qrco.de",
}  # fmt: skip

# host, optionally preceded by a scheme; then an optional path. A space after the slash is allowed
# once ('shm.to/ IRSDocs'), a trick to break automatic link detection.
_URL = re.compile(
    r"(?<![@\w.-])((?:https?://)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,23})"
    r"(/(?: (?=[A-Za-z0-9]{3,}))?[^\s<>\"']*)?",
    re.I,
)


def refang(text: str) -> str:
    """Undo defanging so links can be parsed: hxxp -> http, [.] / (.) / [dot] -> '.'."""
    text = re.sub(r"hxxp", "http", text, flags=re.I)
    return re.sub(r"\s*(?:\[\.\]|\(\.\)|\[dot\]|\(dot\))\s*", ".", text, flags=re.I)


def extract_urls(text: str) -> list[str]:
    """Links in a message, as https://host/path with a lower-case host; no e-mail addresses."""
    out: list[str] = []
    for m in _URL.finditer(refang(text or "")):
        host = re.sub(r"^https?://", "", m.group(1), flags=re.I).lower().strip(".")
        ext = _extract(host)
        if not ext.suffix or not ext.domain:
            continue  # 'u.s', 'a.m', 'no.1': not a real public suffix
        if re.fullmatch(r"[\d.]+", host):
            continue
        path = (m.group(2) or "").replace(" ", "").rstrip(".,;:!?)]}")
        url = f"https://{host}{path}"
        if url not in out:
            out.append(url)
    return out


def defang_links(text: str) -> str:
    """Make every link in a message unclickable for display, leaving the rest of the text as is."""
    for url in extract_urls(text):
        host = host_of(url)
        text = re.sub(re.escape(host), host.replace(".", "[.]"), text, flags=re.I)
    text = re.sub(r"http(s?)://", r"hxxp\1://", text, flags=re.I)
    return re.sub(r"\b(Hello|Hi|Dear|Hey)\s+[A-Z][a-z]+", r"\1 <name>", text)  # recipients' names stay private


def host_of(url: str) -> str:
    return re.sub(r"^https?://", "", url).split("/")[0]


def registered_domain(host: str) -> str:
    ext = _extract(host)
    return f"{ext.domain}.{ext.suffix}" if ext.suffix else host


# ------------------------------------------------------------------ what the text is about ----
def brand_in_text(text: str) -> str | None:
    """Delivery brand named as a word in the message text (not inside 'groups' or 'cups')."""
    t = (text or "").lower()
    if re.search(r"\bfed\s?ex\b", t):
        return "FedEx"
    if re.search(r"\busps\b|\bu\.s\. ?postal|\bpostal service\b", t):
        return "USPS"
    if re.search(r"\bdhl\b", t):
        return "DHL"
    if re.search(r"\bups\b", t) and not re.search(
        r"\b(?:ups and downs|power[- ]ups?|sign[- ]ups?|pick[- ]ups?|follow[- ]ups?)\b", t
    ):
        return "UPS"
    return None


DELIVERY_WORDS = re.compile(r"\b(?:package|parcel|shipment|delivery|deliver|courier|tracking|redeliver\w*)\b", re.I)

# The story the message tells. Ordered: the first match wins, most specific first.
LURES = [
    ("pay a fee", r"\b(?:fee|charge|pay(?:ment)?|\$\s?\d|duty|duties|customs|postage|surcharge|toll)\b"),
    (
        "update address",
        r"\b(?:address|incomplete|insufficient|incorrect|confirm (?:your )?(?:details|information|info))\b",
    ),
    (
        "failed or held delivery",
        r"\b(?:unable to deliver|could not be delivered|couldn'?t be delivered|failed|held|on hold"
        r"|suspended|returned|undeliverable|attempt(?:ed)?)\b",
    ),
    ("schedule delivery", r"\b(?:schedule|reschedule|redeliver\w*|arrange)\b"),
    ("track package", r"\b(?:track|tracking|status|arriv\w*|shipped|out for delivery)\b"),
]
URGENCY = re.compile(
    r"\b(?:within \d+ ?(?:h|hrs?|hours?)|24 ?h|12 ?h|48 ?h|immediately|today|final notice|last notice"
    r"|urgent|as soon as possible|asap|expire\w*)\b",
    re.I,
)
REPLY_TRICK = re.compile(
    r"\breply (?:with )?[\"'“]?(?:y|yes|1)\b|\bexit the (?:text|sms)"
    r"|\bre-?open (?:this|the) (?:message|text)|\bcopy (?:the|this) link\b",
    re.I,
)


def lure_of(text: str) -> str:
    for name, pattern in LURES:
        if re.search(pattern, text or "", re.I):
            return name
    return "other"


def sender_type(sender: str, given: str | None = None) -> str:
    if given and str(given).strip() and str(given).lower() != "nan":
        return str(given).strip()
    s = (sender or "").strip()
    if "@" in s:
        return "Email Address"
    digits = re.sub(r"\D", "", s)
    if 4 <= len(digits) <= 6:
        return "Short Code"
    if digits:
        return "Phone Number"
    return "Unknown"


def country_code(sender: str) -> str | None:
    s = (sender or "").strip()
    m = re.match(r"^\+(\d{1,3})[\s(-]", s)
    if m:
        return "+" + m.group(1)
    if re.sub(r"\D", "", s).__len__() == 10:
        return "+1"
    return None


# ------------------------------------------------------------------ campaigns (same script) ----
def normalize(text: str) -> str:
    """Strip what changes between copies of one script: links, amounts, numbers, names."""
    t = refang(text or "").lower()
    for url in extract_urls(t):
        t = t.replace(url.replace("https://", ""), " ")
    t = re.sub(r"https?://\S+", " <url> ", t)
    t = re.sub(r"\$\s?\d+(?:[.,]\d+)?", " <money> ", t)
    t = re.sub(r"\+?\d[\d\s().-]{6,}\d", " <phone> ", t)
    t = re.sub(r"\d+", " <num> ", t)
    t = re.sub(r"[^a-z<> ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def campaigns(texts: list[str], threshold: float = 0.6) -> np.ndarray:
    """Group messages written from the same script. Returns one campaign id per message.

    TF-IDF over word pairs of the normalised text, cosine similarity, and single-link grouping:
    two messages share a campaign if they are linked by a chain of pairs at least `threshold` alike.
    """
    n = len(texts)
    if n == 0:
        return np.array([], dtype=int)
    norm = [normalize(t) or "<empty>" for t in texts]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    sim = cosine_similarity(vec.fit_transform(norm))
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    rows, cols = np.where(np.triu(sim, 1) >= threshold)
    for i, j in zip(rows, cols, strict=True):
        parent[find(i)] = find(j)
    roots = [find(i) for i in range(n)]
    ids = {r: k for k, r in enumerate(dict.fromkeys(roots))}
    return np.array([ids[r] for r in roots])


# ------------------------------------------------------------------ one table for analysis ----
def message_frame(rows: list[dict]) -> pd.DataFrame:
    """rows: dicts with text, sender, sender_type, brand_claimed, posted_at, origin."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["urls"] = df.text.map(extract_urls)
    if "extra_urls" in df:
        df["urls"] = [
            list(dict.fromkeys(a + [u for u in (b or []) if u])) for a, b in zip(df.urls, df.extra_urls, strict=True)
        ]
    df["hosts"] = df.urls.map(lambda us: [host_of(u) for u in us])
    df["brand_text"] = df.text.map(brand_in_text)
    claimed = df.get("brand_claimed", pd.Series([None] * len(df))).map(
        lambda b: next((v for v in BRANDS.values() if isinstance(b, str) and b.strip().lower() == v.lower()), None)
    )
    df["brand"] = df.brand_text.fillna(claimed)
    df["delivery"] = df.brand.notna() | df.text.str.contains(DELIVERY_WORDS, na=False)
    df["lure"] = df.text.map(lure_of)
    df["urgent"] = df.text.str.contains(URGENCY, na=False)
    df["reply_trick"] = df.text.str.contains(REPLY_TRICK, na=False)
    df["sender_kind"] = [
        sender_type(s, g) for s, g in zip(df.sender.fillna(""), df.get("sender_type", [None] * len(df)), strict=True)
    ]
    df["country"] = df.sender.fillna("").map(country_code)
    df["link_has_brand"] = df.hosts.map(lambda hs: any(brand_token(h) for h in hs))
    df["shortener"] = df.hosts.map(
        lambda hs: any(registered_domain(h) in URL_SHORTENERS or h in URL_SHORTENERS for h in hs)
    )
    return df


def shares(series: pd.Series, top: int = 8) -> dict:
    c = Counter(series.dropna())
    total = sum(c.values()) or 1
    return {k: round(v / total, 3) for k, v in c.most_common(top)}


# ------------------------------------------------------------------ would a script match catch it? ----
def script_reuse(df: pd.DataFrame, threshold: float = 0.6) -> pd.DataFrame:
    """For each message in time order: was its script already seen, and was its link domain new?

    Uses only earlier messages for each decision (plain term frequency, no IDF fitted on the
    future), so it measures what a control running at the time could have known.
    """
    d = df.sort_values("posted_at").reset_index(drop=True).copy()
    if d.empty:
        return d.assign(known_script=[], new_domain=[])
    vec = TfidfVectorizer(ngram_range=(1, 2), use_idf=False)
    sim = cosine_similarity(vec.fit_transform([normalize(t) or "<empty>" for t in d.text]))
    known, new_domain, seen = [], [], set()
    for i in range(len(d)):
        known.append(bool(i > 0 and sim[i, :i].max() >= threshold))
        doms = {registered_domain(h) for h in d.hosts[i]}
        new_domain.append(bool(doms) and not (doms & seen))
        seen |= doms
    d["known_script"], d["new_domain"] = known, new_domain
    return d


def summarize(df: pd.DataFrame, gen_a: pd.DataFrame | None = None) -> dict:
    """Every text-mining number the report and dashboard show. df comes from message_frame()."""
    d = df[df.delivery].copy()
    with_link = d[d.urls.str.len() > 0]
    d["campaign"] = campaigns(d.text.tolist())
    camp = (
        d.groupby("campaign")
        .agg(
            messages=("text", "size"),
            domains=("hosts", lambda x: len({registered_domain(h) for hs in x for h in hs})),
            first=("posted_at", "min"),
            last=("posted_at", "max"),
            brand=("brand", lambda x: x.mode().iat[0] if x.notna().any() else "unbranded"),
            example=("text", "first"),
        )
        .sort_values("messages", ascending=False)
    )
    multi = camp[camp.messages >= 2]
    reuse = script_reuse(d)
    late = reuse.iloc[len(reuse) // 2 :]
    out = {
        "messages": len(df),
        "by_origin": df.groupby("origin").size().to_dict(),
        "delivery_messages": len(d),
        "delivery_by_origin": d.groupby("origin").size().to_dict(),
        "delivery_by_brand": d.brand.fillna("unbranded").value_counts().to_dict(),
        "share_with_link": round(float((d.urls.str.len() > 0).mean()), 3),
        "link_contains_brand": round(float(with_link.link_has_brand.mean()), 3) if len(with_link) else None,
        "link_shortener": round(float(with_link.shortener.mean()), 3) if len(with_link) else None,
        "lures": shares(d.lure),
        "urgency": round(float(d.urgent.mean()), 3),
        "reply_trick": round(float(d.reply_trick.mean()), 3),
        "sender_kinds": shares(d.sender_kind),
        "sender_countries": shares(d.country),
        "campaigns": {
            "repeated_scripts": int(len(multi)),
            "messages_in_repeated_scripts": int(multi.messages.sum()),
            "top": [
                {
                    "messages": int(r.messages),
                    "distinct_domains": int(r.domains),
                    "brand": r.brand,
                    "first": str(r.first)[:10],
                    "last": str(r.last)[:10],
                    "example": r.example[:220],
                }
                for r in multi.head(6).itertuples()
            ],
        },
        "script_reuse": {
            "later_half_messages": len(late),
            "later_reuse_known_script": round(float(late.known_script.mean()), 3) if len(late) else None,
            "of_those_with_never_seen_domain": round(float(late[late.known_script].new_domain.mean()), 3)
            if late.known_script.any()
            else None,
        },
        "link_domains": sorted({registered_domain(h) for hs in d.hosts for h in hs}),
    }
    if gen_a is not None and len(gen_a):
        a = gen_a[gen_a.label == "scam"]
        out["generator_a"] = {
            "lures": shares(a.text.map(lure_of)),
            "reply_trick": round(float(a.text.str.contains(REPLY_TRICK).mean()), 3),
            "link_contains_brand": round(
                float(a.text.map(lambda t: any(brand_token(host_of(u)) for u in extract_urls(t))).mean()), 3
            ),
        }
    return out
