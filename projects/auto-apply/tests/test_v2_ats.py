from auto_apply.v2.ats_check import check_text

BODY = ("Alex Rivera alex@example.com +1 555-010-0199 " + "Summary text. " * 20 +
        "Education University Aug 2024 - May 2026 Skills SQL Experience Analyst Jul 2023 - Present Projects X")


def test_clean_resume_passes():
    rep = check_text(BODY, "alex@example.com", "+15550100199")
    assert rep.ok, rep.problems


def test_en_dash_dates_missing_email_and_garbage_fail():
    bad = BODY.replace("Aug 2024 - May 2026", "Aug 2024 – May 2026").replace("alex@example.com", "(cid:12)")
    rep = check_text(bad, "alex@example.com", "+15550100199")
    assert not rep.ok
    assert any("U+2013" in d for d in rep.dash_ranges)
    assert any("email" in p for p in rep.problems) and any("garbled" in p for p in rep.problems)
