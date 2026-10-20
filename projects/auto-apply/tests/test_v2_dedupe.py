from datetime import date

from auto_apply.v2.dedupe import dedupe, req_id

TODAY = date(2026, 10, 20)

TRACKER = [
    {"Job": "Acme Corp - Data Analyst", "Company": "Acme Corp", "Status": "Applied",
     "Apply URL": "https://boards.greenhouse.io/acme/jobs/4012345?gh_src=abc", "date:Date:start": "2026-09-01"},
    {"Job": "Globex - Reporting Analyst", "Company": "Globex", "Status": "Drafted",
     "Apply URL": "https://globex.wd5.myworkday.com/en-US/careers/job/Memphis/Reporting-Analyst_R10442",
     "date:Date:start": "2026-10-15"},
    {"Job": "Initech - BI Analyst", "Company": "Initech", "Status": "Rejected", "date:Date:start": "2026-06-01"},
    {"Job": "Umbrella - Data Analyst", "Company": "Umbrella", "Status": "Skipped", "date:Date:start": "2026-10-18"},
]


def run(jobs, **kw):
    return [(j["title"], v.keep, v.reason) for j, v in dedupe(jobs, TRACKER, today=TODAY, **kw)]


def test_req_id_patterns():
    assert req_id("https://boards.greenhouse.io/acme/jobs/4012345") == "4012345"
    assert req_id("https://x.wd5.myworkday.com/careers/job/Memphis/Analyst_R10442") == "R10442"
    assert req_id("https://x.wd1.myworkday.com/job/Analyst_JR-0042?src=li") == "JR-0042"
    assert req_id("https://jobs.lever.co/acme/1b2c3d4e-0000-4000-8000-123456789abc/apply") == \
        "1B2C3D4E-0000-4000-8000-123456789ABC"
    assert req_id("https://example.com/careers") == ""


def test_same_posting_with_tracking_params():
    out = run([{"title": "Analyst, Data", "company": "Acme",
                "url": "https://boards.greenhouse.io/acme/jobs/4012345?utm_source=indeed"}])
    assert out == [("Analyst, Data", False, "same posting")]


def test_same_requisition_on_another_url():
    out = run([{"title": "Ops Reporting Analyst", "company": "Globex Inc",
                "url": "https://www.globex.com/careers/job?jobId=R10442"}], cooldown_days=0)
    assert out[0][1] is False and "requisition" in out[0][2]


def test_repost_same_company_similar_title_any_age():
    out = run([{"title": "Data Analyst", "company": "ACME Corporation", "url": "https://indeed.com/viewjob?jk=1"}],
              cooldown_days=0)
    assert out == [("Data Analyst", False, "same company and title (repost or another board)")]


def test_company_cooldown_counts_drafted_but_not_skipped():
    jobs = [{"title": "Financial Analyst", "company": "Globex", "url": "https://globex.com/a"},
            {"title": "Pricing Analyst", "company": "Umbrella", "url": "https://umbrella.com/b"}]
    out = run(jobs)
    assert out[0][1] is False and "cooldown" in out[0][2]
    assert out[1] == ("Pricing Analyst", True, "new")


def test_old_rows_outside_cooldown_allow_a_new_role():
    out = run([{"title": "Marketing Analyst", "company": "Initech", "url": "https://initech.com/m"}])
    assert out == [("Marketing Analyst", True, "new")]


def test_duplicates_inside_one_batch():
    jobs = [{"title": "Data Analyst", "company": "Hooli", "url": "https://indeed.com/viewjob?jk=9"},
            {"title": "Data Analyst", "company": "Hooli Inc", "url": "https://hooli.com/careers/77"},
            {"title": "Supply Chain Analyst", "company": "Hooli", "url": "https://hooli.com/careers/78"}]
    out = run(jobs)
    assert [k for _, k, _ in out] == [True, False, False]
    assert "cooldown" in out[2][2]
