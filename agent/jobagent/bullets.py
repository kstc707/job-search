"""Bullet library: track every bullet's uses and outcomes, and release a wording for reuse
only after it has a proven success rate (Sai's rule, 2026-10-12).

Library format (a JSON list, synced with the Notion "Bullet Library" database):
  {"id", "family", "text", "uses": [application ids], "successes": [application ids]}

A success is an application whose tracker Status reached Interview Scheduled or Offer
(or that got a recruiter reply / next-step email, recorded by the agent).
"""
import re

from . import texparse

FAMILIES = {
    "ai": r"\bai\b|machine learning|\bml\b|llm|genai|generative|agentic|forward deployed|nlp",
    "ds": r"data scientist|scientist|research|measurement|statistic",
    "da": r"analyst|\bbi\b|business intelligence|analytics|insights|reporting",
}


def family_for_title(title):
    """Role family from a job title; AI wins over DS, DS over DA."""
    for fam in ("ai", "ds", "da"):
        if re.search(FAMILIES[fam], title, re.I):
            return fam
    return "da"


def record_use(library, tex, application_id, family):
    """Add one application's bullets to the library."""
    by_id = {b["id"]: b for b in library}
    for text in texparse.bullets(tex):
        bid = texparse.bullet_id(text)
        entry = by_id.get(bid)
        if entry is None:
            entry = {"id": bid, "family": family, "text": text, "uses": [], "successes": []}
            library.append(entry)
            by_id[bid] = entry
        if application_id not in entry["uses"]:
            entry["uses"].append(application_id)
    return library


def record_outcome(library, application_id):
    """Mark every bullet used on a successful application."""
    for b in library:
        if application_id in b["uses"] and application_id not in b["successes"]:
            b["successes"].append(application_id)
    return library


def baseline_rate(library):
    """Share of all applications in the library that succeeded."""
    apps = {a for b in library for a in b["uses"]}
    wins = {a for b in library for a in b["successes"]}
    return len(wins) / len(apps) if apps else 0.0


def reusable(library, family=None, min_uses=2):
    """Bullets cleared for reuse: at least one success, enough uses to judge, and a
    success rate at or above the baseline. Ranked by success rate."""
    base = baseline_rate(library)
    out = []
    for b in library:
        if family and b["family"] != family:
            continue
        uses, wins = len(b["uses"]), len(b["successes"])
        if wins == 0 or uses < min_uses:
            continue
        rate = wins / uses
        if rate >= base:
            out.append({**b, "rate": round(rate, 2)})
    return sorted(out, key=lambda b: (-b["rate"], -len(b["uses"])))
