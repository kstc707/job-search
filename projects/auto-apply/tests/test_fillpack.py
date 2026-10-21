"""Packs for the Apply Autofill extension: validation and CLI, with a made-up candidate."""

import base64
import hashlib
import json

import pytest

from auto_apply import fillpack
from auto_apply.fillpack import PackError, build_job_pack, build_profile_pack, check_rules
from conftest import PROFILE

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

RULES = [
    {"match": "sponsorship", "answer": "ASK", "note": "decide once"},
    {"match": r"authori[sz]ed to work", "answer": "Yes"},
    {"match": r"(?<!trans)gender", "answer": ["Decline to self-identify", "I don't wish to answer"]},
    {"match": "years of experience", "answer": "3"},
]


@pytest.fixture
def files(tmp_path):
    (tmp_path / "profile.json").write_text(json.dumps(PROFILE))
    (tmp_path / "answers.json").write_text(json.dumps({"rules": RULES}))
    (tmp_path / "resume.pdf").write_bytes(PDF)
    (tmp_path / "job-answers.json").write_text(json.dumps({
        "_how": "comment keys are dropped",
        "Why do you want to work at Acme?": "I like spreadsheets.",
    }))
    return tmp_path


def test_profile_pack_keeps_rules_in_order(files):
    pack = build_profile_pack(PROFILE, RULES)
    assert pack["kind"] == "autofill-profile-pack" and pack["version"] == 1
    assert [r["match"] for r in pack["rules"]] == [r["match"] for r in RULES]
    assert pack["profile"]["personalInformation"]["firstName"] == "Alex"
    assert "defaultResume" not in pack


def test_profile_pack_with_default_resume(files):
    pack = build_profile_pack(PROFILE, RULES, files / "resume.pdf")
    r = pack["defaultResume"]
    assert r["filename"] == "resume.pdf" and r["bytes"] == len(PDF)
    assert base64.b64decode(r["base64"]) == PDF
    assert r["sha256"] == hashlib.sha256(PDF).hexdigest()


@pytest.mark.parametrize("rule,needle", [
    ({"match": "(unclosed", "answer": "x"}, "not a valid regex"),
    ({"match": "", "answer": "x"}, "non-empty"),
    ({"match": "ok"}, "no \"answer\""),
    ({"match": "ok", "answer": {"a": 1}}, "answer must be"),
    ({"match": "a++", "answer": "x"}, "possessive"),
    ({"match": "(?>atomic)", "answer": "x"}, "atomic"),
])
def test_bad_rules_are_rejected(rule, needle):
    with pytest.raises(PackError, match=needle):
        check_rules([rule])


def test_rules_python_and_js_both_accept():
    # Lookbehind, a leading (?i) flag and named groups all have JavaScript equivalents.
    rules = check_rules([
        {"match": r"(?<!trans)gender", "answer": "x"},
        {"match": r"(?i)^veteran", "answer": ["No", "I am not a protected veteran"]},
        {"match": r"(?P<n>\d+)\+? years", "answer": None},
    ])
    assert len(rules) == 3


def test_profile_must_have_contact_basics():
    with pytest.raises(PackError, match="email"):
        build_profile_pack({"personalInformation": {"firstName": "A", "lastName": "B"}}, [])
    with pytest.raises(PackError, match="personalInformation"):
        build_profile_pack({}, [])


def test_job_pack(files):
    answers = json.loads((files / "job-answers.json").read_text())
    pack = build_job_pack(files / "resume.pdf", "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/123",
                          "Data Analyst", "Acme", answers, "Alex-Rivera-Resume.pdf")
    assert pack["kind"] == "autofill-job-pack"
    assert pack["job"] == {"url": "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/123",
                           "title": "Data Analyst", "company": "Acme"}
    assert pack["answers"] == {"Why do you want to work at Acme?": "I like spreadsheets."}
    assert pack["resume"]["filename"] == "Alex-Rivera-Resume.pdf"
    assert base64.b64decode(pack["resume"]["base64"]) == PDF


@pytest.mark.parametrize("data,needle", [
    (b"hello", "missing %PDF- header"),
    (b"%PDF-1.4\nno trailer", "truncated"),
    (b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024) + b"\n%%EOF\n", "limit"),
])
def test_job_pack_validates_pdf(tmp_path, data, needle):
    (tmp_path / "bad.pdf").write_bytes(data)
    with pytest.raises(PackError, match=needle):
        build_job_pack(tmp_path / "bad.pdf", "https://x.example/apply", "T", "C")


def test_job_pack_validates_url_and_names(files):
    with pytest.raises(PackError, match="http"):
        build_job_pack(files / "resume.pdf", "acme.com/apply", "T", "C")
    with pytest.raises(PackError, match="plain"):
        build_job_pack(files / "resume.pdf", "https://x.example/a", "T", "C", filename="../x.pdf")
    with pytest.raises(PackError, match="title"):
        build_job_pack(files / "resume.pdf", "https://x.example/a", " ", "C")


def test_cli_profile_and_job(files, capsys):
    out = files / "profile-pack.json"
    assert fillpack.main(["profile", "--profile", str(files / "profile.json"),
                          "--answers", str(files / "answers.json"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["rules"][2]["match"] == "(?<!trans)gender"

    job_out = files / "job" / "job-pack.json"
    assert fillpack.main(["job", "--pdf", str(files / "resume.pdf"), "--url", "https://jobs.example.com/apply/1",
                          "--title", "Data Analyst", "--company", "Acme",
                          "--answers", str(files / "job-answers.json"), "--runs", str(files),
                          "--out", str(job_out)]) == 0
    assert json.loads(job_out.read_text())["resume"]["filename"] == "resume.pdf"
    assert "job pack: Data Analyst @ Acme" in capsys.readouterr().out


def test_cli_reports_bad_input(files, capsys):
    (files / "answers.json").write_text(json.dumps({"rules": [{"match": "(", "answer": "x"}]}))
    assert fillpack.main(["profile", "--profile", str(files / "profile.json"),
                          "--answers", str(files / "answers.json"), "--out", str(files / "p.json")]) == 2
    assert "not a valid regex" in capsys.readouterr().err
    assert not (files / "p.json").exists()


def test_cli_blocks_answers_that_claim_never_claim_skills(files, capsys):
    (files / "instructions.txt").write_text("Never claim: Tableau.")
    (files / "job-answers.json").write_text(json.dumps({"Do you have Tableau experience?": "Yes"}))
    code = fillpack.main(["job", "--pdf", str(files / "resume.pdf"), "--url", "https://jobs.example.com/a",
                          "--title", "T", "--company", "C", "--answers", str(files / "job-answers.json"),
                          "--runs", str(files), "--out", str(files / "j.json")])
    assert code == 3
    assert "Tableau" in capsys.readouterr().err
    assert not (files / "j.json").exists()
