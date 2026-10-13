"""Behavioural metrics over agent trajectories, plus paired significance tests between configs.

Trajectory schema: one JSON object per agent step, in order, with at least
    task_id: str
    tool_name: str | None        # None if the call couldn't be parsed
    tool_args: dict | None
    malformed: bool              # unparseable call, unknown tool, or invalid arguments
    thinking_tokens: int
    answer_tokens: int
    wall_s: float
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class TrajectoryMetrics:
    n_tasks: int
    n_calls: int
    malformed_share: float
    repeat_share: float  # well-formed calls identical to an earlier call in the same task
    p_malformed_after_malformed: float  # NaN if no malformed call was followed by another call
    thinking_token_share: float
    mean_wall_s_per_task: float


def load_steps(path: str | Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _call_key(step: dict) -> str:
    return step["tool_name"] + "\x00" + json.dumps(step["tool_args"], sort_keys=True)


def trajectory_metrics(steps: Iterable[dict]) -> TrajectoryMetrics:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for s in steps:
        by_task[s["task_id"]].append(s)

    n_calls = n_malformed = n_wellformed = n_repeat = 0
    n_after_malformed = n_malformed_after_malformed = 0
    thinking = answer = 0
    wall = 0.0
    for task_steps in by_task.values():
        seen: set[str] = set()
        prev_malformed = False
        for s in task_steps:
            n_calls += 1
            thinking += s["thinking_tokens"]
            answer += s["answer_tokens"]
            wall += s["wall_s"]
            if prev_malformed:
                n_after_malformed += 1
                n_malformed_after_malformed += s["malformed"]
            prev_malformed = s["malformed"]
            if s["malformed"]:
                n_malformed += 1
                continue
            n_wellformed += 1
            key = _call_key(s)
            n_repeat += key in seen
            seen.add(key)

    def ratio(a: float, b: float) -> float:
        return a / b if b else math.nan

    return TrajectoryMetrics(
        n_tasks=len(by_task),
        n_calls=n_calls,
        malformed_share=ratio(n_malformed, n_calls),
        repeat_share=ratio(n_repeat, n_wellformed),
        p_malformed_after_malformed=ratio(n_malformed_after_malformed, n_after_malformed),
        thinking_token_share=ratio(thinking, thinking + answer),
        mean_wall_s_per_task=ratio(wall, len(by_task)),
    )


def mcnemar_exact(a: dict[str, bool], b: dict[str, bool]) -> tuple[int, int, float]:
    """Exact two-sided McNemar test on tasks both configs ran.

    Returns (tasks only `a` resolved, tasks only `b` resolved, p-value).
    """
    shared = a.keys() & b.keys()
    only_a = sum(a[t] and not b[t] for t in shared)
    only_b = sum(b[t] and not a[t] for t in shared)
    n = only_a + only_b
    if n == 0:
        return 0, 0, 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return only_a, only_b, min(1.0, 2 * tail)


def paired_bootstrap_ci(
    a: dict[str, bool], b: dict[str, bool], n_boot: int = 10_000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float, float]:
    """Resolve-rate difference (a - b) with a percentile bootstrap CI over shared tasks."""
    shared = sorted(a.keys() & b.keys())
    if not shared:
        raise ValueError("no shared tasks")
    diffs = [int(a[t]) - int(b[t]) for t in shared]
    rng = random.Random(seed)
    n = len(diffs)
    boots = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(n_boot))
    lo = boots[int(alpha / 2 * n_boot)]
    hi = boots[int((1 - alpha / 2) * n_boot) - 1]
    return sum(diffs) / n, lo, hi
