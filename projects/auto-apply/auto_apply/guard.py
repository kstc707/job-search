"""Pre-submit checks on a tailored resume.

Once Tsenta has the PDF it goes to the employer unchanged, so this is the last point
where a fabricated tool, a changed job title, or a banned phrase can be caught.

Rules come from two places the user already maintains:
- Tsenta's `resumeInstructions` (get-apply-preferences): "Never claim: A, B, C." and
  quoted phrases after "never" / "no" / "do not".
- An optional extra never-claim list (e.g. the "Do not claim" section of a facts file).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NEGATION = re.compile(r"\b(never|no|not|don't|avoid)\b", re.IGNORECASE)
_QUOTED = re.compile(r"'([^']{2,80})'")


@dataclass
class GuardRules:
    never_claim: list[str] = field(default_factory=list)
    banned_phrases: list[str] = field(default_factory=list)


@dataclass
class Finding:
    severity: str  # "error" blocks the submit; "warning" needs a human look
    rule: str
    detail: str


def _split_terms(raw: str) -> list[str]:
    """Split "Docker, GCP/BigQuery/Vertex AI, CI/CD" into individual terms.

    Slash groups split into their parts unless a part is shorter than 3 characters,
    so "CI/CD" stays whole (matching bare "CI" would flag far too much).
    """
    terms: list[str] = []
    for chunk in raw.split(","):
        chunk = chunk.strip().strip(".").strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split("/")]
        if len(parts) > 1 and all(len(p) >= 3 for p in parts):
            terms.extend(parts)
        else:
            terms.append(chunk)
    return terms


def parse_instructions(instructions: str | None) -> GuardRules:
    """Derive guard rules from Tsenta's free-text resume instructions."""
    rules = GuardRules()
    if not instructions:
        return rules
    for sentence in _SENTENCE_SPLIT.split(instructions):
        m = re.match(r"\s*never claim\s*:\s*(.+)", sentence, re.IGNORECASE)
        if m:
            rules.never_claim.extend(_split_terms(m.group(1)))
            continue
        neg = _NEGATION.search(sentence)
        if not neg:
            continue
        # Only quotes after the negation are banned: in "Call me a 'X', never a 'Y'",
        # X is the required wording and Y the banned one.
        for q in _QUOTED.finditer(sentence, neg.start()):
            rules.banned_phrases.append(q.group(1).strip())
    return rules


def _term_pattern(term: str) -> re.Pattern[str]:
    # Word boundaries only where the term starts/ends with a word character, so
    # "CI/CD" and "C++" still match.
    left = r"(?<![\w])" if term[:1].isalnum() else ""
    right = r"(?![\w])" if term[-1:].isalnum() else ""
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)  # re-join words hyphenated across lines
    return re.sub(r"\s+", " ", text).strip()


def pdf_text(pdf_path: str | Path) -> str:
    """Extract text with poppler's pdftotext (the same text an ATS parser sees)."""
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout


def _company_found(company: str, text_lower: str) -> bool:
    """Full name, or a leading part of at least 3 words ("University of Memphis" for
    "University of Memphis ITS Service Desk", which the merged resume entry uses)."""
    words = company.split()
    for n in range(len(words), 0, -1):
        if n < len(words) and n < 3:
            break
        if " ".join(words[:n]).lower() in text_lower:
            return True
    return False


def check_resume(text: str, profile: dict[str, Any], rules: GuardRules) -> list[Finding]:
    """Return findings for a resume's extracted text. No findings means safe to send."""
    findings: list[Finding] = []
    norm = normalize_text(text)
    lower = norm.lower()

    for term in rules.never_claim:
        if _term_pattern(term).search(norm):
            findings.append(Finding("error", "never-claim", f"resume mentions '{term}'"))

    for phrase in rules.banned_phrases:
        if _term_pattern(phrase).search(norm):
            findings.append(Finding("error", "banned-phrase", f"resume uses '{phrase}'"))

    for job in profile.get("workExperience", []):
        role, company = (job.get("role") or "").strip(), (job.get("company") or "").strip()
        if role and role.lower() not in lower:
            findings.append(Finding(
                "error", "fixed-title",
                f"title '{role}' ({company}) is not on the resume exactly as in the profile",
            ))
        if company and not _company_found(company, lower):
            findings.append(Finding(
                "warning", "fixed-employer", f"employer '{company}' not found on the resume",
            ))

    email = (profile.get("personalInformation") or {}).get("email")
    if email and email.lower() not in lower:
        findings.append(Finding(
            "warning", "contact-mismatch",
            f"profile email {email} (used on the form) is not the email on the resume",
        ))
    return findings


_AFFIRMATIVE = re.compile(r"^\s*(yes|y|true|i do|i have)\b", re.IGNORECASE)


def check_answers(answers: dict[str, Any], rules: GuardRules) -> list[Finding]:
    """Checks on drafted per-job form answers ({question label: answer}).

    A "Yes" to a question about a never-claim skill ("Do you have Tableau experience?"),
    or a free-text answer that names one, would claim it as surely as a resume bullet.
    Negated mentions ("I have not used Tableau") are flagged too: a person decides.
    """
    findings: list[Finding] = []
    for label, answer in answers.items():
        if answer is None or label.startswith("_"):
            continue
        text = " ".join(map(str, answer)) if isinstance(answer, list) else str(answer)
        for term in rules.never_claim:
            pat = _term_pattern(term)
            if pat.search(text) or (_AFFIRMATIVE.match(text) and pat.search(label)):
                findings.append(Finding("error", "answer-claims-never-claim",
                                        f"'{label[:70]}' → '{text[:60]}' claims '{term}'"))
        for phrase in rules.banned_phrases:
            if phrase.lower() in text.lower():
                findings.append(Finding("error", "answer-banned-phrase", f"'{label[:70]}' uses '{phrase}'"))
    return findings
