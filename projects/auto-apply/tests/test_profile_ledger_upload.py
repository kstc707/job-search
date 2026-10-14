from datetime import date

import pytest

from auto_apply.ledger import Entry, Ledger, normalize_url
from auto_apply.profile import build_apply_profile, extract_profile_data, missing_fields
from auto_apply.upload import validate_pdf


# --- profile -----------------------------------------------------------------

@pytest.mark.parametrize("wrap", [
    lambda d: d,
    lambda d: {"id": "p1", "data": d},
    lambda d: {"tool": "get-resume-profile", "result": {"id": "p1", "data": d}},
])
def test_extract_accepts_every_tool_response_shape(profile, wrap):
    assert extract_profile_data(wrap(profile)) == profile


def test_extract_rejects_non_profiles():
    with pytest.raises(ValueError, match="not a Tsenta resume profile"):
        extract_profile_data({"result": {"items": []}})


def test_complete_profile_has_nothing_missing(profile):
    assert missing_fields(profile) == []
    assert build_apply_profile(profile) == profile


def test_false_is_a_valid_answer_but_empty_is_missing(profile):
    profile["workAuthorization"]["needsSponsorship"] = False
    profile["personalInformation"]["phone"] = ""
    profile["workExperience"] = []
    assert missing_fields(profile) == ["phone", "work experience"]
    with pytest.raises(ValueError, match="phone, work experience"):
        build_apply_profile(profile)


# --- ledger ------------------------------------------------------------------

def test_normalize_url_drops_tracking_and_trailing_slash():
    a = normalize_url("https://Jobs.Lever.co/acme/123/?utm_source=x&lever-source=LinkedIn")
    b = normalize_url("https://jobs.lever.co/acme/123")
    assert a == b
    # Meaningful parameters are kept.
    assert "gh_jid=42" in normalize_url("https://acme.com/careers?gh_jid=42&utm_medium=y")


def test_ledger_dedupes_by_url_and_job_id(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    assert ledger.find(url="https://x.com/job/1") is None
    ledger.add(Entry(company="Acme", title="Analyst", url="https://x.com/job/1/?utm_source=t", job_id="J1"))
    assert ledger.find(url="https://x.com/job/1").company == "Acme"
    assert ledger.find(job_id="J1").title == "Analyst"
    assert ledger.find(job_id="J2", url="https://x.com/job/2") is None


def test_ledger_counts_today(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.add(Entry(company="A", title="t"))
    ledger.add(Entry(company="B", title="t", at="2020-01-01T12:00:00+00:00"))
    assert ledger.count_on(date.today()) == 1


# --- upload ------------------------------------------------------------------

def test_validate_pdf_accepts_minimal_pdf():
    validate_pdf(b"%PDF-1.5\n...\n%%EOF\n")


@pytest.mark.parametrize("data,msg", [
    (b"<html>", "not a PDF"),
    (b"%PDF-1.5\n" + b"x" * 100, "truncated"),
])
def test_validate_pdf_rejects_bad_input(data, msg):
    with pytest.raises(ValueError, match=msg):
        validate_pdf(data)


def test_validate_pdf_enforces_size_limit():
    with pytest.raises(ValueError, match="limit"):
        validate_pdf(b"%PDF-1.5\n%%EOF", max_bytes=5)
