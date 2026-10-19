"""Read a Greenhouse application form's questions from the public Job Board API.

GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true returns
every question with its label, required flag, and fields (name, type, option values).
The field `name` is also the input's DOM id on the hosted form, which is what lets the
browser step find each input without guessing from label text.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true"
_PATH = re.compile(r"^/(?:embed/job_app\?for=)?([^/]+)/jobs/(\d+)")


@dataclass
class Option:
    label: str
    value: int | str


@dataclass
class Field:
    name: str
    type: str  # input_text, textarea, input_file, multi_value_single_select, multi_value_multi_select
    options: list[Option] = field(default_factory=list)


@dataclass
class Question:
    label: str
    required: bool
    fields: list[Field]
    section: str = "questions"


def parse_job_url(url: str) -> tuple[str, str]:
    """(board, job_id) from a hosted Greenhouse URL.

    Handles job-boards.greenhouse.io / boards.greenhouse.io (incl. .eu.) paths and the
    embed form (?for=board&token=id). Company career pages with only ?gh_jid= do not say
    which board they belong to, so they are rejected rather than guessed.
    """
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if not host.endswith("greenhouse.io"):
        raise ValueError(f"not a hosted Greenhouse URL: {url} (need the board link, not a career page)")
    query = parse_qs(parts.query)
    if "for" in query and "token" in query:
        return query["for"][0], query["token"][0]
    m = _PATH.match(parts.path)
    if not m:
        raise ValueError(f"no board/job id in Greenhouse URL: {url}")
    return m.group(1), m.group(2)


def form_url(url: str) -> str:
    """The embeddable form for a job. Hosted job links redirect to the company's own career
    site when it has one (Stripe, Airbnb, Coinbase); the embed form never does."""
    board, job_id = parse_job_url(url)
    host = "job-boards.eu.greenhouse.io" if ".eu." in urlsplit(url).netloc.lower() else "job-boards.greenhouse.io"
    return f"https://{host}/embed/job_app?for={board}&token={job_id}"


def _fields(raw_fields: list[dict]) -> list[Field]:
    return [
        Field(
            name=f["name"],
            type=f["type"],
            options=[Option(v["label"], v["value"]) for v in f.get("values") or []],
        )
        for f in raw_fields
    ]


def questions_from_api(data: dict) -> list[Question]:
    """All questions in a job API response, across every section that can hold them."""
    out: list[Question] = []

    def add(items: list[dict] | None, section: str) -> None:
        for q in items or []:
            if q["fields"] and all(f["type"] == "input_hidden" for f in q["fields"]):
                continue  # set by the page itself (latitude/longitude come from the location pick)
            out.append(Question(q["label"].strip(), bool(q.get("required")), _fields(q["fields"]), section))

    add(data.get("questions"), "questions")
    add(data.get("location_questions"), "location")
    for block in data.get("compliance") or []:
        items = block.get("questions") or []
        if block.get("type") == "eeoc" and any(f["name"] == "race" for q in items for f in q["fields"]):
            # Greenhouse shows Race only after "Are you Hispanic/Latino?" is answered, and that
            # question is rendered on the form but missing from the API. Add it, first.
            out.append(Question("Are you Hispanic/Latino?", False, [Field("hispanic_ethnicity", "multi_value_single_select",
                [Option("Yes", "Yes"), Option("No", "No"), Option("Decline To Self Identify", "Decline To Self Identify")])],
                f"compliance:{block.get('type')}"))
        add(items, f"compliance:{block.get('type', '')}")
    demo = data.get("demographic_questions") or {}
    for q in demo.get("questions") or []:
        # Demographic questions use answer_options instead of fields; model them as one
        # select field named after the question id.
        opts = [Option(o["label"], o["id"]) for o in q.get("answer_options") or []]
        multi = q.get("type") == "multi_value_multi_select"
        out.append(Question(
            q["label"].strip(), bool(q.get("required")),
            [Field(f"demographic_{q['id']}", "multi_value_multi_select" if multi else "multi_value_single_select", opts)],
            "demographic",
        ))
    return out


def fetch_form(url: str, timeout: float = 30) -> tuple[dict, list[Question]]:
    board, job_id = parse_job_url(url)
    with urllib.request.urlopen(API.format(board=board, job_id=job_id), timeout=timeout) as resp:
        data = json.load(resp)
    return data, questions_from_api(data)
