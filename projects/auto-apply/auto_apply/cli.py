"""Command-line entry points the agent calls between Tsenta MCP steps.

    python -m auto_apply.cli profile  runs/profile_raw.json -o runs/profile.json
    python -m auto_apply.cli gate     runs/<job>/resume.pdf --url URL [--job-id ID]
    python -m auto_apply.cli upload   runs/<job>/resume.pdf UPLOAD_URL
    python -m auto_apply.cli record   --company C --title T --url URL --application-id A
    python -m auto_apply.cli list

Shared state lives in `runs/` (git-ignored): profile.json, instructions.txt,
never_claim.txt (optional, one term per line or comma-separated), ledger.jsonl.
Exit codes: 0 ok, 1 usage/IO error, 2 blocked by a check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from .guard import GuardRules, _split_terms, check_resume, parse_instructions, pdf_text
from .ledger import Entry, Ledger
from .profile import build_apply_profile, set_path
from .upload import put_pdf

RUNS = Path(__file__).resolve().parent.parent / "runs"
DEFAULT_DAILY_CAP = 15


def _load_rules(runs: Path) -> GuardRules:
    instructions = runs / "instructions.txt"
    rules = parse_instructions(instructions.read_text() if instructions.exists() else None)
    extra = runs / "never_claim.txt"
    if extra.exists():
        for line in extra.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                rules.never_claim.extend(_split_terms(line))
    # De-duplicate case-insensitively, keeping the first spelling.
    unique: dict[str, str] = {}
    for term in rules.never_claim:
        unique.setdefault(term.lower(), term)
    rules.never_claim = list(unique.values())
    return rules


def cmd_profile(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.source).read_text())
    try:
        profile = build_apply_profile(raw)
        for assignment in args.set or []:
            path, _, value = assignment.partition("=")
            if not path or not _:
                raise ValueError(f"--set needs path=value, got '{assignment}'")
            set_path(profile, path, value)
    except ValueError as e:
        print(f"BLOCKED: {e}")
        return 2
    out = Path(args.out) if args.out else Path(args.runs) / "profile.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, indent=2))
    print(f"ok: apply profile written to {out}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    runs = Path(args.runs)
    blocked = False
    ledger = Ledger(runs / "ledger.jsonl")

    prior = ledger.find(job_id=args.job_id or "", url=args.url or "")
    if prior:
        print(f"BLOCKED duplicate: already applied {prior.at[:10]} ({prior.company} – {prior.title})")
        blocked = True
    used = ledger.count_on(date.today())
    if used >= args.cap:
        print(f"BLOCKED daily cap: {used}/{args.cap} applications today")
        blocked = True

    profile = json.loads((runs / "profile.json").read_text())
    findings = check_resume(pdf_text(args.pdf), profile, _load_rules(runs))
    for f in findings:
        if args.arm == "B" and f.rule == "fixed-title":
            f.severity = "warning"  # resume experiment arm B writes titles from the posting
        print(f"{f.severity.upper():7} {f.rule}: {f.detail}")
        blocked |= f.severity == "error"

    print("BLOCKED" if blocked else "PASS", f"({len(findings)} findings, {used}/{args.cap} today)")
    return 2 if blocked else 0


def cmd_upload(args: argparse.Namespace) -> int:
    status = put_pdf(args.upload_url, args.pdf)
    print(f"upload HTTP {status}")
    return 0 if 200 <= status < 300 else 1


def cmd_record(args: argparse.Namespace) -> int:
    sha = hashlib.sha256(Path(args.pdf).read_bytes()).hexdigest() if args.pdf else ""
    Ledger(Path(args.runs) / "ledger.jsonl").add(Entry(
        company=args.company, title=args.title, url=args.url or "", job_id=args.job_id or "",
        application_id=args.application_id or "", status=args.status, resume_sha256=sha,
        note=args.note or "",
    ))
    print("recorded")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for e in Ledger(Path(args.runs) / "ledger.jsonl").entries():
        print(f"{e.at[:16]}  {e.status:12} {e.company} – {e.title}  {e.application_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="auto_apply")
    p.add_argument("--runs", default=str(RUNS), help="state directory (default: ./runs)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("profile", help="build apply profile from a get-resume-profile response")
    s.add_argument("source")
    s.add_argument("-o", "--out", help="default: <runs>/profile.json")
    s.add_argument("--set", action="append", metavar="PATH=VALUE",
                   help="override a profile field the Tsenta tools cannot edit, "
                        "e.g. diversityEquityInclusion.gender=Male (repeatable)")
    s.set_defaults(func=cmd_profile)

    s = sub.add_parser("gate", help="all pre-submit checks; exit 2 if anything blocks")
    s.add_argument("pdf")
    s.add_argument("--url")
    s.add_argument("--job-id")
    s.add_argument("--cap", type=int, default=DEFAULT_DAILY_CAP)
    s.add_argument("--arm", choices=["A", "B"], default="A",
                   help="resume experiment arm; B allows titles written from the posting")
    s.set_defaults(func=cmd_gate)

    s = sub.add_parser("upload", help="PUT the PDF to a presigned upload URL")
    s.add_argument("pdf")
    s.add_argument("upload_url")
    s.set_defaults(func=cmd_upload)

    s = sub.add_parser("record", help="log an application in the ledger")
    for name in ("--company", "--title"):
        s.add_argument(name, required=True)
    for name in ("--url", "--job-id", "--application-id", "--pdf", "--note"):
        s.add_argument(name)
    s.add_argument("--status", default="SUBMITTED")
    s.set_defaults(func=cmd_record)

    s = sub.add_parser("list", help="show the ledger")
    s.set_defaults(func=cmd_list)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
