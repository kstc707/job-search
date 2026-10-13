"""Thinking-budget forcing for a hybrid-thinking model served by llama.cpp's `llama-server`.

Gemma 4 exposes thinking only as on/off. To study intermediate budgets we cap the thinking phase
at N tokens and, if the model hasn't closed its thought by then, append a short wrap-up line plus
the end-of-thinking marker and let it answer (budget forcing, as in s1: arXiv 2501.19393).

The thinking markers are model-specific, so they're passed in via `ThinkMarkers` rather than
hardcoded. Read them off the rendered chat template in the feasibility notebook.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

# `post(path, payload) -> response dict`. Injected so tests don't need a server.
PostFn = Callable[[str, dict[str, Any]], dict[str, Any]]

UNLIMITED = -1


@dataclass(frozen=True)
class ThinkMarkers:
    start: str
    end: str
    # Appended before `end` when the budget runs out, nudging the model to act on what it has.
    wrap_up: str = "\nI'm out of thinking time, so I'll act on what I have.\n"


@dataclass
class BudgetedCompletion:
    thinking: str
    answer: str
    thinking_tokens: int
    answer_tokens: int
    forced: bool  # True if we cut the thought off at the budget


def http_post(base_url: str, timeout_s: float = 600.0) -> PostFn:
    def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read())

    return post


def _stopped_on_word(resp: dict[str, Any]) -> bool:
    # Newer llama-server builds report `stop_type`; older ones `stopped_word`.
    if "stop_type" in resp:
        return resp["stop_type"] == "word"
    return bool(resp.get("stopped_word"))


def _hit_token_limit(resp: dict[str, Any]) -> bool:
    if "stop_type" in resp:
        return resp["stop_type"] == "limit"
    return bool(resp.get("stopped_limit"))


def complete_with_budget(
    post: PostFn,
    prompt: str,
    markers: ThinkMarkers,
    budget: int,
    max_answer_tokens: int = 2048,
    sampling: dict[str, Any] | None = None,
) -> BudgetedCompletion:
    """Generate from an already-templated `prompt`, spending at most `budget` thinking tokens.

    `budget=UNLIMITED` leaves thinking uncapped. `budget=0` should be run with thinking disabled
    in the chat template instead; forcing a zero-length thought is not the same condition.
    """
    if budget == 0:
        raise ValueError("budget=0: render the prompt with thinking disabled and use plain completion")
    sampling = sampling or {}

    def complete(p: str, n_predict: int, stop: list[str]) -> dict[str, Any]:
        return post("/completion", {"prompt": p, "n_predict": n_predict, "stop": stop, **sampling})

    first = complete(prompt, budget, [markers.end])
    text = first["content"]
    n_first = first["tokens_predicted"]

    if markers.start not in text:
        # The model skipped thinking and went straight to its answer. Don't cut that off.
        answer, n_answer = text, n_first
        if _hit_token_limit(first):
            rest = complete(prompt + text, max_answer_tokens - n_first, [])
            answer += rest["content"]
            n_answer += rest["tokens_predicted"]
        return BudgetedCompletion("", answer, 0, n_answer, forced=False)

    forced = not _stopped_on_word(first)
    closing = (markers.wrap_up if forced else "") + markers.end
    second = complete(prompt + text + closing, max_answer_tokens, [])
    return BudgetedCompletion(
        thinking=text,
        answer=second["content"],
        thinking_tokens=n_first,
        answer_tokens=second["tokens_predicted"],
        forced=forced,
    )
