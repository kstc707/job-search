import pytest

from llm_data_analyst.agent import DataAnalystAgent
from llm_data_analyst.db import Database


class FakeLLM:
    """Returns canned responses in order instead of calling a real model, so
    the agent's control flow (retry loop, guard integration) can be tested
    without network access or an API key."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def complete(self, system, user, max_tokens=1024):
        self.calls.append((system, user))
        return self._responses.pop(0)


def _make_db(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("region,revenue\nNorth,100\nSouth,50\n")
    db = Database()
    db.load_csv("data", str(csv_path))
    return db


def test_agent_answers_on_first_try(tmp_path):
    db = _make_db(tmp_path)
    llm = FakeLLM(
        [
            "SELECT region, SUM(revenue) AS total FROM data GROUP BY region",
            "North leads with $100 in revenue, ahead of South at $50.",
        ]
    )
    agent = DataAnalystAgent(db, llm)

    result = agent.ask("Which region has the most revenue?")

    assert result.attempts == 1
    assert "North" in result.answer
    assert len(llm.calls) == 2


def test_agent_retries_after_invalid_sql(tmp_path):
    db = _make_db(tmp_path)
    llm = FakeLLM(
        [
            "DROP TABLE data",  # rejected by the guard
            "SELECT region FROM data WHERE revenue > 75",  # valid retry
            "Only North has revenue above 75.",
        ]
    )
    agent = DataAnalystAgent(db, llm)

    result = agent.ask("Which regions have revenue over 75?")

    assert result.attempts == 2
    assert "North" in result.answer


def test_agent_gives_up_after_max_attempts(tmp_path):
    db = _make_db(tmp_path)
    llm = FakeLLM(["DROP TABLE data"] * 3)
    agent = DataAnalystAgent(db, llm)

    with pytest.raises(RuntimeError):
        agent.ask("anything")


def test_strips_markdown_fences_from_sql(tmp_path):
    db = _make_db(tmp_path)
    llm = FakeLLM(
        [
            "```sql\nSELECT * FROM data\n```",
            "There are two regions in the data.",
        ]
    )
    agent = DataAnalystAgent(db, llm)

    result = agent.ask("Show me everything")

    assert result.sql == "SELECT * FROM data"
