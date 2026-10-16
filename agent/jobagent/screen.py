"""Knockout screen: hard requirements checked before any resume is built (no model tokens).

A job fails the screen when the posting asks for something the candidate cannot meet:
citizenship or clearance, sponsorship they would need, OPT when they are on it, too many years, a degree they lack,
a senior title, or student-only status. Every rule reads the candidate from the user config,
so the same screen works for anyone.
"""
import re

_CITIZEN = re.compile(
    r"(u\.?\s?s\.?|united states)\s+citizen(ship)?\s+(is\s+)?(required|only)"
    r"|must\s+be\s+an?\s+(u\.?\s?s\.?|united states)\s+citizen"
    r"|requires?\s+(u\.?\s?s\.?|united states)\s+citizenship"
    r"|citizenship\s+(is\s+)?required"
    r"|(u\.?\s?s\.?|united states)\s+citizenship\b(?!\s+(is\s+)?(not\s+required|preferred))", re.I)
_CLEARANCE = re.compile(
    r"(security|secret|ts/sci|top secret)\s+clearance"
    r"|(ability|able|eligib\w*)\s+to\s+obtain\s+(a\s+|an\s+)?(\w+\s+)?clearance"
    r"|clearance\s+(is\s+)?required", re.I)
_NO_SPONSOR = re.compile(
    r"(not|unable to|cannot|can't|will not|won't)\s+(provide\s+|offer\s+)?sponsor"
    r"|no\s+(visa\s+)?sponsorship|without\s+(the\s+need\s+for\s+)?sponsorship", re.I)
_NO_OPT = re.compile(
    r"\b(f-?1|opt|stem\s+opt|cpt)\b[^.\n]{0,60}?\b(not\s+eligi\w*|ineligi\w*|not\s+(be\s+)?(accepted|considered|supported)|does\s+not\s+qualify)"
    r"|\b(not|unable\s+to|cannot|won't)\b[^.\n]{0,60}?\b(support|accept|sponsor|consider)\w*\b[^.\n]{0,120}?\b(f-?1|opt|stem\s+opt|cpt)\b", re.I)
_STUDENT = re.compile(
    r"must\s+be\s+(currently\s+)?(enrolled|a\s+(current\s+)?student)"
    r"|currently\s+enrolled\s+(in|as)|returning\s+to\s+school", re.I)
_YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?(?:years?|yrs?)\b[^.\n]{0,60}?experience"
    r"|experience[^.\n]{0,25}?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)

DEFAULT_SENIOR = ["senior", "sr.", "sr ", "staff", "principal", "lead", "manager", "director",
                  "head of", "vp", "architect"]


def required_years(meta, text):
    """Years of experience the posting asks for: the feed's value if it has one, otherwise the
    largest 'N years ... experience' in the text (the binding requirement)."""
    if isinstance(meta.get("yearsOfExperienceMin"), (int, float)):
        return meta["yearsOfExperienceMin"]
    found = [int(a or b) for a, b in _YEARS.findall(text)]
    found = [n for n in found if n <= 15]
    return max(found) if found else None


def screen(meta, text, cfg):
    """List of knockout reasons; empty means the job passes."""
    auth = cfg.get("work_authorization", {})
    reasons = []
    title = (meta.get("title") or "").lower()

    for term in cfg.get("skip_title_terms", DEFAULT_SENIOR):
        if term.strip() and re.search(r"(^|\W)" + re.escape(term.strip()) + r"(\W|$)", title):
            reasons.append(f"senior title ({term.strip()})")
            break

    if not auth.get("us_citizen") and _CITIZEN.search(text):
        reasons.append("requires U.S. citizenship")
    clearance = meta.get("clearanceRequired") is True or _CLEARANCE.search(text)
    if clearance and not auth.get("clearance_eligible"):
        reasons.append("requires a security clearance")

    sponsorship = str(meta.get("sponsorship", "")).upper()
    if auth.get("needs_sponsorship") and (sponsorship == "NO_SPONSORSHIP" or _NO_SPONSOR.search(text)):
        reasons.append("no visa sponsorship")

    if auth.get("on_opt") and _NO_OPT.search(text):
        reasons.append("does not accept OPT work authorization")

    years = required_years(meta, text)
    limit = cfg.get("max_required_years")
    if years is not None and limit is not None and years > limit:
        reasons.append(f"asks for {years}+ years (limit {limit})")

    degrees = {d.upper() for d in cfg.get("degrees", [])}
    req = meta.get("degreeRequirements") or {}
    if str(req.get("phd", "")).upper() == "REQUIRED" and "DOCTORATE" not in degrees:
        reasons.append("requires a PhD")
    if str(req.get("masters", "")).upper() == "REQUIRED" and not degrees & {"MASTERS", "DOCTORATE"}:
        reasons.append("requires a master's degree")

    if not cfg.get("student") and _STUDENT.search(text):
        reasons.append("student-only")
    return reasons
