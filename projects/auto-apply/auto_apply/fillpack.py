"""Build the JSON packs the Apply Autofill browser extension loads (projects/autofill-extension).

    python -m auto_apply.fillpack profile --profile runs/profile.json --answers runs/answers.json \\
        [--resume runs/default-resume.pdf] --out runs/profile-pack.json
    python -m auto_apply.fillpack job --pdf runs/<job>/resume.pdf --url <apply url> \\
        --title "Data Analyst" --company Acme [--answers runs/<job>/answers.json] \\
        [--filename Alex-Rivera-Resume.pdf] --out runs/<job>/job-pack.json

The profile pack (loaded once) holds the profile and the ordered answer rules from
runs/answers.json, so the extension answers exactly as filler/answers.py does. The job pack
(per job) holds the job, the per-job answers {"exact label": answer} and the tailored PDF as
base64. Everything is validated here, before it reaches a browser: the PDF (header, trailer,
5 MB), every rule's regex (Python and the JavaScript the extension runs), and drafted per-job
answers against the never-claim list, like `filler.cli fill` does.

Packs hold personal data: write them under runs/ (git-ignored).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .filler.answers import ASK
from .upload import MAX_BYTES, validate_pdf

PROFILE_KIND = "autofill-profile-pack"
JOB_KIND = "autofill-job-pack"
VERSION = 1

RUNS = Path(__file__).resolve().parents[1] / "runs"

# Python regex syntax the extension's translator (content/answers.js pyRegex) cannot express.
_JS_UNSUPPORTED = [
    (re.compile(r"\(\?>"), "atomic group (?>...)"),
    (re.compile(r"(?<!\\)[*+?}]\+"), "possessive quantifier"),
    (re.compile(r"\(\?\("), "conditional group (?(...)...)"),
    (re.compile(r"(?<!^)\(\?[aiLmsux-]+[:)]"), "inline flags after the start"),
    (re.compile(r"^\(\?[aiLmsu]*x"), "verbose (?x) pattern"),
    (re.compile(r"\\z"), r"\z"),
]


class PackError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def check_rules(rules: Any) -> list[dict]:
    """The answers.json "rules" list, checked: each has a valid `match` regex and an `answer`."""
    if not isinstance(rules, list):
        raise PackError('"rules" must be a list of {"match", "answer", "note"}')
    problems = []
    for i, r in enumerate(rules):
        where = f"rule {i + 1}"
        if not isinstance(r, dict) or not isinstance(r.get("match"), str) or not r["match"]:
            problems.append(f'{where}: needs a non-empty "match" string')
            continue
        where = f"rule {i + 1} /{r['match']}/"
        try:
            re.compile(r["match"], re.IGNORECASE)
        except re.error as e:
            problems.append(f"{where}: not a valid regex ({e})")
            continue
        for pat, what in _JS_UNSUPPORTED:
            if pat.search(r["match"]):
                problems.append(f"{where}: uses {what}, which the browser extension cannot run")
        if "answer" not in r:
            problems.append(f'{where}: no "answer" (use "{ASK}" to always ask, null to leave blank)')
            continue
        a = r["answer"]
        ok = a is None or isinstance(a, (str, int, float, bool)) or (
            isinstance(a, list) and a and all(isinstance(x, (str, int, float, bool)) for x in a))
        if not ok:
            problems.append(f"{where}: answer must be text, a number, a list of alternatives, or null")
        if "note" in r and not isinstance(r["note"], str):
            problems.append(f'{where}: "note" must be text')
    if problems:
        raise PackError("invalid rules:\n  " + "\n  ".join(problems))
    return [{k: r[k] for k in ("match", "answer", "note") if k in r} for r in rules]


def check_profile(profile: Any) -> dict:
    if not isinstance(profile, dict):
        raise PackError("profile must be a JSON object")
    pi = profile.get("personalInformation")
    if not isinstance(pi, dict):
        raise PackError("profile has no personalInformation")
    missing = [k for k in ("firstName", "lastName", "email") if not pi.get(k)]
    if missing:
        raise PackError(f"profile.personalInformation is missing {', '.join(missing)}")
    for key in ("workExperience", "education"):
        if key in profile and not isinstance(profile[key], list):
            raise PackError(f"profile.{key} must be a list")
    return profile


def pdf_entry(path: Path, filename: str | None = None) -> dict:
    """A validated PDF as the extension stores it: name, size, sha256 and base64 bytes."""
    if not path.exists():
        raise PackError(f"no such PDF: {path}")
    data = path.read_bytes()
    try:
        validate_pdf(data, MAX_BYTES)
    except ValueError as e:
        raise PackError(f"{path}: {e}") from e
    name = filename or path.name
    if not name.lower().endswith(".pdf") or "/" in name or "\\" in name:
        raise PackError(f"resume file name must be a plain *.pdf name, got {name!r}")
    return {
        "filename": name,
        "type": "application/pdf",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "base64": base64.b64encode(data).decode("ascii"),
    }


def build_profile_pack(profile: dict, rules: list, resume: Path | None = None) -> dict:
    pack = {
        "kind": PROFILE_KIND,
        "version": VERSION,
        "createdAt": _now(),
        "profile": check_profile(profile),
        "rules": check_rules(rules),
    }
    if resume is not None:
        pack["defaultResume"] = pdf_entry(resume)
    return pack


def check_job_answers(answers: Any) -> dict:
    """{"exact question label": answer}; keys starting with "_" are comments and dropped."""
    if not isinstance(answers, dict):
        raise PackError('per-job answers must be {"exact question label": answer}')
    out = {}
    for label, a in answers.items():
        if label.startswith("_"):
            continue
        ok = a is None or isinstance(a, (str, int, float, bool)) or (
            isinstance(a, list) and all(isinstance(x, (str, int, float, bool)) for x in a))
        if not ok:
            raise PackError(f"answer for {label!r} must be text, a number, a list, or null")
        out[label] = a
    return out


def build_job_pack(pdf: Path, url: str, title: str, company: str,
                   answers: dict | None = None, filename: str | None = None) -> dict:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise PackError(f"--url must be the http(s) apply link, got {url!r}")
    if not title.strip() or not company.strip():
        raise PackError("--title and --company must not be empty")
    return {
        "kind": JOB_KIND,
        "version": VERSION,
        "createdAt": _now(),
        "job": {"url": url, "title": title.strip(), "company": company.strip()},
        "answers": check_job_answers(answers or {}),
        "resume": pdf_entry(pdf, filename),
    }


def _read_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise PackError(f"no {what} file: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise PackError(f"{path} is not valid JSON: {e}") from e


def _write(pack: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=1, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fillpack", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("profile", help="profile + answer rules (load once)")
    pp.add_argument("--profile", required=True, type=Path)
    pp.add_argument("--answers", required=True, type=Path, help='runs/answers.json with a "rules" list')
    pp.add_argument("--resume", type=Path, help="default resume PDF, used when no job pack is loaded")
    pp.add_argument("--out", required=True, type=Path)

    pj = sub.add_parser("job", help="one job: URL, title, company, per-job answers, tailored PDF")
    pj.add_argument("--pdf", required=True, type=Path)
    pj.add_argument("--url", required=True)
    pj.add_argument("--title", required=True)
    pj.add_argument("--company", required=True)
    pj.add_argument("--answers", type=Path, help='per-job {"exact label": answer} JSON')
    pj.add_argument("--filename", help="file name the employer sees (default: the PDF's name)")
    pj.add_argument("--runs", type=Path, default=RUNS, help="where instructions.txt / never_claim.txt live")
    pj.add_argument("--out", required=True, type=Path)

    a = p.parse_args(argv)
    try:
        if a.cmd == "profile":
            answers = _read_json(a.answers, "answers")
            rules = answers.get("rules") if isinstance(answers, dict) else None
            pack = build_profile_pack(_read_json(a.profile, "profile"), rules, a.resume)
            _write(pack, a.out)
            extra = f", default resume {pack['defaultResume']['filename']}" if "defaultResume" in pack else ""
            print(f"profile pack: {len(pack['rules'])} rules{extra} -> {a.out}")
            return 0

        job_answers = _read_json(a.answers, "per-job answers") if a.answers else {}
        pack = build_job_pack(a.pdf, a.url, a.title, a.company, job_answers, a.filename)
        if pack["answers"]:
            # Drafted answers face the same never-claim rules as the resume (as in filler.cli).
            from .cli import _load_rules
            from .guard import check_answers
            bad = [f for f in check_answers(pack["answers"], _load_rules(a.runs)) if f.severity == "error"]
            if bad:
                print(f"BLOCKED: {len(bad)} per-job answer(s) break the rules:", file=sys.stderr)
                for f in bad:
                    print(f"  - [{f.rule}] {f.detail}", file=sys.stderr)
                return 3
        _write(pack, a.out)
        print(f"job pack: {pack['job']['title']} @ {pack['job']['company']}, {len(pack['answers'])} answers, "
              f"resume {pack['resume']['filename']} ({pack['resume']['bytes']} bytes) -> {a.out}")
        return 0
    except PackError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
