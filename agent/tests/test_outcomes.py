"""Tests for the outcome log and calibration report. Fixtures are synthetic."""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jobagent import outcomes  # noqa: E402
from jobagent.__main__ import main  # noqa: E402

TODAY = dt.date(2026, 10, 14)


def row(app, score, outcome="", applied="2026-08-01", family="ds"):
    return {"app_id": app, "applied": applied, "score": str(score), "outcome": outcome,
            "family": family, "source": "tsenta"}


def test_label_handles_pending_and_ghosting():
    assert outcomes.label(row("a", 70, "interview"), TODAY) == 1
    assert outcomes.label(row("a", 70, "rejected"), TODAY) == 0
    assert outcomes.label(row("a", 70, "", applied="2026-08-01"), TODAY) == 0  # 74 days: ghosted
    assert outcomes.label(row("a", 70, "", applied="2026-10-01"), TODAY) is None  # still pending
    assert outcomes.label(row("a", 70, "", applied="bad"), TODAY) is None


def test_wilson_interval():
    lo, hi = outcomes.wilson(0, 10)
    assert lo == 0.0 and 0.25 < hi < 0.35  # zero successes still leaves real uncertainty
    lo, hi = outcomes.wilson(5, 10)
    assert lo < 0.5 < hi and abs((lo + hi) / 2 - 0.5) < 1e-9
    assert outcomes.wilson(0, 0) == (0.0, 1.0)


def test_auc():
    assert outcomes.auc([90, 80, 60, 50], [1, 1, 0, 0]) == 1.0
    assert outcomes.auc([50, 60, 80, 90], [1, 1, 0, 0]) == 0.0
    assert outcomes.auc([70, 70], [1, 0]) == 0.5
    assert outcomes.auc([70, 80], [1, 1]) is None


def test_report_leaves_out_pending_rows():
    rows = [row("a", 85, "interview"), row("b", 60, "rejected"),
            row("c", 75, "", applied="2026-10-10"), row("d", "", "offer")]
    res = outcomes.report(rows, TODAY)
    assert res["settled"] == 2 and res["positives"] == 1 and res["auc"] == 1.0
    assert res["enough_data"] is False
    assert "Not enough data" in outcomes.text(res)
    assert res["groups"]["family"] == {"ds": {"n": 2, "positives": 1}}


def test_cli_add_set_report(tmp_path, capsys):
    log = str(tmp_path / "outcomes.csv")
    sj = tmp_path / "s.json"
    sj.write_text(json.dumps({"title": "Data Scientist", "company": "Acme", "family": "ds",
                              "score": 77.5, "decision": "review",
                              "parts": {"required": 24, "keywords": 12}}))
    assert main(["outcomes", "add", "APP1", "--score-json", str(sj), "--applied", "2026-08-01",
                 "--log", log]) == 0
    assert main(["outcomes", "set", "APP1", "interview", "--log", log]) == 0
    rows = outcomes.load(log)
    assert rows[0]["required"] == "24" and rows[0]["outcome"] == "interview"
    assert rows[0]["signal"] == ""
    capsys.readouterr()
    assert main(["outcomes", "report", "--log", log, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["positives"] == 1
