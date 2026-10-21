"""Gmail -> outcome inbox rows. Every message, company and person here is made up."""

import json

from auto_apply.v2 import gmail_inbox as gi
from auto_apply.v2.outcomes import build_plan


def gm(i, sender, subject, snippet, labels=("CATEGORY_UPDATES", "INBOX"), date="2026-10-10T12:00:00Z", **kw):
    return {"id": i, "threadId": i, "sender": sender, "toRecipients": ["alex@example.com"], "subject": subject,
            "snippet": snippet, "date": date, "internalDate": "1791000000000", "labelIds": list(labels), **kw}


ACK = gm("a1", "acmehealth@myworkday.com", "Application Received",
         "Hello Alex, Thank you for your interest in Acme Health and the Data Analyst - Reporting position. "
         "Your application was received and will be reviewed.")
REJECT = gm("r1", "Acme Hiring Team <no-reply@us.greenhouse-mail.io>", "Your application to Acme",
            "Thank you for applying for the Business Intelligence Analyst role. Unfortunately, we have decided "
            "to move forward with other candidates.")
INTERVIEW = gm("i1", "Jordan Lee <jordan.lee@bluerivertech.example>", "Interview invitation - Reporting Analyst",
               "Hi Alex, we would like to invite you to a phone interview. Please share your availability for "
               "next week.", labels=("CATEGORY_PERSONAL", "INBOX"))
HIREVUE = gm("s1", "Cobalt Recruiting <noreply@hirevue.com>", "Complete your HireVue interview",
             "Cobalt has invited you to complete an on-demand video interview for the Data Analyst position.")
CODILITY = gm("s2", "no-reply@codility.com", "Your test invitation",
              "You have been invited to complete a coding test for your application.")
OFFER = gm("o1", "Pat Kim <pat.kim@deltalabs.example>", "Offer letter - Junior Data Analyst",
           "Hi Alex, we are pleased to extend an offer for the Junior Data Analyst position at Delta Labs. "
           "Your offer letter is attached.", labels=("INBOX",))
PERSON = gm("p1", "Sam Rivera <sam.rivera@orbitanalytics.example>", "Re: Analyst role",
            "Thanks for getting back to me. Could you send your updated resume and a good number to reach you?",
            labels=("INBOX",))


def cat(m):
    return gi.classify(m)[0]


def test_each_outcome_category_has_a_rule():
    assert cat(ACK) == "ACKNOWLEDGMENT"
    assert cat(REJECT) == "REJECTION"
    assert cat(INTERVIEW) == "INTERVIEW"
    assert cat(HIREVUE) == "ASSESSMENT"           # a recorded AI screen is a step, not an interview
    assert cat(CODILITY) == "ASSESSMENT"
    assert cat(OFFER) == "OFFER"
    assert cat(PERSON) == "RECRUITER_MESSAGE"


def test_rule_names_are_reported():
    assert "move forward" in gi.classify(REJECT)[1]
    assert gi.classify(PERSON)[1].startswith("written by a person")


def test_an_acknowledgment_that_mentions_a_future_interview_is_not_an_invitation():
    m = gm("a2", "no-reply@hire.lever.co", "Thank you for applying to Example Freight",
           "We have received your application. If your qualifications match, we will contact you to schedule "
           "an interview. Should we decide not to move forward, we will let you know.")
    assert cat(m) == "ACKNOWLEDGMENT"


def test_alerts_newsletters_account_notices_and_unrelated_mail():
    assert cat(gm("j1", "donotreply@jobalert.indeed.com", "Data Analyst at Example Co. 3 more jobs",
                  "Under general supervision, designs and implements processes")) == "JOB_ALERT"
    assert cat(gm("j2", "acme@nurture.icims.com", "Acme Talent Newsletter",
                  "Thanks for staying connected with Acme. Explore your next career opportunity")) == "JOB_ALERT"
    assert cat(gm("j3", "acme@myworkday.com", "Candidate Home account deactivated",
                  "The Candidate Home account associated with this email address has been deactivated.")) == "GENERAL"
    assert cat(gm("n1", "deals@shop.example", "Accept your offer before it's gone!",
                  "Get credit back on your next order")) == "NOT_JOB"     # "offer" alone is not a job offer
    assert cat(gm("n2", "admissions@university.example", "Applications are now open",
                  "Submit your application for Fall 2027")) == "NOT_JOB"


def test_a_job_email_no_rule_understands_is_unclassified():
    m = gm("u1", "notifications@smartrecruiters.com", "Message regarding Data Analyst",
           "Please log in to view a message about the position.")
    assert cat(m) == "UNCLASSIFIED"


def test_company_and_title_extraction():
    row = gi.to_inbox_row(ACK)
    assert row["application"] == {"companyName": "Acme Health",
                                  "trackedApplication": {"positionTitle": "Data Analyst - Reporting"}}
    row = gi.to_inbox_row(REJECT)
    assert row["application"]["companyName"] == "Acme"
    assert row["application"]["trackedApplication"]["positionTitle"] == "Business Intelligence Analyst"
    row = gi.to_inbox_row(OFFER)
    assert row["application"]["companyName"] == "Delta Labs"
    assert row["application"]["trackedApplication"]["positionTitle"] == "Junior Data Analyst"
    assert gi.to_inbox_row(HIREVUE)["application"]["companyName"] == "Cobalt"   # from "Cobalt Recruiting"


def test_title_from_subject_parts_and_requisition_ids_are_dropped():
    assert gi.extract_title("Interview invitation - Reporting Analyst", "") == "Reporting Analyst"
    assert gi.extract_title("Data Analyst II (R12345) | Application update", "") == "Data Analyst II"
    assert gi.extract_title("Your application", "Thanks for applying for the Pricing Analyst role at Zeta.") \
        == "Pricing Analyst"
    assert gi.extract_company("Thank you for applying to Example Freight!", "") == "Example Freight"
    assert gi.extract_company("", "the position of Analyst at Bank of Example.") == "Bank of Example"
    assert gi.extract_company("Your application", "") == ""


def test_weak_company_guesses_never_become_linked_applications():
    row = gi.to_inbox_row(gm("w1", "cobalt@myworkday.com", "Application update",
                             "Unfortunately, we will not be moving forward with your application."))
    assert row["category"] == "REJECTION" and row["application"] is None and row["fromName"] == "cobalt"
    row = gi.to_inbox_row(INTERVIEW)  # a person wrote it: their company domain is only a hint
    assert row["application"] is None and row["fromName"] == "bluerivertech"


def test_display_name_helpers():
    assert gi.company_from_display("Acme Hiring Team") == "Acme"
    assert gi.company_from_display("Example Freight Talent Acquisition") == "Example Freight"
    assert gi.company_from_display("Jordan Lee") == ""
    assert gi.looks_like_person("Jordan Lee via Greenhouse")
    assert not gi.looks_like_person("Workday")


def test_connector_shapes_html_entities_sent_mail_and_dedupe():
    search = {"threads": [{"id": "t1", "messageCount": 2, "messages": [
        gm("x1", "acme@myworkday.com", "Application Received",
           "Thank you for your interest in O&#39;Brien Example and the Data Analyst position.͏ ͏"),
        gm("x2", "alex@example.com", "Re: Application Received", "Thanks!", labels=("SENT",))]}],
        "nextPageToken": "abc", "resultCountEstimate": "1"}
    thread = {"id": "t1", "messages": [search["threads"][0]["messages"][0]]}  # same message again
    rows, counts = gi.convert(search)
    assert counts["SKIPPED_OWN"] == 1 and len(rows) == 1
    assert rows[0]["application"]["companyName"] == "O'Brien Example"
    assert "͏" not in rows[0]["snippet"] and "&#39;" not in rows[0]["snippet"]
    assert len(gi.load_messages([thread, search["threads"][0]])) == 2   # x1 deduped, x2 kept (skipped later)
    assert gi.load_messages(thread)[0]["id"] == "x1"


def test_received_at_falls_back_to_internal_date():
    m = gm("d1", "acme@myworkday.com", "Application Received", "Your application was received.", date=None)
    assert gi.to_inbox_row(m)["receivedAt"] == "2026-10-03T04:00:00Z"


def test_end_to_end_into_outcomes_build_plan():
    tracker = [
        {"url": "r1", "Job": "Business Intelligence Analyst", "Company": "Acme", "Status": "Applied", "Notes": ""},
        {"url": "r2", "Job": "Data Analyst", "Company": "Cobalt", "Status": "Applied", "Notes": ""},
        {"url": "r3", "Job": "Reporting Analyst", "Company": "Umbra Logistics", "Status": "Applied", "Notes": ""},
    ]
    late_reject = gm("r9", "umbra@myworkday.com", "Application update",
                     "Unfortunately, we have decided not to move forward with your application.",
                     date="2026-10-12T00:00:00Z")
    gmail = {"threads": [{"id": m["id"], "messages": [m]} for m in
                         (REJECT, HIREVUE, OFFER, late_reject,
                          gm("n1", "deals@shop.example", "Accept your offer", "Credit back today"))]}
    rows, counts = gi.convert(gmail)
    assert counts["NOT_JOB"] == 1 and len(rows) == 4
    plan = build_plan(tracker, json.loads(json.dumps(rows)))
    got = {(u.row_url, u.new_status, u.confidence) for u in plan.updates}
    assert got == {("r1", "Rejected", "high"), ("r2", "Waiting", "high"), ("r3", "Rejected", "medium")}
    n, = plan.new_rows
    assert (n.company, n.job, n.status, n.needs_sai) == ("Delta Labs", "Junior Data Analyst", "Offer", True)
    assert not plan.unmatched


def test_cli_prints_counts_and_unclassified(tmp_path, capsys):
    src = tmp_path / "gmail.json"
    src.write_text(json.dumps([ACK, REJECT, gm("u1", "notifications@smartrecruiters.com",
                                                 "Message regarding Data Analyst",
                                                 "Please log in to view a message about the position.")]))
    out = tmp_path / "inbox.json"
    assert gi.main([str(src), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "ACKNOWLEDGMENT     1" in text and "REJECTION          1" in text
    assert "unclassified" in text and "Message regarding Data Analyst" in text
    assert [r["category"] for r in json.loads(out.read_text())] == ["ACKNOWLEDGMENT", "REJECTION", "UNCLASSIFIED"]
