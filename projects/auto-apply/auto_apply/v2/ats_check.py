"""Read a resume PDF the way an applicant tracking system (ATS) does, and flag problems.

An ATS reads the PDF's text layer, not the picture. Checks:
- text extracts at all, with no (cid:NN) or replacement characters
- email and phone appear as plain text
- every date range uses a plain hyphen: a year joined to an en-dash ("2023 – 2024", what
  LaTeX makes from "--") is reported to be dropped by some Workday imports
- the main sections appear in the order the page shows them
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from ..guard import pdf_text

DASHES = "‐‑‒–—―−"
_RANGE = re.compile(rf"((?:[A-Z][a-z]{{2,8}}\.? )?\d{{4}})\s*([{DASHES}])\s*((?:[A-Z][a-z]{{2,8}}\.? )?\d{{4}}|Present|Current|Now|Graduated)")
SECTIONS = ["summary", "education", "skills", "experience", "projects"]


@dataclass
class AtsReport:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dash_ranges: list[str] = field(default_factory=list)


def check_text(text: str, email: str, phone: str) -> AtsReport:
    rep = AtsReport(ok=True)
    if len(text.strip()) < 200:
        rep.problems.append("almost no text extracted: the ATS would see an empty resume")
    if "(cid:" in text or "�" in text:
        rep.problems.append("garbled characters in the text layer ((cid:..) or �)")
    if email and email.lower() not in text.lower():
        rep.problems.append(f"email {email} is not in the text layer")
    digits = re.sub(r"\D", "", phone or "")[-10:]
    if digits and digits not in re.sub(r"\D", "", text):
        rep.problems.append("phone number is not in the text layer")
    for m in _RANGE.finditer(text):
        rep.dash_ranges.append(f"{m.group(0)!r} uses U+{ord(m.group(2)):04X}")
    if rep.dash_ranges:
        rep.problems.append(f"{len(rep.dash_ranges)} date range(s) use a dash other than '-': write them with a plain hyphen")
    low = text.lower()
    found = [(low.find(s), s) for s in SECTIONS if s in low]
    order = [s for _, s in sorted(found)]
    if order != [s for s in SECTIONS if s in order]:
        rep.warnings.append(f"sections read in this order: {', '.join(order)}")
    rep.ok = not rep.problems
    return rep


def check_pdf(path: str, email: str, phone: str) -> AtsReport:
    return check_text(pdf_text(path), email, phone)


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.ats_check")
    p.add_argument("pdf", nargs="+")
    p.add_argument("--email", required=True)
    p.add_argument("--phone", required=True)
    a = p.parse_args(argv)
    bad = 0
    for path in a.pdf:
        rep = check_pdf(path, a.email, a.phone)
        print(("PASS " if rep.ok else "FAIL ") + path)
        for x in rep.problems:
            print("  problem:", x)
        for x in rep.dash_ranges:
            print("    ", x)
        for x in rep.warnings:
            print("  note:", x)
        bad += not rep.ok
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
