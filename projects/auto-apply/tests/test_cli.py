import json

import pytest

from auto_apply import cli
from conftest import GOOD_RESUME, INSTRUCTIONS, PROFILE


@pytest.fixture
def runs(tmp_path, monkeypatch):
    (tmp_path / "instructions.txt").write_text(INSTRUCTIONS)
    raw = tmp_path / "profile_raw.json"
    raw.write_text(json.dumps({"tool": "get-resume-profile", "result": {"data": PROFILE}}))
    assert cli.main(["--runs", str(tmp_path), "profile", str(raw)]) == 0
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.5\n%%EOF\n")
    return tmp_path


def _gate(runs, text, monkeypatch, *extra):
    monkeypatch.setattr(cli, "pdf_text", lambda _: text)
    return cli.main(["--runs", str(runs), "gate", str(runs / "resume.pdf"), *extra])


def test_profile_command_writes_apply_profile(runs):
    assert json.loads((runs / "profile.json").read_text()) == PROFILE


def test_gate_passes_clean_resume(runs, monkeypatch, capsys):
    assert _gate(runs, GOOD_RESUME, monkeypatch, "--url", "https://x.com/j/1") == 0
    assert "PASS" in capsys.readouterr().out


def test_gate_lets_any_tool_through(runs, monkeypatch, capsys):
    # The instructions' "Never claim: ... Tableau" list is not enforced.
    assert _gate(runs, GOOD_RESUME + " Modeled in SAS and Tableau.", monkeypatch) == 0


def test_gate_blocks_duplicates_and_cap(runs, monkeypatch, capsys):
    cli.main(["--runs", str(runs), "record", "--company", "Acme", "--title", "Analyst",
              "--url", "https://x.com/j/1", "--pdf", str(runs / "resume.pdf")])
    assert _gate(runs, GOOD_RESUME, monkeypatch, "--url", "https://x.com/j/1/?utm_source=a") == 2
    assert "duplicate" in capsys.readouterr().out
    assert _gate(runs, GOOD_RESUME, monkeypatch, "--url", "https://x.com/j/2", "--cap", "1") == 2
    assert "daily cap" in capsys.readouterr().out


def test_record_stores_resume_hash(runs):
    cli.main(["--runs", str(runs), "record", "--company", "A", "--title", "T",
              "--pdf", str(runs / "resume.pdf"), "--application-id", "app1"])
    entry = json.loads((runs / "ledger.jsonl").read_text().splitlines()[0])
    assert entry["application_id"] == "app1" and len(entry["resume_sha256"]) == 64


def test_profile_set_overrides_known_fields_only(tmp_path):
    import copy
    prof = copy.deepcopy(PROFILE)
    prof["diversityEquityInclusion"] = {"gender": ""}
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"data": prof}))
    assert cli.main(["--runs", str(tmp_path), "profile", str(raw),
                     "--set", "diversityEquityInclusion.gender=Male"]) == 0
    assert json.loads((tmp_path / "profile.json").read_text())["diversityEquityInclusion"]["gender"] == "Male"
    assert cli.main(["--runs", str(tmp_path), "profile", str(raw), "--set", "diversityEquityInclusion.gendr=Male"]) == 2
