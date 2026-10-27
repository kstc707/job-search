from datetime import datetime, timezone

import pytest

from auto_apply.v2 import apify, boards

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def test_parse_board_urls():
    assert boards.parse_board_url("https://boards.greenhouse.io/oscar") == {"ats": "greenhouse", "board": "oscar"}
    assert boards.parse_board_url("https://job-boards.greenhouse.io/oscar/jobs/1")["board"] == "oscar"
    assert boards.parse_board_url("https://jobs.lever.co/acme/abc")["company"] == "acme"
    assert boards.parse_board_url("https://jobs.ashbyhq.com/ramp")["company"] == "ramp"
    assert boards.parse_board_url("https://jobs.smartrecruiters.com/SBTGlobalInc/123")["company"] == "SBTGlobalInc"
    wd = boards.parse_board_url("https://ally.wd1.myworkdayjobs.com/en-US/ally/job/x")
    assert wd == {"ats": "workday", "tenant": "ally", "host": "ally.wd1.myworkdayjobs.com", "site": "ally"}
    with pytest.raises(ValueError):
        boards.parse_board_url("https://careers-acme.icims.com/jobs/1")
    assert boards.ats_of("https://careers-acme.icims.com/jobs/1") == "icims"
    assert boards.ats_of("https://jobright.ai/jobs/info/abc") == "jobright"


def test_parse_posted():
    assert boards.parse_posted("Posted Today", NOW) == NOW.isoformat()
    assert boards.parse_posted("Posted Yesterday", NOW).startswith("2026-10-26")
    assert boards.parse_posted("Posted 3 Days Ago", NOW).startswith("2026-10-24")
    assert boards.parse_posted("Posted 30+ Days Ago", NOW).startswith("2026-09-26")
    assert boards.parse_posted("21 minutes ago", NOW).startswith("2026-10-27T11:39")
    assert boards.parse_posted("an hour ago", NOW).startswith("2026-10-27T11:00")
    assert boards.parse_posted(1761480000000, NOW).startswith("2025-10-26")
    assert boards.parse_posted("2026-10-20T10:00:00Z", NOW) == "2026-10-20T10:00:00Z"
    assert boards.parse_posted("", NOW) is None and boards.parse_posted("soon", NOW) is None


class FakeHttp:
    """Answers by URL prefix; records calls."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, body):
        self.calls.append((method, url, body))
        for prefix, resp in self.routes.items():
            if url.startswith(prefix):
                return resp(body) if callable(resp) else resp
        raise ValueError(f"no route for {url}")


GH = {"jobs": [
    {"title": "Data Analyst", "location": {"name": "Memphis, TN"}, "first_published": "2026-10-26T09:00:00Z",
     "absolute_url": "https://boards.greenhouse.io/acme/jobs/1"},
    {"title": "Senior Data Analyst", "location": {"name": "Remote"}, "updated_at": "2026-10-26T09:00:00Z",
     "absolute_url": "https://boards.greenhouse.io/acme/jobs/2"},
    {"title": "Office Manager", "location": {"name": "Memphis, TN"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/3"},
]}


def workday_pages(body):
    # 45 analyst jobs over three pages; like Workday, only the first page carries the total
    start = body["offset"]
    n = min(20, 45 - start)
    return {"total": 45 if start == 0 else 0, "jobPostings": [
        {"title": f"Reporting Analyst {start + i}", "externalPath": f"/job/Memphis/r{start + i}",
         "locationsText": "Memphis, TN", "postedOn": "Posted 2 Days Ago"} for i in range(n)]}


def test_scan_keeps_new_analyst_titles_and_remembers_them():
    http = FakeHttp({
        "https://boards-api.greenhouse.io/v1/boards/acme/": GH,
        "https://bigco.wd5.myworkdayjobs.com/wday/cxs/bigco/External/jobs": workday_pages,
        "https://api.lever.co/": lambda b: (_ for _ in ()).throw(ValueError("404")),
    })
    wl = [{"company": "Acme", "url": "https://boards.greenhouse.io/acme", "tier": "Memphis"},
          {"company": "BigCo", "url": "https://bigco.wd5.myworkdayjobs.com/External", "tier": "Memphis"},
          {"company": "Gone", "url": "https://jobs.lever.co/gone", "tier": "Remote"}]
    seen = {}
    jobs, report = boards.scan(wl, seen, http=http, now=NOW)
    assert [j["title"] for j in jobs][:1] == ["Data Analyst"] and len(jobs) == 46
    acme = jobs[0]
    assert acme == {"title": "Data Analyst", "company": "Acme", "location": "Memphis, TN",
                    "posted": "2026-10-26T09:00:00Z", "url": "https://boards.greenhouse.io/acme/jobs/1",
                    "source": "boards", "ats": "greenhouse", "board_tier": "Memphis"}
    wd = jobs[1]
    assert wd["url"] == "https://bigco.wd5.myworkdayjobs.com/External/job/Memphis/r0" and wd["posted"].startswith("2026-10-25")
    assert [c[2]["offset"] for c in http.calls if c[0] == "POST"] == [0, 20, 40]
    assert report[0] == {"company": "Acme", "postings": 3, "analyst": 1, "new": 1}
    assert "error" in report[2]  # one broken board doesn't stop the scan

    again, _ = boards.scan(wl, seen, http=http, now=NOW)
    assert again == []
    assert len(boards.scan(wl, seen, http=http, now=NOW, include_seen=True)[0]) == 46


def test_other_boards_normalize():
    http = FakeHttp({
        "https://api.lever.co/v0/postings/lc": [{"text": "Data Analyst", "categories": {"location": "Remote"},
                                                  "createdAt": 1761480000000, "hostedUrl": "https://jobs.lever.co/lc/1"}],
        "https://api.ashbyhq.com/posting-api/job-board/ab": {"jobs": [
            {"title": "BI Analyst", "location": "", "isRemote": True, "publishedAt": "2026-10-26T00:00:00Z",
             "jobUrl": "https://jobs.ashbyhq.com/ab/1"},
            {"title": "Hidden Analyst", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/ab/2"}]},
        "https://api.smartrecruiters.com/v1/companies/sr/": {"totalFound": 1, "content": [
            {"id": "77", "name": "Data Analyst", "releasedDate": "2026-10-25T00:00:00Z",
             "location": {"city": "Memphis", "region": "TN"}}]},
    })
    lv = boards.fetch_board({"company": "LC", "url": "https://jobs.lever.co/lc"}, http=http, now=NOW)
    ab = boards.fetch_board({"company": "AB", "url": "https://jobs.ashbyhq.com/ab"}, http=http, now=NOW)
    sr = boards.fetch_board({"company": "SR", "url": "https://jobs.smartrecruiters.com/sr"}, http=http, now=NOW)
    assert lv[0]["url"] == "https://jobs.lever.co/lc/1" and lv[0]["ats"] == "lever"
    assert [(j["title"], j["location"]) for j in ab] == [("BI Analyst", "Remote")]
    assert sr[0]["url"] == "https://jobs.smartrecruiters.com/sr/77" and sr[0]["location"] == "Memphis, TN"


def test_find_guesses_board_slugs():
    http = FakeHttp({"https://boards-api.greenhouse.io/v1/boards/acmeanalytics/": {"jobs": [
        {"title": "Data Analyst", "absolute_url": "https://boards.greenhouse.io/acmeanalytics/jobs/9"},
        {"title": "Recruiter", "absolute_url": "https://boards.greenhouse.io/acmeanalytics/jobs/8"}]}})
    hits = boards.find("Acme Analytics, Inc.", "data analyst", http=http, now=NOW)
    assert [h["url"] for h in hits] == ["https://boards.greenhouse.io/acmeanalytics/jobs/9"]


def test_jobright_items_normalize_and_dedupe():
    item = {"jobTitle": " Data Analyst ", "companyName": "Acme", "location": "Memphis, TN",
            "postedDate": "2 days ago", "applyUrl": "https://jobright.ai/jobs/info/abc",
            "salary": "$60K/yr", "experienceLevel": "Entry", "description": "SQL and Power BI"}
    j = apify.normalize(item, NOW)
    assert j["title"] == "Data Analyst" and j["ats"] == "jobright" and j["posted"].startswith("2026-10-25")
    assert apify.dedupe([j, dict(j)]) == [j]
    ins = apify.search_inputs(["data analyst@Memphis, TN", "reporting analyst@remote"], max_items=20, date_posted="3d")
    assert ins[0]["location"] == "Memphis, TN" and not ins[0]["remoteOnly"]
    assert ins[1]["location"] == "" and ins[1]["remoteOnly"] and ins[1]["experienceLevel"] == "entry"


def test_apify_cli_needs_token(monkeypatch, capsys):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    assert apify.main(["--search", "data analyst@Memphis, TN"]) == 2
    assert "APIFY_TOKEN" in capsys.readouterr().out


def test_apify_cli_budget_guard(monkeypatch, capsys):
    monkeypatch.setenv("APIFY_TOKEN", "x")
    monkeypatch.setattr(apify, "run_actor", lambda *a, **k: pytest.fail("must not run over budget"))
    assert apify.main(["--search", "a@b", "--max-per-search", "500", "--budget-usd", "1"]) == 2
    assert "over --budget-usd" in capsys.readouterr().out
