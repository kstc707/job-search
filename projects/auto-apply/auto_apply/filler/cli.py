"""Plan, fill and (optionally) submit a Greenhouse, Lever or Ashby application.

    python -m auto_apply.filler.cli plan <job url> --pdf runs/<job>/resume.pdf
    python -m auto_apply.filler.cli fill <job url> --pdf runs/<job>/resume.pdf [--submit]

Hands-free (see auto_apply/voice.py): `plan --speak` prints every answer as sentences to read
to Sai and remembers that read-back; `fill --submit --voice-confirm "<what Sai said>"` sends
only if he said "submit <company>" after hearing exactly this plan.

Greenhouse questions come from its public API; Lever and Ashby forms are read from the page.
`plan` only reads the form and prints every field's answer and source.
`fill` opens a browser, fills, verifies and screenshots; it submits only with --submit,
and never when a required field is unanswered or a field failed to fill.
Exit codes: 0 ok, 2 failed fill/submit, 3 blocked on answers you must provide,
4 spoken go-ahead refused (nothing was opened or sent).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..cli import _load_rules
from ..guard import check_answers
from .. import voice
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


def write_questions(plan, path: Path) -> None:
    """Questions still open, with their options, for drafting per-job answers.

    The drafts go into answers.json next to it as {"exact label": answer}; nothing in
    questions.json is ever sent to a form.
    """
    rows = [{"label": r.question.label, "required": r.question.required, "type": r.field.type,
             "options": [o.label for o in r.field.options], "status": r.status, "note": r.note}
            for r in plan if r.status in ("ask", "missing", "no-option") or r.blocking]
    path.write_text(json.dumps({
        "_how": "Draft answers from facts.md only, show Sai, then save them to answers.json in this "
                "folder as {\"exact label\": answer}. Choice questions: use one of the options. "
                "Leave out anything Sai must decide.",
        "questions": rows}, indent=2))


def _gate(plan, cmd: str, test_fill: bool = False, questions_file: Path | None = None,
          spoken: "_Spoken | None" = None) -> int | None:
    """Print the plan; return an exit code if the run stops here, None to go on and fill."""
    _print_plan(plan)
    blocking = [r for r in plan if r.blocking]
    if spoken is not None:
        code = spoken.handle(plan, cmd, bool(blocking))
        if code is not None:
            return code
    if questions_file is not None:
        write_questions(plan, questions_file)
    if blocking:
        print(f"\nBLOCKED: {len(blocking)} required question(s) need an approved answer:")
        for r in blocking:
            print(f"  - {r.question.label}  [{r.status}] {r.note}")
        if questions_file is not None:
            print(f"open questions written to {questions_file}")
        if not (test_fill and cmd == "fill"):
            return 3
        print("--test-fill: filling the answered fields anyway; nothing will be submitted")
    if cmd == "plan":
        print("\nREADY: every required question has an approved answer")
        return 0
    return None


class _Spoken:
    """Voice mode: read the plan back (plan --speak) or check the go-ahead (fill --voice-confirm)."""

    def __init__(self, runs: Path, url: str, pdf: Path, company: str, title: str,
                 speak: bool, confirm: str | None):
        self.runs, self.url, self.pdf = runs, url, pdf
        self.company, self.title, self.speak, self.confirm = company, title, speak, confirm

    def handle(self, plan, cmd: str, blocked: bool) -> int | None:
        digest = voice.plan_digest(plan, self.pdf)
        if self.speak:
            print("\nSPOKEN:\n" + voice.speak_plan(plan, self.company, self.title))
            if not blocked:
                voice.record_readback(self.runs, self.url, self.company, self.title, digest, "filler", self.pdf)
        if cmd == "fill" and self.confirm is not None and not blocked:
            ok, reason = voice.check_confirmation(self.confirm, voice.Pending.load(self.runs), self.url, digest)
            print(("CONFIRMED: " if ok else "REFUSED: ") + reason)
            if not ok:
                return 4
            voice.Pending.clear(self.runs)
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
    p.add_argument("--company", help="company name to speak and to expect in 'submit <company>' "
                                     "(default: from the form or the board slug)")
    p.add_argument("--speak", action="store_true",
                   help="voice mode: print the plan as sentences to read to Sai and remember the read-back")
    p.add_argument("--voice-confirm", metavar="TRANSCRIPT",
                   help="voice mode: Sai's words; --submit goes ahead only if he said 'submit <company>' "
                        "after hearing this exact plan")
    a = p.parse_args(argv)
    if a.test_fill and a.submit:
        p.error("--test-fill never submits; drop --submit")
    if a.voice_confirm is not None and not a.submit:
        p.error("--voice-confirm is the go-ahead for --submit; add --submit")

    runs, pdf = Path(a.runs), Path(a.pdf)
    job_answers = Path(a.job_answers) if a.job_answers else pdf.parent / "answers.json"
    bank = AnswerBank.load(runs / "profile.json", runs / "answers.json",
                           {"resume": str(pdf), "cover_letter": a.cover_letter}, job_answers)
    shot = str(pdf.parent / "form-filled.png")
    questions_file = pdf.parent / "questions.json"

    # Drafted per-job answers face the same never-claim rules as the resume.
    if job_answers.exists():
        bad = [f for f in check_answers(json.loads(job_answers.read_text()), _load_rules(runs)) if f.severity == "error"]
        if bad:
            print(f"BLOCKED: {len(bad)} drafted answer(s) in {job_answers} break the rules:")
            for f in bad:
                print(f"  - [{f.rule}] {f.detail}")
            return 3
    ats = detect_ats(a.url)
    if ats in ("lever", "ashby"):
        session = open_and_plan(a.url, ats, bank)
        try:
            print(f"{session.title} ({len(session.questions)} questions, read from the {ats} page)")
            spoken = _spoken(a, runs, pdf, _company_from_url(a.url), session.title)
            code = _gate(session.plan, a.cmd, a.test_fill, questions_file, spoken)
            if code is not None:
                return code
            rep = session.fill(shot, submit=a.submit)
        finally:
            session.close()
    else:
        data, questions = fetch_form(a.url)
        print(f"{data.get('company_name') or ''} — {data['title']} ({len(questions)} questions)")
        plan = bank.plan(questions)
        spoken = _spoken(a, runs, pdf, data.get("company_name") or _company_from_url(a.url), data["title"])
        code = _gate(plan, a.cmd, a.test_fill, questions_file, spoken)
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


def _company_from_url(url: str) -> str:
    """Board slug as a stand-in company name (jobs.ashbyhq.com/acme-labs/... → "Acme Labs")."""
    from urllib.parse import urlsplit
    parts = [x for x in urlsplit(url).path.split("/") if x]
    return parts[0].replace("-", " ").replace("_", " ").title() if parts else ""


def _spoken(a, runs: Path, pdf: Path, company: str, title: str) -> "_Spoken | None":
    if not (a.speak or a.voice_confirm is not None):
        return None
    return _Spoken(runs, a.url, pdf, a.company or company, title, a.speak, a.voice_confirm)


if __name__ == "__main__":
    sys.exit(main())
