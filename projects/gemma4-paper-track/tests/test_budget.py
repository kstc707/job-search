import pytest

from thinkbudget.budget import ThinkMarkers, complete_with_budget, UNLIMITED

M = ThinkMarkers(start="<think>", end="</think>", wrap_up="[wrap]")


class FakeServer:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, path, payload):
        self.calls.append(payload)
        return self.responses.pop(0)


def test_natural_finish_within_budget():
    srv = FakeServer([
        {"content": "<think>short plan", "tokens_predicted": 12, "stop_type": "word"},
        {"content": "call(edit)", "tokens_predicted": 5, "stop_type": "eos"},
    ])
    out = complete_with_budget(srv, "P", M, budget=100)
    assert not out.forced
    assert (out.thinking_tokens, out.answer_tokens, out.answer) == (12, 5, "call(edit)")
    assert srv.calls[0]["n_predict"] == 100 and srv.calls[0]["stop"] == ["</think>"]
    assert srv.calls[1]["prompt"] == "P<think>short plan</think>"


def test_budget_exhausted_forces_wrap_up():
    srv = FakeServer([
        {"content": "<think>long long", "tokens_predicted": 64, "stop_type": "limit"},
        {"content": "call(grep)", "tokens_predicted": 4, "stop_type": "eos"},
    ])
    out = complete_with_budget(srv, "P", M, budget=64)
    assert out.forced
    assert srv.calls[1]["prompt"] == "P<think>long long[wrap]</think>"


def test_older_server_stop_fields():
    srv = FakeServer([
        {"content": "<think>x", "tokens_predicted": 3, "stopped_word": True},
        {"content": "a", "tokens_predicted": 1},
    ])
    assert not complete_with_budget(srv, "P", M, budget=10).forced


def test_skipped_thinking_answer_is_not_truncated():
    srv = FakeServer([
        {"content": "call(", "tokens_predicted": 8, "stop_type": "limit"},
        {"content": "read)", "tokens_predicted": 2, "stop_type": "eos"},
    ])
    out = complete_with_budget(srv, "P", M, budget=8, max_answer_tokens=50)
    assert (out.thinking, out.answer, out.answer_tokens, out.forced) == ("", "call(read)", 10, False)
    assert srv.calls[1]["prompt"] == "Pcall(" and srv.calls[1]["n_predict"] == 42


def test_unlimited_and_sampling_passthrough():
    srv = FakeServer([
        {"content": "<think>t", "tokens_predicted": 2, "stop_type": "word"},
        {"content": "a", "tokens_predicted": 1, "stop_type": "eos"},
    ])
    complete_with_budget(srv, "P", M, budget=UNLIMITED, sampling={"temperature": 0.6, "seed": 1})
    assert srv.calls[0]["n_predict"] == -1 and srv.calls[0]["seed"] == 1


def test_zero_budget_rejected():
    with pytest.raises(ValueError):
        complete_with_budget(FakeServer([]), "P", M, budget=0)
