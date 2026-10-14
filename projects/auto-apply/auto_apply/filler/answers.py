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
    """The single option label an answer refers to: exact, then prefix, then substring."""
    a = _norm(answer)
    labels = [o.label for o in options]
    for test in (
        lambda l: _norm(l) == a,
        lambda l: _norm(l).startswith(a),
        lambda l: a in _norm(l),
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

        found = self._lookup(q.label)
        if found is None:
            return Resolution(q, f, "missing" if q.required else "skip", note="no approved answer")
        answer, source, note = found
        if answer is None or answer == "":
            return Resolution(q, f, "missing" if q.required else "skip", source=source, note=note or "rule says leave blank")
        if answer == ASK:
            return Resolution(q, f, "ask" if q.required else "skip", source=source, note=note or "needs your answer")

        if f.type == "multi_value_single_select":
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
