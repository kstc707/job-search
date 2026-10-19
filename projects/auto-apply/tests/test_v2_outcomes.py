"""Outcome sync: emails → tracker status changes (made-up companies and ids)."""

from auto_apply.v2.outcomes import build_plan, company_match

ROWS = [
    {"url": "u1", "Job": "Data Analyst", "Company": "Acme Health, Inc.", "Status": "Applied", "Notes": ""},
    {"url": "u2", "Job": "Business Analyst", "Company": "Blue River", "Status": "Applied", "Notes": ""},
    {"url": "u3", "Job": "Data Scientist", "Company": "Blue River", "Status": "Applied", "Notes": ""},
    {"url": "u4", "Job": "Reporting Analyst", "Company": "Cobalt", "Status": "Drafted", "Notes": "[outcome:m9]"},
]


def msg(i, cat, company, title="", when="2026-10-10T00:00:00Z", sender="no-reply@ats.example"):
    app = {"companyName": company, "trackedApplication": {"positionTitle": title} if title else None}
    return {"id": i, "category": cat, "receivedAt": when, "from": sender, "fromName": company,
            "subject": f"About your application to {company}", "application": app}


def test_company_names_match_across_suffixes():
    assert company_match("Acme Health, Inc.", "acme health")
    assert company_match("The Home Depot", "Home Depot")
    assert not company_match("Blue River", "Red River")


def test_rejection_updates_the_matching_row_with_evidence():
    plan = build_plan(ROWS, [msg("m1", "REJECTION", "Acme Health", "Data Analyst")])
    u, = plan.updates
    assert (u.row_url, u.old_status, u.new_status, u.confidence) == ("u1", "Applied", "Rejected", "high")
    assert u.evidence[0].message_id == "m1" and not u.needs_sai


def test_title_picks_between_two_rows_at_one_company_and_no_title_means_no_guess():
    plan = build_plan(ROWS, [msg("m2", "INTERVIEW", "Blue River", "Data Scientist")])
    assert [(u.row_url, u.new_status, u.needs_sai) for u in plan.updates] == [("u3", "Interview Scheduled", True)]
    plan = build_plan(ROWS, [msg("m3", "REJECTION", "Blue River")])
    assert not plan.updates and not plan.new_rows
    assert [e.message_id for e in plan.unmatched] == ["m3"]  # two Blue River rows, no title: ask


def test_status_never_moves_backwards_but_rejection_ends_it():
    msgs = [msg("a", "INTERVIEW", "Acme Health", "Data Analyst", "2026-10-01T00:00:00Z"),
            msg("b", "ACKNOWLEDGMENT", "Acme Health", "Data Analyst", "2026-10-02T00:00:00Z"),
            msg("c", "REJECTION", "Acme Health", "Data Analyst", "2026-10-05T00:00:00Z")]
    u, = build_plan(ROWS, msgs).updates
    assert u.new_status == "Rejected" and [e.message_id for e in u.evidence] == ["a", "b", "c"]


def test_already_applied_emails_are_skipped_and_unknown_applications_become_new_rows():
    plan = build_plan(ROWS, [msg("m9", "REJECTION", "Cobalt", "Reporting Analyst"),
                             msg("m5", "ACKNOWLEDGMENT", "Delta Labs", "Data Analyst")])
    assert plan.skipped_seen == 1 and not plan.updates
    n, = plan.new_rows
    assert (n.company, n.job, n.status) == ("Delta Labs", "Data Analyst", "Applied")


def test_job_alerts_and_general_mail_are_ignored():
    plan = build_plan(ROWS, [msg("x", "JOB_ALERT", "Acme Health"), msg("y", "GENERAL", "Acme Health")])
    assert not plan.updates and not plan.new_rows and not plan.unmatched
