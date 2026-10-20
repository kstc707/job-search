"""Pick the job title each resume entry shows, from the posting's role family.

Sai's roles were broader than one title, so a resume may add a focus to a title when that
matches the posting, e.g. "Data Analyst (Business Intelligence)" for a BI Analyst posting.
The rules:

- Variants come only from Sai's list (runs/titles.json, copied from the Notion Profile
  page). Nothing is generated here.
- Every variant keeps the base title verbatim. Application forms send the profile's base
  title and background checks return the employer's title, so the resume must still
  carry it; the gate's fixed-title check keeps passing.
- A job marked "fixed" (the Data Analyst Intern role) never changes.
- A variant is used only where it adds something: when the posting's family has one in
  Sai's list. Otherwise the base title stays (e.g. TCS "Data Analyst" for a Data Analyst
  posting already says it best).

runs/titles.json:
    {"jobs": [{"employer": "...", "base": "Data Analyst Intern", "fixed": true},
              {"employer": "...", "base": "Data Analyst",
               "variants": {"bi": "Data Analyst (Business Intelligence)", ...}}]}
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass

# Checked in order; the first match is the posting's family.
FAMILIES: list[tuple[str, re.Pattern[str]]] = [
    ("ml_ai", re.compile(r"\b(machine learning|ml|ai|artificial intelligence|llm|gen ?ai|generative|"
                         r"nlp|deep learning|agentic|mlops)\b", re.I)),
    ("data_science", re.compile(r"\b(data scien\w*|scientist|statistician|statistical|quantitative|"
                                r"decision scien\w*)\b", re.I)),
    ("data_engineering", re.compile(r"\b(data engineer\w*|analytics engineer\w*|etl|elt|data platform|"
                                    r"data pipelines?|data integration)\b", re.I)),
    ("bi", re.compile(r"\b(business intelligence|bi|power bi|tableau|dashboards?|visuali[sz]ation)\b", re.I)),
    ("product", re.compile(r"\b(product (analyst|analytics)|growth|user analytics|marketing analy\w*|"
                           r"customer insights?|insights analyst)\b", re.I)),
    ("business_analyst", re.compile(r"\b(business (systems |process )?analyst|operations analyst|"
                                    r"process analyst|systems analyst)\b", re.I)),
    ("reporting", re.compile(r"\b(reporting|report analyst|mis analyst)\b", re.I)),
    ("data_analyst", re.compile(r"\b(data analy\w*|analytics|analyst)\b", re.I)),
]
OTHER = "other"


def family(posting_title: str) -> str:
    for name, rx in FAMILIES:
        if rx.search(posting_title or ""):
            return name
    return OTHER


def validate(config: dict) -> None:
    """Raise ValueError when a variant drops its base title or names an unknown family."""
    known = {name for name, _ in FAMILIES} | {OTHER}
    for job in config.get("jobs", []):
        base = (job.get("base") or "").strip()
        if not base:
            raise ValueError(f"{job.get('employer')!r}: missing base title")
        if job.get("fixed") and job.get("variants"):
            raise ValueError(f"{base!r} is fixed and cannot have variants")
        for fam, title in (job.get("variants") or {}).items():
            if fam not in known:
                raise ValueError(f"{base!r}: unknown family {fam!r} (known: {', '.join(sorted(known))})")
            if base.lower() not in title.lower():
                raise ValueError(f"variant {title!r} must keep the title {base!r} verbatim")


@dataclass
class Choice:
    employer: str
    title: str
    changed: bool
    reason: str


def choose(config: dict, posting_title: str) -> tuple[str, list[Choice]]:
    validate(config)
    fam = family(posting_title)
    out = []
    for job in config.get("jobs", []):
        employer, base = job.get("employer") or "", job["base"].strip()
        variant = (job.get("variants") or {}).get(fam)
        if job.get("fixed"):
            out.append(Choice(employer, base, False, "fixed title"))
        elif variant:
            out.append(Choice(employer, variant, True, f"posting family {fam}"))
        else:
            out.append(Choice(employer, base, False, f"no variant for {fam}: base title adds the most"))
    return fam, out


def check_text(text: str, choices: list[Choice]) -> list[str]:
    """Errors for chosen titles missing from the resume text."""
    lower = " ".join(text.split()).lower()
    return [f"title '{c.title}' ({c.employer}) is not on the resume" for c in choices
            if c.title.lower() not in lower]


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.titles")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("choose", help="titles to put on the resume for a posting")
    c.add_argument("posting_title")
    c.add_argument("--config", default="runs/titles.json")
    c.add_argument("--json", action="store_true")
    k = sub.add_parser("check", help="the built resume carries the chosen titles")
    k.add_argument("pdf")
    k.add_argument("--posting-title", required=True)
    k.add_argument("--config", default="runs/titles.json")
    a = p.parse_args(argv)
    try:
        fam, choices = choose(json.load(open(a.config)), a.posting_title)
    except ValueError as e:
        print(f"BLOCKED: {e}")
        return 2
    if a.cmd == "choose":
        if a.json:
            print(json.dumps({"family": fam, "titles": [asdict(x) for x in choices]}, indent=1))
        else:
            print(f"family: {fam}")
            for x in choices:
                print(f"  {x.employer[:40]:40} {x.title:45} ({x.reason})")
        return 0
    from auto_apply.guard import pdf_text
    errors = check_text(pdf_text(a.pdf), choices)
    for e in errors:
        print(f"ERROR   title: {e}")
    print("PASS" if not errors else "FAIL")
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
