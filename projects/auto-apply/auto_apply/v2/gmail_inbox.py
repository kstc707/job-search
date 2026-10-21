"""Turn Gmail messages into the inbox rows that `outcomes.py` reads (replaces the Tsenta inbox).

Tsenta used to read Sai's application emails and give each one a category. This module does
the same from the Gmail connector's output, with rules you can read below, and writes rows in
the exact shape `outcomes.build_plan` already accepts, so the rest of the outcome sync does
not change.

Input: JSON the agent saved from the Gmail connector. Any of these works:
- a `search_threads` response: {"threads": [{"id", "messages": [message, ...]}, ...]}
- a `get_thread` response:     {"id", "messages": [message, ...]}
- a list of threads or a list of messages
where a message is {"id", "threadId", "sender", "toRecipients", "subject", "snippet", "date",
"internalDate", "labelIds", ["plaintextBody"]}. `sender` is "addr" or "Name <addr>".

Output rows (outcomes.py input): {"id", "threadId", "from", "fromName", "subject", "snippet",
"receivedAt", "category", "application": {"companyName", "trackedApplication":
{"positionTitle"}} | null, "rule"}. `rule` says which rule picked the category.

How a message is classified (first rule that fires wins):
 0. Sai's own sent mail and drafts are skipped.
 1. Job-board alert senders (jobalert., match.indeed, nurture., talent-community mailers)
    -> JOB_ALERT.
 2. Not about a job at all (no ATS sender and no job words) -> NOT_JOB (dropped from output).
 3. REJECTION, OFFER, ASSESSMENT, INTERVIEW: phrase rules on subject + snippet + body. Before
    these run, sentences that are only conditional ("if selected, we will contact you to
    schedule an interview") are removed, so an acknowledgment that mentions a future
    interview is not mistaken for an invitation.
 4. ACKNOWLEDGMENT: "thank you for applying", "application received" and similar.
 5. RECRUITER_MESSAGE: written by a person (not a no-reply/notification mailbox; a personal
    display name, a "Re:" subject, or Gmail's Primary/Personal tab).
 6. Alert/newsletter/account phrases ("new jobs matching", "newsletter", "candidate home
    account") -> JOB_ALERT or GENERAL.
 7. Anything else that is about a job -> UNCLASSIFIED, listed for Sai to look at.

Company and title: taken from phrases such as "your interest in Acme and the Data Analyst
position", "applying to Acme", "Data Analyst - Application received", then from the sender's
display name ("Acme Hiring Team" -> "Acme"). Only a company found in the text or the display
name is put in `application.companyName`; a company guessed from an ATS mailbox
("acme@myworkday.com") goes to `fromName` only, so outcomes.py uses it to find an existing
tracker row but never creates a new row from it.
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from email.utils import parseaddr

# ---------------------------------------------------------------- vocabulary

OUTCOME_CATEGORIES = ("ACKNOWLEDGMENT", "REJECTION", "INTERVIEW", "ASSESSMENT", "RECRUITER_MESSAGE", "OFFER")
ALL_CATEGORIES = OUTCOME_CATEGORIES + ("JOB_ALERT", "GENERAL", "UNCLASSIFIED", "NOT_JOB")

# Applicant tracking systems (ATS) and the mail domains they send from.
ATS_DOMAINS = {
    "myworkday.com": "Workday", "myworkdayjobs.com": "Workday", "greenhouse-mail.io": "Greenhouse",
    "greenhouse.io": "Greenhouse", "icims.com": "iCIMS", "smartrecruiters.com": "SmartRecruiters",
    "lever.co": "Lever", "ashbyhq.com": "Ashby", "ultipro.com": "UKG", "ukg.com": "UKG",
    "paylocity.com": "Paylocity", "dayforcehcm.com": "Dayforce", "dayforce.com": "Dayforce",
    "jobvite.com": "Jobvite", "taleo.net": "Taleo", "oraclecloud.com": "Oracle", "brassring.com": "BrassRing",
    "successfactors.com": "SuccessFactors", "breezy-mail.com": "Breezy", "workablemail.com": "Workable",
    "workable.com": "Workable", "recruitee.com": "Recruitee", "applytojob.com": "JazzHR",
    "bamboohr.com": "BambooHR", "avature.net": "Avature", "eightfold.ai": "Eightfold",
    "paradox.ai": "Paradox", "phenompeople.com": "Phenom", "adp.com": "ADP",
}
# Assessment vendors: an invitation from (or naming) one of these is an ASSESSMENT.
ASSESSMENT_VENDORS = ("hirevue", "codility", "hackerrank", "codesignal", "pymetrics", "harver", "criteriacorp",
                      "criteria corp", "testgorilla", "karat", "coderbyte", "vervoe", "wonderlic", "spark hire",
                      "sparkhire", "modern hire", "talview", "mettl", "shl.com", "plum.io", "canditech", "imocha")
ALERT_SENDERS = re.compile(r"(jobalert|job-alert|jobalerts|match\.indeed|nurture\.|talentcommunity|"
                           r"jobs-listings)", re.I)
AUTOMATED_LOCAL = re.compile(
    r"^(no-?reply|do-?not-?reply|donotreply|noreply|notifications?|notify|alerts?|mailer|mailer-daemon|news|"
    r"newsletters?|info|hello|team|careers?|jobs?|talent|recruiting|recruitment|hr|support|updates?|"
    r"marketing|digest|webmaster|admin|system|bounces?|candidates?|applications?|apply|hiring)\b", re.I)
FREEMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com", "icloud.com",
            "me.com", "aol.com", "proton.me", "protonmail.com", "msn.com"}

# "your application" and "applied" alone are not enough: colleges, lenders and scholarships use them too.
JOB_WORDS = re.compile(
    r"\b(position|role|candidate|candidacy|interview\w*|recruit\w*|hiring|talent acquisition|requisition|"
    r"thank you for applying|(job|employment) application|job offer|offer letter|"
    r"hiring manager|job opportunit\w*|career opportunit\w*)\b", re.I)

# Phrase rules. Each entry: (rule name, regex). Searched case-insensitively.
_R = lambda *ps: [(p, re.compile(p, re.I)) for p in ps]  # noqa: E731
REJECTION = _R(
    r"not (to )?(be )?mov(e|ing) forward",
    r"(decided|chosen|elected|decision) to (pursue|proceed|move forward|go forward) with (other|another|a different)",
    r"pursue other candidates",
    r"other candidates (whose|who)",
    r"(will|would) not be (moving|proceeding|progressing|advancing|considered|offering)",
    r"no longer (being )?consider",
    r"(were|was|have not been|has not been) (not )?selected",
    r"not been selected|not selected (for|to)",
    r"(position|role|requisition|job|opening) (has been|is now|was|has) (filled|closed|cancell?ed|been filled)",
    r"unable to (offer you|move forward|proceed|advance)",
    r"regret to (inform|let you know)",
    r"not (be )?a (match|fit) (at this time|for)",
    r"unfortunately[^.]{0,200}\b(not|other candidates|decided|unable|filled|closed)\b",
)
OFFER = _R(
    r"(pleased|happy|excited|delighted|thrilled) to (extend|offer you|make you an offer)",
    r"\boffer (letter|of employment)\b",
    r"extend(ing)? (you )?an? (formal |verbal |written |conditional )?(job |employment )?offer",
    r"\b(job|employment) offer\b",
    r"congratulations[^.]{0,80}\boffer\b",
)
ASSESSMENT = _R(
    r"\b(" + "|".join(re.escape(v) for v in ASSESSMENT_VENDORS) + r")\b",
    r"\b(online|technical|skills?|coding|cognitive|personality|pre-?employment|virtual|written|aptitude) "
    r"(assessment|test|challenge|evaluation|exercise)\b",
    r"\b(complete|take|invited to|invitation to)( the| an| your| a| our)?( \w+){0,3} (assessment|questionnaire)\b",
    r"\btake-?home (assignment|exercise|challenge|project)\b",
    r"\b(one-?way|on-?demand|recorded|asynchronous|self-?recorded) (video )?interview\b",
    r"\bassessment (invitation|invite|link|request)\b",
)
INTERVIEW = _R(
    r"\b(invite|invitation|like|love|want|happy|excited|pleased) (for )?(you )?to (an? |the )?(\w+ ){0,2}"
    r"(interview|phone screen|screening|call|chat|conversation|meet)\b",
    r"\binterview (invitation|invite|request|confirmation|confirmed|scheduled|schedule|availability|details)\b",
    r"\bschedul(e|ing) (a |an |your |the )?(\w+ ){0,2}(interview|phone screen|screening call|screen|call|chat)\b",
    r"\b(your|share your|provide your|send me your|send your|let me know your|what is your) (availability|available times)\b",
    r"\b(phone|video|virtual|technical|onsite|on-site|in-person|panel|final|first|second|hiring manager) "
    r"(interview|screen|screening)\b",
    r"\b(first|second|third|final|next)[- ]round\b",
    r"(calendly\.com|goodtime\.io|select a time|book a time|pick a time|choose a time)",
    r"(like|happy|pleased|excited) to (move|moving) forward with (you|your)",
)
ACK = _R(
    r"thank(s| you) for (applying|your application|submitting|your recent application|your interest in)",
    r"\bapplication (has been |was |is )?(received|submitted|complete)\b",
    r"\b(received|receipt of|reviewing) your application\b",
    r"\bwe('ve| have) (received|got) your\b",
    r"\bapplication (confirmation|acknowledg\w+)\b",
    r"\bsuccessfully (applied|submitted)\b",
    r"\byour application (to|for|with|at)\b",
)
ALERT_PHRASES = _R(
    r"\bjob alert\b", r"\bnew jobs?\b", r"jobs? (matching|that match|for you|you may like)", r"recommended jobs?",
    r"\bnewsletter\b", r"talent (community|network) (newsletter|update)", r"staying connected", r"\bjobs? digest\b",
    r"new (job )?opportunities at", r"is hiring\b", r"\bstrong match for this\b",
)
ACCOUNT_PHRASES = _R(
    r"candidate (home )?account", r"verify your (email|account)", r"(reset|change) your password", r"password reset",
    r"account (created|deactivated|activated|verification)", r"\bsign-?in code\b", r"confirm your email",
)
CONDITIONAL = re.compile(r"\b(if|should (you|your|we|there)|in the event|whether|may (contact|reach)|"
                         r"will (contact|reach out|be in touch|get in touch|notify)|unless)\b", re.I)

# Words that make a phrase look like a job title.
TITLE_WORD = re.compile(
    r"\b(analyst|analytics|scientist|science|engineer|developer|manager|specialist|associate|intern|internship|"
    r"consultant|coordinator|administrator|designer|representative|director|assistant|technician|officer|"
    r"architect|advisor|adviser|researcher|programmer|accountant|strategist|lead|fellow|apprentice|"
    r"launchpad|trainee|statistician|economist|actuary|auditor|operator|planner|recruiter)\b", re.I)
_WORD = r"[\w&'’\-]*(?:\.[A-Za-z0-9]+)*"   # "Acme", "O'Brien", "Example.io"; never ends with "."
_CO = r"(?P<c>[A-Z0-9]" + _WORD + r"(?: (?:[A-Z0-9&]" + _WORD + r"|of|de)){0,5})"
COMPANY_PATTERNS = [
    re.compile(r"(?i:interest in|applying to|applying with|applied to|applied with|application to|application with|"
               r"applying at|applied at|application at|career at|careers at|opportunities at|joining|"
               r"position at|role at|opening at|team at|considering|chose|choosing|join) " + _CO),
    re.compile(r"\b(?i:analyst|scientist|engineer|associate|specialist|intern|position|role|opening) (?i:at|with) " + _CO),
    re.compile(r"(?i:from|at) (?:the )?" + _CO + r" (?i:talent acquisition|recruiting|recruitment|hiring|careers|people) (?i:team)"),
]
TITLE_PATTERNS = [
    re.compile(r"(?i:the) (?P<t>[A-Z][\w/&,'’()+\- ]{2,80}?) (?i:position|role|opening|job|opportunity|vacancy)\b"),
    re.compile(r"(?i:position|role|job|opening) (?i:of|as) (?:(?i:an?|the) )?(?P<t>[A-Z][\w/&,'’()+\- ]{2,80}?)"
               r"(?= (?i:at|with|in|for)\b|[.!,;|]|$)"),
    re.compile(r"(?i:applying for|applied for|application for|apply for|applying to|applied to|interest in|"
               r"consideration for|candidacy for) (?:(?i:the|our|an?) )?(?P<t>[A-Z][\w/&,'’()+\- ]{2,80}?)"
               r"(?= (?i:position|role|opening|job|at|with|in)\b|[.!,;|]|$)"),
    re.compile(r"(?i:position|role|job|requisition)\s*[:#\-–]\s*(?P<t>[A-Z][\w/&,'’()+\- ]{2,80}?)(?=\s*(?:[|.!(]|$| (?i:at|with) ))"),
]
GENERIC_COMPANY = re.compile(
    r"^(the|your|our|this|us|we|a|an|it|workday|greenhouse|lever|ashby|icims|smartrecruiters|indeed|linkedin|"
    r"no-?reply|careers?|jobs?|talent|recruiting|hiring|team|hr|candidate|position|role|application|"
    r"applying|you|my|their|interview|opportunit\w*|notifications?)$", re.I)
_REQ_ID = re.compile(r"\s*[\[(#]?\b(?:R|JR|REQ|req|ID|Job ID)?[-_ ]?\d{4,}[\])]?\s*$")
_DISPLAY_SUFFIX = re.compile(
    r"\s*(?:[-|@,]\s*)?\b(talent acquisition|recruiting|recruitment|hiring|careers?|jobs|people|hr|"
    r"human resources|team|talent|notifications?|no-?reply|via \w+|workday|greenhouse|lever|ashby)\b.*$", re.I)


# ---------------------------------------------------------------- input shape

def load_messages(data) -> list[dict]:
    """Flatten whatever the connector returned into a list of message dicts (deduped by id)."""
    if isinstance(data, dict):
        if "threads" in data:
            data = data["threads"]
        elif "messages" in data:
            data = [data]
        else:
            data = [data]
    out, seen = [], set()
    for item in data or []:
        msgs = item.get("messages") if isinstance(item, dict) and "messages" in item else [item]
        for m in msgs or []:
            if not isinstance(m, dict) or m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            out.append(m)
    return out


def _clean(s: str | None) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"[͏​-‏⁠﻿­]", "", s)  # invisible padding in marketing mail
    return " ".join(s.split())


def _received(m: dict) -> str:
    if m.get("date"):
        return m["date"]
    if m.get("internalDate"):
        ts = int(m["internalDate"]) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


def _body(m: dict) -> str:
    return _clean(m.get("plaintextBody") or m.get("plaintext_body") or "")[:4000]


# ---------------------------------------------------------------- sender helpers

def ats_of(addr: str) -> str | None:
    domain = addr.rpartition("@")[2].lower()
    for d, name in ATS_DOMAINS.items():
        if domain == d or domain.endswith("." + d):
            return name
    return None


def is_automated(addr: str, name: str) -> bool:
    local = addr.partition("@")[0].lower()
    if AUTOMATED_LOCAL.match(local) or "noreply" in local or "no-reply" in local or "donotreply" in local:
        return True
    if ats_of(addr) and not looks_like_person(name):
        return True  # ATS mailboxes like acme@myworkday.com
    return False


def looks_like_person(name: str) -> bool:
    """'Jordan Lee' or 'Jordan Lee via Greenhouse', not 'Acme Talent Team' or 'Acme'."""
    name = re.sub(r"\s+via\s+.*$", "", name or "", flags=re.I).strip()
    if not name or _DISPLAY_SUFFIX.search(name) or re.search(r"\b(inc|llc|corp|ltd|co)\b", name, re.I):
        return False
    words = name.replace(",", " ").split()
    return 2 <= len(words) <= 4 and all(w[:1].isupper() for w in words) and not any(w.isupper() and len(w) > 3 for w in words)


def company_from_display(name: str) -> str:
    """'Acme Hiring Team' -> 'Acme'; 'Jordan Lee' -> '' (a person, not a company)."""
    name = (name or "").strip().strip('"')
    if not name or looks_like_person(name):
        return ""
    co = _DISPLAY_SUFFIX.sub("", name).strip(" -|,@")
    return "" if not co or GENERIC_COMPANY.match(co) else co


def company_from_ats_mailbox(addr: str) -> str:
    """acme@myworkday.com -> 'acme' (a weak guess: only used to find existing rows)."""
    if not ats_of(addr):
        return ""
    local = re.split(r"[+._-]", addr.partition("@")[0].lower())[0]
    return "" if not local or AUTOMATED_LOCAL.match(local) or local in ("do", "no") else local


def company_from_person_domain(addr: str) -> str:
    """jordan@acmehealth.com -> 'acmehealth' (weak guess)."""
    domain = addr.rpartition("@")[2].lower()
    if not domain or domain in FREEMAIL or ats_of(addr):
        return ""
    parts = domain.split(".")
    return parts[-2] if len(parts) >= 2 else ""


# ---------------------------------------------------------------- extraction

def _tidy_title(t: str) -> str:
    t = _REQ_ID.sub("", t.strip(" -–|:,.")).strip(" -–|:,.")
    return t


def extract_title(subject: str, text: str) -> str:
    for rx in TITLE_PATTERNS:
        for src in (subject, text):
            for m in rx.finditer(src):
                t = _tidy_title(m.group("t"))
                if TITLE_WORD.search(t) and len(t) <= 90:
                    return t
    # "Data Analyst - Application received" / "Your application: Data Analyst | Acme"
    for part in re.split(r"\s+[-–|:]\s+|:\s+|\s+\|\s*", subject):
        part = _tidy_title(re.sub(r"^(re|fwd?):\s*", "", part, flags=re.I))
        if TITLE_WORD.search(part) and not re.search(r"\b(application|thank|applying|interview|update|"
                                                     r"received|regarding|your|status|invitation)\b", part, re.I):
            return part
    return ""


def extract_company(subject: str, text: str) -> str:
    for rx in COMPANY_PATTERNS:
        for src in (subject, text):
            for m in rx.finditer(src):
                c = re.sub(r" (?:of|de)$", "", m.group("c").strip(" .,-"))
                if c and not GENERIC_COMPANY.match(c) and not TITLE_WORD.search(c) and len(c) <= 60:
                    return c
    return ""


# ---------------------------------------------------------------- classification

def _first(rules, text: str) -> str | None:
    for name, rx in rules:
        if rx.search(text):
            return name
    return None


def _definite(text: str) -> str:
    """Drop conditional sentences ('If selected, we'll schedule an interview')."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(s for s in sentences if not CONDITIONAL.search(s))


def classify(m: dict) -> tuple[str, str]:
    """(category, rule) for one Gmail message."""
    name, addr = parseaddr(m.get("sender") or m.get("from") or "")
    addr = addr.lower()
    subject = _clean(m.get("subject"))
    text = " ".join(x for x in (subject, _clean(m.get("snippet")), _body(m)) if x)
    labels = set(m.get("labelIds") or [])
    ats = ats_of(addr)

    if ALERT_SENDERS.search(addr):
        return "JOB_ALERT", f"alert sender {addr.partition('@')[2]}"
    vendor = next((v for v in ASSESSMENT_VENDORS if v.replace(" ", "") in addr), None)
    if not ats and not vendor and not JOB_WORDS.search(text):
        return "NOT_JOB", "no ATS sender and no job words"
    if "CATEGORY_PROMOTIONS" in labels and not ats and not vendor:
        return "NOT_JOB", "promotions tab, not an ATS"

    definite = _definite(text)
    for cat, rules in (("REJECTION", REJECTION), ("OFFER", OFFER), ("ASSESSMENT", ASSESSMENT), ("INTERVIEW", INTERVIEW)):
        hit = _first(rules, definite)
        if hit:
            return cat, f"{cat.lower()} phrase /{hit}/"
    if vendor:
        return "ASSESSMENT", f"assessment vendor sender ({vendor})"
    hit = _first(ACK[:-1], text)
    if hit:
        return "ACKNOWLEDGMENT", f"acknowledgment phrase /{hit}/"

    person = not is_automated(addr, name) and "CATEGORY_PROMOTIONS" not in labels and (
        looks_like_person(name) or re.match(r"^(re|fwd?):", subject, re.I) is not None
        or "CATEGORY_PERSONAL" in labels
        or re.match(r"^[a-z]+[._][a-z]+$", addr.partition("@")[0]) is not None)
    if person:
        return "RECRUITER_MESSAGE", "written by a person (not a no-reply/ATS mailbox)"
    hit = _first(ACCOUNT_PHRASES, text)
    if hit:
        return "GENERAL", f"account notice /{hit}/"
    hit = _first(ALERT_PHRASES, text)
    if hit:
        return "JOB_ALERT", f"alert phrase /{hit}/"
    hit = _first(ACK[-1:], text)
    if hit:
        return "ACKNOWLEDGMENT", f"acknowledgment phrase /{hit}/"
    return "UNCLASSIFIED", "about a job, no rule matched"


def to_inbox_row(m: dict) -> dict:
    name, addr = parseaddr(m.get("sender") or m.get("from") or "")
    addr = addr.lower()
    cat, rule = classify(m)
    subject = _clean(m.get("subject"))
    text = " ".join(x for x in (_clean(m.get("snippet")), _body(m)) if x)
    title = extract_title(subject, text) if cat in OUTCOME_CATEGORIES else ""
    strong = extract_company(subject, text) or company_from_display(name)
    weak = company_from_ats_mailbox(addr) or (
        company_from_person_domain(addr) if cat in OUTCOME_CATEGORIES and not is_automated(addr, name) else "")
    app = None
    if strong and cat in OUTCOME_CATEGORIES:
        app = {"companyName": strong, "trackedApplication": {"positionTitle": title} if title else None}
    return {
        "id": m.get("id", ""), "threadId": m.get("threadId", ""), "from": addr,
        "fromName": strong or weak or (name or None), "subject": subject,
        "snippet": _clean(m.get("snippet"))[:300], "receivedAt": _received(m),
        "category": cat, "application": app, "rule": rule,
    }


def convert(data, *, keep_all: bool = False) -> tuple[list[dict], Counter]:
    """Gmail connector JSON -> (inbox rows for outcomes.py, count per category)."""
    rows, counts = [], Counter()
    for m in load_messages(data):
        labels = set(m.get("labelIds") or [])
        if "SENT" in labels or "DRAFT" in labels:
            counts["SKIPPED_OWN"] += 1
            continue
        row = to_inbox_row(m)
        counts[row["category"]] += 1
        if keep_all or row["category"] != "NOT_JOB":
            rows.append(row)
    return rows, counts


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.gmail_inbox",
                                description="Classify Gmail messages into outcome categories for outcomes.py")
    p.add_argument("gmail", help="JSON saved from the Gmail connector (search_threads / get_thread output)")
    p.add_argument("--out", help="write inbox rows here (the --inbox input of auto_apply.v2.outcomes)")
    p.add_argument("--keep-all", action="store_true", help="also write NOT_JOB messages")
    a = p.parse_args(argv)
    with open(a.gmail) as f:
        rows, counts = convert(json.load(f), keep_all=a.keep_all)
    for cat in ALL_CATEGORIES + ("SKIPPED_OWN",):
        if counts[cat]:
            print(f"{cat:18} {counts[cat]}")
    unclassified = [r for r in rows if r["category"] == "UNCLASSIFIED"]
    if unclassified:
        print("unclassified (read these):")
        for r in unclassified:
            print(f"  {r['receivedAt'][:10]}  {r['from'][:40]:40} {r['subject'][:70]}")
    if a.out:
        with open(a.out, "w") as f:
            json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
