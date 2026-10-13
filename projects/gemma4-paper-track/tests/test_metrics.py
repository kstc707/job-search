import math

import pytest

from thinkbudget.metrics import mcnemar_exact, paired_bootstrap_ci, trajectory_metrics


def step(task, name, args, malformed=False, think=10, ans=5, wall=1.0):
    return {"task_id": task, "tool_name": name, "tool_args": args, "malformed": malformed,
            "thinking_tokens": think, "answer_tokens": ans, "wall_s": wall}


def test_trajectory_metrics():
    steps = [
        step("t1", "grep", {"q": "a"}),
        step("t1", "grep", {"q": "a"}),            # repeat
        step("t1", None, None, malformed=True),
        step("t1", None, None, malformed=True),    # malformed after malformed
        step("t1", "read", {"p": "x"}),            # well-formed after malformed
        step("t2", "grep", {"q": "a"}),            # same call, different task: not a repeat
    ]
    m = trajectory_metrics(steps)
    assert (m.n_tasks, m.n_calls) == (2, 6)
    assert m.malformed_share == pytest.approx(2 / 6)
    assert m.repeat_share == pytest.approx(1 / 4)
    assert m.p_malformed_after_malformed == pytest.approx(1 / 2)
    assert m.thinking_token_share == pytest.approx(60 / 90)
    assert m.mean_wall_s_per_task == pytest.approx(3.0)


def test_arg_order_does_not_matter_for_repeats():
    m = trajectory_metrics([step("t", "f", {"a": 1, "b": 2}), step("t", "f", {"b": 2, "a": 1})])
    assert m.repeat_share == 0.5


def test_no_malformed_gives_nan_conditional():
    assert math.isnan(trajectory_metrics([step("t", "f", {})]).p_malformed_after_malformed)


def test_mcnemar_exact():
    a = {f"t{i}": i < 8 for i in range(10)}
    b = {f"t{i}": i < 2 for i in range(10)}
    only_a, only_b, p = mcnemar_exact(a, b)
    assert (only_a, only_b) == (6, 0)
    assert p == pytest.approx(2 / 64)
    assert mcnemar_exact(a, a)[2] == 1.0


def test_paired_bootstrap_ci_brackets_point_estimate():
    a = {f"t{i}": i % 2 == 0 for i in range(40)}
    b = {f"t{i}": i % 4 == 0 for i in range(40)}
    est, lo, hi = paired_bootstrap_ci(a, b, n_boot=2000)
    assert est == pytest.approx(0.25)
    assert lo <= est <= hi
