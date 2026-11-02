import json
from datetime import datetime, timedelta, timezone

import pytest

from auto_apply import voice
from auto_apply.filler import cli as filler_cli
from auto_apply.filler.answers import AnswerBank
from auto_apply.filler.schema import questions_from_api
from conftest import PROFILE
from test_filler import API, RULES

URL = "https://job-boards.greenhouse.io/acme/jobs/123"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------ spoken URLs

@pytest.mark.parametrize("spoken,url", [
    ("jobs dot ashbyhq dot com slash acme slash 1 2 3", "https://jobs.ashbyhq.com/acme/123"),
    ("job dash boards dot greenhouse dot io slash acme slash jobs slash four five six",
     "https://job-boards.greenhouse.io/acme/jobs/456"),
    ("https colon slash slash jobs dot lever dot co slash acme", "https://jobs.lever.co/acme"),
    ("The link is jobs.lever.co/acme.", "https://jobs.lever.co/acme"),
    ("jobs . lever . co / acme / abc-def", "https://jobs.lever.co/acme/abc-def"),
])
def test_spoken_urls(spoken, url):
    assert voice.normalize_spoken_url(spoken) == url


@pytest.mark.parametrize("spoken", ["find me data jobs", "apply to number two", ""])
def test_not_a_url(spoken):
    assert voice.normalize_spoken_url(spoken) is None


# ------------------------------------------------------------ read-back

@pytest.fixture
def plan():
    rules = [r for r in RULES if r["match"] != "sponsorship"] + [{"match": "sponsorship", "answer": "No"}]
    bank = AnswerBank(PROFILE, rules, {"resume": "/tmp/r.pdf", "cover_letter": None})
    return bank.plan(questions_from_api(API))


def test_readback_says_every_answer(plan):
    text = voice.speak_plan(plan, "Acme", "Data Analyst")
    assert text.startswith("Acme, Data Analyst.")
    assert "From your profile: First Name, Email." in text
    assert "Attached: your tailored resume." in text
    assert "authorized to work in the United States? Yes." in text
    assert "sponsorship? No." in text
    assert "Certifications: CFA." in text
    assert "Left blank, optional: Cover Letter; Why do you want to join?" in text
    assert text.endswith("Say submit Acme to send, or skip.")
    assert "|" not in text and "*" not in text  # nothing a speech engine reads as symbols


def test_readback_asks_for_blocking_questions():
    bank = AnswerBank(PROFILE, RULES, {"resume": "/tmp/r.pdf", "cover_letter": None})  # sponsorship = ASK
    text = voice.speak_plan(bank.plan(questions_from_api(API)), "Acme", "Data Analyst")
    assert "I need you for 1 question." in text
    assert "require sponsorship? Options: Yes, No." in text
    assert "Say submit" not in text


def test_tsenta_readback():
    text = voice.speak_tsenta(PROFILE, "Acme", "Data Analyst")
    assert "Email: alex@example.com." in text
    assert "Authorized to work: yes. Needs sponsorship: no." in text
    assert text.endswith("Say submit Acme to send, or skip.")


def test_digest_follows_answers_and_resume(plan, tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1 a")
    d = voice.plan_digest(plan, pdf)
    assert voice.plan_digest(plan, pdf) == d
    pdf.write_bytes(b"%PDF-1 b")
    assert voice.plan_digest(plan, pdf) != d
    plan[-1].value = "something else"
    assert voice.plan_digest(plan, pdf) != voice.plan_digest(plan[:-1], pdf)


# ------------------------------------------------------------ the spoken go-ahead

def pending(company="Acme", digest="d1", at=NOW):
    return voice.Pending(url=URL, company=company, title="Data Analyst", digest=digest, route="filler",
                         pdf="", read_at=at.isoformat())


@pytest.mark.parametrize("said", ["Submit Acme.", "yes, submit acme", "OK submit Acme Inc please",
                                  "submit acme's application"])
def test_go_ahead(said):
    ok, reason = voice.check_confirmation(said, pending(), URL, "d1", now=NOW)
    assert ok, reason


@pytest.mark.parametrize("said,why", [
    ("yes", "say submit Acme"),
    ("sure go ahead", "say submit Acme"),
    ("don't submit Acme", "a no or a wait"),
    ("submit acme, wait", "a no or a wait"),
    ("submit stripe", "didn't catch the company"),
    ("submit", "didn't catch the company"),
])
def test_refusals(said, why):
    ok, reason = voice.check_confirmation(said, pending(), URL, "d1", now=NOW)
    assert not ok and why in reason


def test_company_words_are_not_negatives():
    ok, _ = voice.check_confirmation("submit hold co", pending(company="Hold Co"), URL, "d1", now=NOW)
    assert ok


def test_dictation_splits_company_names():
    ok, _ = voice.check_confirmation("submit data dog", pending(company="Datadog"), URL, "d1", now=NOW)
    assert ok


def test_refuses_without_matching_readback():
    assert not voice.check_confirmation("submit acme", None, URL, "d1", now=NOW)[0]
    assert "changed" in voice.check_confirmation("submit acme", pending(), URL, "d2", now=NOW)[1]
    other = "https://job-boards.greenhouse.io/acme/jobs/999"
    assert "not this one" in voice.check_confirmation("submit acme", pending(), other, "d1", now=NOW)[1]
    stale = pending(at=NOW - timedelta(minutes=31))
    assert "minutes" in voice.check_confirmation("submit acme", stale, URL, "d1", now=NOW)[1]
    # tracking parameters don't make it a different job
    assert voice.check_confirmation("submit acme", pending(), URL + "?gh_src=x", "d1", now=NOW)[0]


# ------------------------------------------------------------ CLI: Tsenta path and hands-on list

def test_tsenta_readback_then_confirm(tmp_path, capsys):
    (tmp_path / "profile.json").write_text(json.dumps(PROFILE))
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1 x")
    args = ["--runs", str(tmp_path)]
    assert voice.main(args + ["readback-tsenta", "--pdf", str(pdf), "--company", "Acme",
                              "--title", "Data Analyst", "--url", URL]) == 0
    assert voice.main(args + ["confirm", "--url", URL, "yes"]) == 2
    pdf.write_bytes(b"%PDF-1 changed")
    assert voice.main(args + ["confirm", "--url", URL, "submit acme"]) == 2  # resume changed since read-back
    pdf.write_bytes(b"%PDF-1 x")
    assert voice.main(args + ["confirm", "--url", URL, "submit acme"]) == 0
    assert voice.main(args + ["confirm", "--url", URL, "submit acme"]) == 2  # used up: one go-ahead per read-back
    out = capsys.readouterr().out
    assert "CONFIRMED: Submitting Acme." in out


def test_hands_on_list(tmp_path, capsys):
    args = ["--runs", str(tmp_path)]
    voice.main(args + ["later", "list"])
    assert "Nothing is waiting" in capsys.readouterr().out
    voice.main(args + ["later", "add", "Finish the captcha on Acme", "--url", URL])
    voice.main(args + ["later", "list"])
    out = capsys.readouterr().out
    assert "1 thing needs your hands:" in out and "Finish the captcha on Acme" in out and URL in out


# ------------------------------------------------------------ filler CLI end to end (no network, no browser)

@pytest.fixture
def runs(tmp_path, monkeypatch):
    (tmp_path / "profile.json").write_text(json.dumps(PROFILE))
    rules = [r for r in RULES if r["match"] != "sponsorship"] + [{"match": "sponsorship", "answer": "No"}]
    (tmp_path / "answers.json").write_text(json.dumps({"rules": rules}))
    job = tmp_path / "job"
    job.mkdir()
    (job / "resume.pdf").write_bytes(b"%PDF-1 resume")
    data = dict(API, company_name="Acme")
    monkeypatch.setattr(filler_cli, "fetch_form", lambda url: (data, questions_from_api(API)))
    sent = []

    class Report:
        filled, failed, hidden, captcha, screenshot = ["x"], [], [], False, "shot.png"
        submitted, confirmation = True, "Thanks for applying"

    def fake_fill(url, plan, shot, submit):
        sent.append(submit)
        return Report()

    monkeypatch.setattr(filler_cli, "fill_form", fake_fill)
    return tmp_path, sent


def test_filler_speak_then_voice_submit(runs, capsys):
    tmp, sent = runs
    base = ["--runs", str(tmp), "--pdf", str(tmp / "job" / "resume.pdf")]
    assert filler_cli.main(["fill", URL, "--submit", "--voice-confirm", "submit acme"] + base) == 4
    assert sent == []  # no read-back yet: nothing opened

    assert filler_cli.main(["plan", URL, "--speak"] + base) == 0
    out = capsys.readouterr().out
    assert "SPOKEN:\nAcme, Data Analyst." in out and "Say submit Acme" in out

    assert filler_cli.main(["fill", URL, "--submit", "--voice-confirm", "yeah"] + base) == 4
    assert sent == []
    assert filler_cli.main(["fill", URL, "--submit", "--voice-confirm", "Submit Acme."] + base) == 0
    assert sent == [True]
    assert "CONFIRMED" in capsys.readouterr().out
    assert voice.Pending.load(tmp) is None


def test_filler_refuses_when_answers_change_after_readback(runs):
    tmp, sent = runs
    base = ["--runs", str(tmp), "--pdf", str(tmp / "job" / "resume.pdf")]
    assert filler_cli.main(["plan", URL, "--speak"] + base) == 0
    rules = json.loads((tmp / "answers.json").read_text())
    rules["rules"].append({"match": "join", "answer": "I like the mission"})
    (tmp / "answers.json").write_text(json.dumps(rules))
    assert filler_cli.main(["fill", URL, "--submit", "--voice-confirm", "submit acme"] + base) == 4
    assert sent == []


def test_voice_confirm_needs_submit(runs):
    tmp, _ = runs
    with pytest.raises(SystemExit):
        filler_cli.main(["fill", URL, "--voice-confirm", "submit acme", "--runs", str(tmp),
                         "--pdf", str(tmp / "job" / "resume.pdf")])
