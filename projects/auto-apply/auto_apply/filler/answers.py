"""Decide the answer for every form field, or say exactly why there isn't one.

Answers come only from data the user approved:
- the Tsenta profile (name, email, phone),
- `runs/answers.json`: ordered rules {"match": regex on the question label, "answer": ...},
  where "answer": "ASK" means "never answer this without asking me",
- an optional per-job file of {"exact question label": answer} (e.g. drafted free-text
  answers the user reviewed).

A required question with no approved answer blocks the run. Nothing is guessed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import Field, Question

ASK = "ASK"

# Greenhouse's standard field names → profile path.
_PROFILE_FIELDS = {
    "first_name": "personalInformation.firstName",
    "last_name": "personalInformation.lastName",
    "email": "personalInformation.email",
    "phone": "personalInformation.phone",
}

# Forms read from the page (Lever, Ashby) have no stable field names, so the contact
# questions are recognised by label instead. Anchored: "Preferred name" is not "Name".
_PROFILE_LABELS = [
    (re.compile(r"^(full |legal )?name$"), ("personalInformation.firstName", "personalInformation.lastName")),
    (re.compile(r"^first name$"), ("personalInformation.firstName",)),
    (re.compile(r"^last name$"), ("personalInformation.lastName",)),
    (re.compile(r"^(e ?mail|email address)$"), ("personalInformation.email",)),
    (re.compile(r"^(phone|phone number|mobile|mobile phone)$"), ("personalInformation.phone",)),
    (re.compile(r"^(zip|postal)\b"), ("personalInformation.zipCode",)),
    (re.compile(r"^(please enter your )?(home |street |mailing )?address\b"),
     ("personalInformation.address", "personalInformation.city", "personalInformation.state",
      "personalInformation.zipCode")),
]

# Field types where the answer must name exactly one of the options.
_SINGLE_CHOICE = ("multi_value_single_select", "native_select", "radio", "yesno")


@dataclass
class Resolution:
    question: Question
    field: Field
    status: str  # fill | skip | ask | missing | no-option
    value: Any = None  # str, list[str] of option labels, or a file path
    source: str = ""
    note: str = ""

    @property
    def blocking(self) -> bool:
        return self.question.required and self.status in ("ask", "missing", "no-option")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def match_option(answer: str, options: list) -> str | None:
    """The single option label an answer refers to: exact, then prefix, then whole words inside.

    Whole words only: "No" must not pick "I am not a veteran" because "no" is inside "not".
    """
    a = _norm(answer)
    labels = [o.label for o in options]
    for test in (
        lambda l: _norm(l) == a,
        lambda l: _norm(l).startswith(a),
        lambda l: re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", _norm(l)) is not None,
    ):
        hits = [l for l in labels if test(l)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None  # ambiguous: refuse rather than pick one
    return None


class AnswerBank:
    def __init__(self, profile: dict, rules: list[dict], files: dict[str, str | None],
                 job_answers: dict[str, Any] | None = None):
        self.profile = profile
        self.rules = [(re.compile(r["match"], re.IGNORECASE), r["answer"], r.get("note", "")) for r in rules]
        self.files = files
        self.job_answers = {_norm(k): v for k, v in (job_answers or {}).items()}

    @classmethod
    def load(cls, profile_path: Path, rules_path: Path, files: dict[str, str | None],
             job_answers_path: Path | None = None) -> "AnswerBank":
        profile = json.loads(profile_path.read_text())
        rules = json.loads(rules_path.read_text())["rules"]
        job = json.loads(job_answers_path.read_text()) if job_answers_path and job_answers_path.exists() else None
        return cls(profile, rules, files, job)

    def _profile_value(self, dotted: str) -> Any:
        node: Any = self.profile
        for key in dotted.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        return node

    def _profile_by_label(self, label: str) -> str | None:
        key = _norm(label)
        for pattern, paths in _PROFILE_LABELS:
            if pattern.match(key):
                parts = [self._profile_value(path) for path in paths]
                if not all(parts):
                    return None
                if len(parts) == 4:  # street, city, state zip
                    return f"{parts[0]}, {parts[1]}, {parts[2]} {parts[3]}"
                return " ".join(str(x) for x in parts)
        return None

    def _years_threshold(self, q: Question, f: Field) -> "Resolution | None":
        """'Do you have at least N years of …?' answered from the approved years-of-experience rule.

        More years asked than you have → "No" (true whatever the skill). Fewer or equal is only
        safe for experience overall; for a specific skill ("5 years in AWS") it must be asked.
        """
        m = re.search(r"(?:minimum of|at least|\bover)\s+(\d+)\+?\s+years", q.label, re.IGNORECASE)
        found = self._lookup("years of experience")
        first = found[0][0] if found and isinstance(found[0], list) and found[0] else (found[0] if found else None)
        if not m or first is None or not re.match(r"\d+", str(first)):
            return None
        asked, have = int(m.group(1)), int(re.match(r"\d+", str(first)).group())
        if asked > have:
            hit = match_option("No", f.options)
            if hit:
                return Resolution(q, f, "fill", hit, f"derived: asks {asked} years, you have {have}")
            return None
        return Resolution(q, f, "ask" if q.required else "skip", source="years rule",
                          note=f"asks {asked} years; you have {have} overall — confirm for this skill")

    def _lookup(self, label: str) -> tuple[Any, str, str] | None:
        key = _norm(label)
        if key in self.job_answers:
            return self.job_answers[key], "job answers", ""
        for pattern, answer, note in self.rules:
            if pattern.search(label):
                return answer, f"rule /{pattern.pattern}/", note
        return None

    def resolve_field(self, q: Question, f: Field) -> Resolution:
        if f.type == "input_file":
            kind = "resume" if "resume" in f.name or "resume" in q.label.lower() else (
                "cover_letter" if "cover" in f.name or "cover" in q.label.lower() else f.name)
            path = self.files.get(kind)
            if path:
                return Resolution(q, f, "fill", path, f"file:{kind}")
            return Resolution(q, f, "missing" if q.required else "skip", note=f"no {kind} file")

        if f.name in _PROFILE_FIELDS:
            v = self._profile_value(_PROFILE_FIELDS[f.name])
            if v:
                return Resolution(q, f, "fill", str(v), "profile")
        if f.type in ("input_text", "textarea"):
            v = self._profile_by_label(q.label)
            if v:
                return Resolution(q, f, "fill", v, "profile")

        if f.type in _SINGLE_CHOICE:
            derived = self._years_threshold(q, f)
            if derived:
                return derived

        found = self._lookup(q.label)
        if found is None:
            return Resolution(q, f, "missing" if q.required else "skip", note="no approved answer")
        answer, source, note = found
        if answer is None or answer == "":
            return Resolution(q, f, "missing" if q.required else "skip", source=source, note=note or "rule says leave blank")
        if answer == ASK:
            return Resolution(q, f, "ask" if q.required else "skip", source=source, note=note or "needs your answer")

        if f.type in _SINGLE_CHOICE:
            # A rule may list alternatives (forms word the same answer differently):
            # the first one that names exactly one option wins.
            candidates = answer if isinstance(answer, list) else [answer]
            hit = next((h for h in (match_option(str(c), f.options) for c in candidates) if h), None)
            if hit is None:
                return Resolution(q, f, "no-option", answer, source,
                                  f"'{answer}' matches no single option: {[o.label for o in f.options][:8]}")
            return Resolution(q, f, "fill", hit, source, note)
        if f.type == "multi_value_multi_select":
            wanted = answer if isinstance(answer, list) else [answer]
            hits = [match_option(str(a), f.options) for a in wanted]
            if None in hits:
                # A list can also be alternative wordings of one answer ("decline", "I don't
                # wish to answer"): accept it when exactly one of them names an option.
                found = [h for h in hits if h]
                if len(found) == 1:
                    return Resolution(q, f, "fill", found, source, note)
                return Resolution(q, f, "no-option", answer, source, f"options: {[o.label for o in f.options][:8]}")
            return Resolution(q, f, "fill", hits, source, note)
        return Resolution(q, f, "fill", str(answer), source, note)

    def plan(self, questions: list[Question]) -> list[Resolution]:
        out: list[Resolution] = []
        for q in questions:
            fields = q.fields
            # "Attach or paste" questions offer input_file + textarea; attaching is enough.
            if any(f.type == "input_file" for f in fields):
                fields = [f for f in fields if f.type == "input_file"]
            out.extend(self.resolve_field(q, f) for f in fields)
        return out
