"""Hands-free mode: Sai drives the pipeline by voice and never has to look at the screen.

Three things change when nobody can read a screenshot or tap a button:

1. **Review by ear.** The screenshot review before submit becomes a spoken read-back of every
   answer that will be sent (`speak_plan` for our filler, `speak_tsenta` for Tsenta jobs).
2. **Approval by phrase.** A submit needs Sai to say "submit <company>" after that read-back.
   A bare "yes" is not enough: dictation picks up background talk, and "yes" could answer any
   question. `confirm` checks the phrase, that the read-back was of *exactly* the answers about
   to be sent (a digest), and that it is recent. Anything negative in the phrase ("don't",
   "wait", "cancel") stops it.
3. **A hands-on list.** Things a voice cannot do (captchas, setting a password, email
   verification links) are queued in `runs/voice/later.jsonl` for when Sai can use the phone.

    python -m auto_apply.voice url "jobs dot ashbyhq dot com slash acme slash 1 2 3"
    python -m auto_apply.voice readback-tsenta --pdf runs/<job>/resume.pdf --company C --title T --url URL
    python -m auto_apply.voice confirm --url URL "submit acme"
    python -m auto_apply.voice later add "captcha on Acme" --url URL
    python -m auto_apply.voice later list

The filler's read-back and confirmation are `filler.cli plan --speak` and
`filler.cli fill --submit --voice-confirm "<what Sai said>"`.
Exit codes: 0 ok, 2 refused (say why to Sai), 1 usage/IO error.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RUNS = Path(__file__).resolve().parent.parent / "runs"
READBACK_TTL = timedelta(minutes=30)

# ---------------------------------------------------------------- spoken URLs

_SPOKEN_SYMBOLS = [
    (r"\bcolon\s*(slash\s*slash|//)", "://"),
    (r"\bforward slash\b|\bslash\b", "/"),
    (r"\bdot\b|\bpoint\b|\bperiod\b", "."),
    (r"\bdash\b|\bhyphen\b|\bminus\b", "-"),
    (r"\bunderscore\b", "_"),
    (r"\bquestion mark\b", "?"),
    (r"\bequals\b|\bequal sign\b", "="),
    (r"\bampersand\b", "&"),
    (r"\bcolon\b", ":"),
]
_DIGITS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine".split())}
_DIGITS["oh"] = "0"


def normalize_spoken_url(text: str) -> str | None:
    """A URL from dictation ("jobs dot lever dot co slash acme"), or None if it isn't one.

    Dictation may already give "jobs.lever.co/acme" or put spaces inside it; both work.
    """
    s = text.strip().lower().rstrip(".!?")
    s = re.sub(r"^(the )?(link|url|posting|job) (is|at)\s+", "", s)
    for pattern, symbol in _SPOKEN_SYMBOLS:
        s = re.sub(pattern, f" {symbol} ", s)
    s = " ".join(_DIGITS.get(tok, tok) for tok in s.split())
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^(https?):?/*", r"\1://", s)
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    host = s.split("://", 1)[1].split("/", 1)[0]
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host):
        return None
    return s


# ---------------------------------------------------------------- read-backs


def _clean(text: str) -> str:
    """Plain words for a speech engine: no markdown, no stray symbols, no trailing colon."""
    t = re.sub(r"[*_`#>|]+", "", str(text))
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip(":").strip()


def _sentence(text: str) -> str:
    """End with a full stop unless it already ends with one (labels are often questions)."""
    t = _clean(text)
    return t if t[-1:] in ".?!" else t + "."


def _qa(label: str, value: Any) -> str:
    """'Authorized to work? Yes.' / 'Certifications: CFA.'"""
    label = _clean(label)
    return f"{label} {_sentence(_say_value(value))}" if label.endswith("?") else f"{label}: {_sentence(_say_value(value))}"


def _say_value(value: Any) -> str:
    if isinstance(value, list):
        return " and ".join(_clean(v) for v in value)
    return _clean(value)


def speak_plan(plan, company: str, title: str) -> str:
    """Every answer the filler will send, as sentences Sai can follow without a screen.

    Contact fields and files are grouped (they come from the profile Sai approved); every
    other answer is read out in full, because this read-back replaces the screenshot review.
    """
    company, title = _clean(company), _clean(title)
    lines = [f"{company}, {title}." if company else f"{title}."]
    profile = [r for r in plan if r.status == "fill" and r.source == "profile"]
    files = [r for r in plan if r.status == "fill" and r.source.startswith("file:")]
    answers = [r for r in plan if r.status == "fill" and r not in profile and r not in files]
    skipped = [r for r in plan if r.status == "skip"]
    blocking = [r for r in plan if r.blocking]

    if profile:
        lines.append("From your profile: " + ", ".join(_clean(r.question.label) for r in profile) + ".")
    for r in files:
        kind = r.source.split(":", 1)[1].replace("_", " ")
        lines.append(f"Attached: your tailored {kind}." if kind == "resume" else f"Attached: {kind}.")
    for i, r in enumerate(answers, 1):
        lines.append(f"{i}. {_qa(r.question.label, r.value)}")
    if skipped:
        lines.append(_sentence("Left blank, optional: " + "; ".join(_clean(r.question.label) for r in skipped)))
    if blocking:
        lines.append(f"I need you for {len(blocking)} question{'s' if len(blocking) > 1 else ''}.")
        for r in blocking:
            opts = [o.label for o in r.field.options]
            ask = _sentence(r.question.label)
            if opts:
                ask += " Options: " + ", ".join(_clean(o) for o in opts[:6]) + "."
            lines.append(ask)
        lines.append("Tell me the answer, or say skip this job.")
    else:
        lines.append(f"Say submit {company or 'it'} to send, or skip.")
    return "\n".join(lines)


def speak_tsenta(profile: dict, company: str, title: str) -> str:
    """What Tsenta will put on the form: it fills every field from the profile JSON."""
    pi = profile.get("personalInformation", {})
    wa = profile.get("workAuthorization", {})
    yes_no = lambda v: "yes" if v else "no"  # noqa: E731
    lines = [
        f"{_clean(company)}, {_clean(title)}, sent through Tsenta with your tailored resume.",
        f"Name: {pi.get('firstName', '')} {pi.get('lastName', '')}.",
        f"Email: {pi.get('email', '')}.",
        f"Phone: {pi.get('phone', '')}.",
        f"Location: {', '.join(x for x in (pi.get('city'), pi.get('state')) if x)}.",
        f"Authorized to work: {yes_no(wa.get('isAuthorizedToWork'))}. "
        f"Needs sponsorship: {yes_no(wa.get('needsSponsorship'))}.",
        "Tsenta answers any other form question from your profile; anything it can't answer comes back to you.",
        f"Say submit {_clean(company)} to send, or skip.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- digests and pending state


def _sha(path: str | Path | None) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).exists() else ""


def plan_digest(plan, pdf: str | Path | None = None) -> str:
    """Changes whenever an answer, a required flag or the resume changes."""
    rows = [[r.question.label, r.field.name, r.status, r.value if not isinstance(r.value, Path) else str(r.value)]
            for r in plan]
    blob = json.dumps({"rows": rows, "pdf": _sha(pdf)}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def tsenta_digest(profile: dict, pdf: str | Path) -> str:
    blob = json.dumps({"profile": profile, "pdf": _sha(pdf)}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _url_key(url: str) -> str:
    return re.sub(r"[?#].*$", "", url.strip().lower()).rstrip("/")


@dataclass
class Pending:
    url: str
    company: str
    title: str
    digest: str
    route: str  # filler | tsenta
    pdf: str
    read_at: str

    @staticmethod
    def path(runs: Path) -> Path:
        return runs / "voice" / "pending.json"

    def save(self, runs: Path) -> None:
        p = self.path(runs)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.__dict__, indent=2))

    @classmethod
    def load(cls, runs: Path) -> "Pending | None":
        p = cls.path(runs)
        return cls(**json.loads(p.read_text())) if p.exists() else None

    @classmethod
    def clear(cls, runs: Path) -> None:
        cls.path(runs).unlink(missing_ok=True)


def record_readback(runs: Path, url: str, company: str, title: str, digest: str, route: str,
                    pdf: str | Path, now: datetime | None = None) -> Pending:
    """Remember what was just read to Sai. Only one job is ever pending: the last one heard."""
    pending = Pending(url=url, company=company, title=title, digest=digest, route=route, pdf=str(pdf),
                      read_at=(now or datetime.now(timezone.utc)).isoformat())
    pending.save(runs)
    return pending


# ---------------------------------------------------------------- the spoken go-ahead

_NEGATIVE = re.compile(r"\b(don'?t|do not|not|no|never|cancel|stop|wait|hold|skip|later|undo)\b")
_COMPANY_NOISE = {"inc", "llc", "ltd", "co", "corp", "corporation", "company", "the", "plc", "gmbh", "group"}


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split()


def _company_heard(company: str, heard: str) -> bool:
    """True when the words after "submit" name this company (dictation-tolerant)."""
    want = [w for w in _words(company) if w not in _COMPANY_NOISE] or _words(company)
    got = [w for w in _words(heard) if w not in _COMPANY_NOISE]
    if not want or not got:
        return False
    if all(w in got for w in want):
        return True
    # "data dog" for "Datadog", "stripe's" for "Stripe": compare squashed letters.
    a, b = "".join(want), "".join(got).replace("'s", "").replace("'", "")
    return a in b or difflib.SequenceMatcher(None, a, b[: len(a) + 3]).ratio() >= 0.8


def check_confirmation(transcript: str, pending: Pending | None, url: str, current_digest: str,
                       now: datetime | None = None) -> tuple[bool, str]:
    """(ok, reason). The reason is meant to be read to Sai as is."""
    if pending is None:
        return False, "I haven't read you this application yet. Say read it back."
    if _url_key(pending.url) != _url_key(url):
        return False, f"The last application I read you was {pending.company}, not this one. Say read it back."
    now = now or datetime.now(timezone.utc)
    if now - datetime.fromisoformat(pending.read_at) > READBACK_TTL:
        return False, f"It's been over {int(READBACK_TTL.total_seconds() // 60)} minutes since I read it. Say read it back."
    if pending.digest != current_digest:
        return False, "Something changed since I read it to you. Say read it back."
    words = _words(transcript)
    if "submit" not in words:
        return False, f"To send it, say submit {pending.company}."
    before = " ".join(words[: words.index("submit")])
    after = " ".join(words[words.index("submit") + 1:])
    own = set(_words(pending.company))  # a company called "Hold Co" is not a "hold"
    rest = " ".join(w for w in after.split() if w not in own)
    if _NEGATIVE.search(before) or _NEGATIVE.search(rest):
        return False, "I heard a no or a wait in that, so I didn't send it."
    if not _company_heard(pending.company, after):
        return False, f"I didn't catch the company. Say submit {pending.company}."
    return True, f"Submitting {pending.company}."


# ---------------------------------------------------------------- hands-on list


def later_path(runs: Path) -> Path:
    return runs / "voice" / "later.jsonl"


def later_add(runs: Path, what: str, url: str = "", now: datetime | None = None) -> None:
    p = later_path(runs)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({"at": (now or datetime.now(timezone.utc)).isoformat(), "what": what, "url": url}) + "\n")


def later_items(runs: Path) -> list[dict]:
    p = later_path(runs)
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def speak_later(items: list[dict]) -> str:
    if not items:
        return "Nothing is waiting for your hands."
    lines = [f"{len(items)} thing{'s' if len(items) > 1 else ''} need{'' if len(items) > 1 else 's'} your hands:"]
    lines += [f"{i}. {_sentence(it['what'])}" for i, it in enumerate(items, 1)]
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="voice")
    p.add_argument("--runs", default=str(RUNS))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("url", help="turn a dictated link into a URL")
    s.add_argument("spoken")

    s = sub.add_parser("readback-tsenta", help="speak what Tsenta will send and remember it as pending")
    for name in ("--pdf", "--company", "--title", "--url"):
        s.add_argument(name, required=True)

    s = sub.add_parser("confirm", help="check a spoken go-ahead for a Tsenta job (filler: --voice-confirm)")
    s.add_argument("--url", required=True)
    s.add_argument("transcript")

    s = sub.add_parser("later", help="the hands-on list")
    s.add_argument("action", choices=["add", "list", "clear"])
    s.add_argument("what", nargs="?")
    s.add_argument("--url", default="")

    a = p.parse_args(argv)
    runs = Path(a.runs)

    if a.cmd == "url":
        url = normalize_spoken_url(a.spoken)
        if url is None:
            print("REFUSED: that doesn't sound like a link. Spell the site, like jobs dot lever dot co slash company.")
            return 2
        print(url)
        return 0

    if a.cmd == "readback-tsenta":
        profile = json.loads((runs / "profile.json").read_text())
        print(speak_tsenta(profile, a.company, a.title))
        record_readback(runs, a.url, a.company, a.title, tsenta_digest(profile, a.pdf), "tsenta", a.pdf)
        return 0

    if a.cmd == "confirm":
        pending = Pending.load(runs)
        if pending is not None and pending.route != "tsenta":
            print("REFUSED: this one goes through the filler; use filler.cli fill --submit --voice-confirm.")
            return 2
        digest = tsenta_digest(json.loads((runs / "profile.json").read_text()), pending.pdf) if pending else ""
        ok, reason = check_confirmation(a.transcript, pending, a.url, digest)
        print(("CONFIRMED: " if ok else "REFUSED: ") + reason)
        if ok:
            Pending.clear(runs)
        return 0 if ok else 2

    if a.action == "add":
        if not a.what:
            p.error("later add needs a description")
        later_add(runs, a.what, a.url)
        print("added")
    elif a.action == "list":
        print(speak_later(later_items(runs)))
        for it in later_items(runs):
            if it.get("url"):
                print(f"  {it['url']}")
    else:
        later_path(runs).unlink(missing_ok=True)
        print("cleared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
