"""Plan, fill and (optionally) submit a Greenhouse, Lever or Ashby application.

    python -m auto_apply.filler.cli plan <job url> --pdf runs/<job>/resume.pdf
    python -m auto_apply.filler.cli fill <job url> --pdf runs/<job>/resume.pdf [--submit]

Greenhouse questions come from its public API; Lever and Ashby forms are read from the page.
`plan` only reads the form and prints every field's answer and source.
`fill` opens a browser, fills, verifies and screenshots; it submits only with --submit,
and never when a required field is unanswered or a field failed to fill.
Exit codes: 0 ok, 2 failed fill/submit, 3 blocked on answers you must provide.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .answers import AnswerBank
from .domform import detect_ats, open_and_plan
from .greenhouse import fill_form
from .schema import fetch_form

RUNS = Path(__file__).resolve().parents[2] / "runs"


def _print_plan(plan) -> None:
    for r in plan:
        mark = {"fill": "✓", "skip": "·", "ask": "?", "missing": "✗", "no-option": "✗"}[r.status]
        req = "*" if r.question.required else " "
        val = r.value if not isinstance(r.value, str) or len(r.value) < 60 else r.value[:57] + "..."
        print(f" {mark}{req} {r.question.label[:62]:62} {r.status:9} {val if val is not None else ''}"
              f"{'  ← ' + r.note if r.note and r.status != 'fill' else ''}")


def _gate(plan, cmd: str, test_fill: bool = False) -> int | None:
    """Print the plan; return an exit code if the run stops here, None to go on and fill."""
    _print_plan(plan)
    blocking = [r for r in plan if r.blocking]
    if blocking:
        print(f"\nBLOCKED: {len(blocking)} required question(s) need an approved answer:")
        for r in blocking:
            print(f"  - {r.question.label}  [{r.status}] {r.note}")
        if not (test_fill and cmd == "fill"):
            return 3
        print("--test-fill: filling the answered fields anyway; nothing will be submitted")
    if cmd == "plan":
        print("\nREADY: every required question has an approved answer")
        return 0
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="filler")
    p.add_argument("cmd", choices=["plan", "fill"])
    p.add_argument("url")
    p.add_argument("--pdf", required=True)
    p.add_argument("--cover-letter")
    p.add_argument("--job-answers", help="per-job answers JSON (default: <pdf dir>/answers.json)")
    p.add_argument("--runs", default=str(RUNS))
    p.add_argument("--submit", action="store_true")
    p.add_argument("--test-fill", action="store_true",
                   help="testing only: fill even when blocked (never submits), to check the filling itself")
    a = p.parse_args(argv)
    if a.test_fill and a.submit:
        p.error("--test-fill never submits; drop --submit")

    runs, pdf = Path(a.runs), Path(a.pdf)
    job_answers = Path(a.job_answers) if a.job_answers else pdf.parent / "answers.json"
    bank = AnswerBank.load(runs / "profile.json", runs / "answers.json",
                           {"resume": str(pdf), "cover_letter": a.cover_letter}, job_answers)
    shot = str(pdf.parent / "form-filled.png")
    ats = detect_ats(a.url)
    if ats in ("lever", "ashby"):
        session = open_and_plan(a.url, ats, bank)
        try:
            print(f"{session.title} ({len(session.questions)} questions, read from the {ats} page)")
            code = _gate(session.plan, a.cmd, a.test_fill)
            if code is not None:
                return code
            rep = session.fill(shot, submit=a.submit)
        finally:
            session.close()
    else:
        data, questions = fetch_form(a.url)
        print(f"{data.get('company_name') or ''} — {data['title']} ({len(questions)} questions)")
        plan = bank.plan(questions)
        code = _gate(plan, a.cmd, a.test_fill)
        if code is not None:
            return code
        rep = fill_form(a.url, plan, shot, submit=a.submit)
    print(f"\nfilled {len(rep.filled)} fields; failed {len(rep.failed)}; not shown by the form {len(rep.hidden)}; "
          f"captcha on page: {rep.captcha}")
    for f in rep.failed:
        print(f"  FAILED {f}")
    print(f"screenshot: {rep.screenshot}")
    if a.submit:
        print("SUBMITTED" if rep.submitted else "NOT SUBMITTED", "-", rep.confirmation[:200])
        return 0 if rep.submitted else 2
    return 2 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
