"""Bullet library: release a bullet's wording for reuse only after it has a proven success
rate (the owner's rule).

The library is built lazily. Every sent resume's PDF is already stored on its tracker row, so
nothing is copied ahead of time. When an application succeeds (interview, offer, or a recruiter
reply), the agent passes all sent resumes to `scan`: each bullet of the successful resumes is
matched by similarity against every other resume, which gives its uses and successes. Only
those bullets go into the tracker's Bullets tab.
"""
import re

from . import texparse
from .audit import best_match

FAMILIES = {
    "ai": r"\bai\b|machine learning|\bml\b|llm|genai|generative|agentic|forward deployed|nlp",
    "ds": r"data scientist|scientist|research|measurement|statistic",
    "da": r"analyst|\bbi\b|business intelligence|analytics|insights|reporting",
}
SAME_WORDING = 0.8  # similarity at which two bullets count as the same wording


def family_for_title(title):
    """Role family from a job title; AI wins over DS, DS over DA."""
    for fam in ("ai", "ds", "da"):
        if re.search(FAMILIES[fam], title, re.I):
            return fam
    return "da"


def pdf_bullets(pdf_text):
    """Bullets from `pdftotext` output: a bullet starts at '•' and wraps onto at most one
    more line (the resume skill caps bullets at two lines)."""
    lines = [l.strip() for l in pdf_text.replace("ﬁ", "fi").replace("ﬂ", "fl").splitlines()]
    lines = [l for l in lines if l]
    out = []
    for i, line in enumerate(lines):
        if not line.startswith("•"):
            continue
        text = line.lstrip("• ").strip()
        j = i + 1
        # Bullets end with a period; keep joining wrapped lines until one does (max 2 more).
        while not text.endswith(".") and j < len(lines) and j <= i + 2 and _continues(lines[j]):
            text = text + " " + lines[j]
            j += 1
        out.append(texparse.clean(text))
    return out


_DATES = re.compile(r"^(?:[A-Z][a-z]{2} )?\d{4}\s*[–-]\s*(?:Present|(?:[A-Z][a-z]{2} )?\d{4})$")


def _continues(line):
    """True when a line can be the wrapped tail of a bullet, not a new heading or bullet."""
    return not (line.startswith("•") or " | " in line or _DATES.match(line))


def scan(resumes, successes, families=None, threshold=SAME_WORDING):
    """Library entries for every bullet on a successful resume.

    resumes: {application id: [bullet text, ...]} for every sent resume
    successes: application ids with a positive outcome
    families: optional {application id: "ai" | "ds" | "da"}
    """
    families = families or {}
    entries, seen = [], set()
    for app in sorted(set(successes) & set(resumes)):
        for text in resumes[app]:
            bid = texparse.bullet_id(text)
            if bid in seen:
                continue
            seen.add(bid)
            uses = [a for a, items in resumes.items()
                    if a == app or best_match(text, items, threshold) >= threshold]
            entries.append({
                "id": bid, "family": families.get(app, ""), "text": text,
                "uses": sorted(uses), "successes": sorted(u for u in uses if u in successes),
            })
    baseline = len(set(successes) & set(resumes)) / len(resumes) if resumes else 0.0
    return {"baseline": round(baseline, 3), "applications": len(resumes), "bullets": entries}


def reusable(library, family=None, min_uses=2):
    """Bullets cleared for reuse: 1+ success, at least `min_uses` uses, and a success rate at
    or above the baseline (the share of all applications that succeeded). Ranked by rate."""
    base = library.get("baseline", 0.0) if isinstance(library, dict) else 0.0
    items = library.get("bullets", []) if isinstance(library, dict) else library
    out = []
    for b in items:
        if family and b.get("family") and b["family"] != family:
            continue
        uses, wins = len(b["uses"]), len(b["successes"])
        if wins == 0 or uses < min_uses:
            continue
        rate = wins / uses
        if rate >= base:
            out.append({**b, "rate": round(rate, 2)})
    return sorted(out, key=lambda b: (-b["rate"], -len(b["uses"])))
