"""Career-board reader: made-up fixture payloads in the real API shapes, no network."""

import io
import json
import urllib.error
from pathlib import Path

from auto_apply.v2 import boards

FIX = Path(__file__).parent / "fixtures" / "boards"
WATCH = [
    {"name": "Acme Example", "ats": "greenhouse", "board": "acmeexample"},
    {"name": "Blue River Example", "ats": "lever", "board": "blueriverexample"},
    {"name": "Cobalt Example", "ats": "ashby", "board": "cobaltexample"},
]


def fake_fetch(url):
    for ats, name in (("greenhouse", "greenhouse"), ("lever", "lever"), ("ashbyhq", "ashby")):
        if ats in url and "missing" not in url:
            return json.loads((FIX / f"{name}.json").read_text())
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))


def test_api_urls():
    assert boards.API["greenhouse"].format(board="x") == "https://boards-api.greenhouse.io/v1/boards/x/jobs?content=true"
    assert boards.API["lever"].format(board="x") == "https://api.lever.co/v0/postings/x?mode=json"
    assert boards.API["ashby"].format(board="x") == \
        "https://api.ashbyhq.com/posting-api/job-board/x?includeCompensation=true"


def test_greenhouse_normalised_to_jobs_json_shape():
    jobs = boards.from_greenhouse(WATCH[0], json.loads((FIX / "greenhouse.json").read_text()))
    j = jobs[0]
    assert set(j) == {"id", "title", "company", "location", "posted", "url", "source", "ats", "description"}
    assert (j["title"], j["company"], j["location"], j["posted"], j["source"], j["ats"]) == \
        ("Data Analyst, Growth", "Acme Example", "Remote - US", "2026-10-17T14:30:00Z", "board", "greenhouse")
    assert j["url"].endswith("/1001") and j["id"] == "greenhouse:acmeexample:1001"
    assert "<" not in j["description"] and "SQL dashboards" in j["description"]
    assert "- A/B tests & reporting" in j["description"]
    assert jobs[1]["posted"] == "2026-10-16T09:00:00Z"  # no first_published: falls back to updated_at


def test_lever_locations_lists_and_epoch_dates():
    jobs = boards.from_lever(WATCH[1], json.loads((FIX / "lever.json").read_text()))
    j = jobs[0]
    assert j["location"] == "Memphis, TN; Atlanta, GA" and j["posted"] == "2026-10-14T17:46:40Z"
    assert "Own weekly reporting." in j["description"] and "Tableau or Power BI" in j["description"]
    assert jobs[1]["location"] == "Chicago, IL (Remote)"


def test_ashby_skips_unlisted_and_adds_compensation():
    jobs = boards.from_ashby(WATCH[2], json.loads((FIX / "ashby.json").read_text()))
    assert [j["title"] for j in jobs] == ["Reporting Analyst", "Analytics Engineer"]
    assert jobs[0]["location"] == "Atlanta, GA; Birmingham, AL"
    assert jobs[0]["description"].startswith("Compensation: $60K - $75K")
    assert jobs[1]["location"] == "San Francisco, CA (Remote)"


def test_keyword_filters():
    job = {"title": "Senior Data Analyst", "location": "Memphis, TN"}
    assert boards.keep(job, ["analyst"], [], [])
    assert not boards.keep(job, ["analyst"], ["senior"], [])
    assert boards.keep(job, [], [], ["tn", "remote"])
    assert not boards.keep(job, [], [], ["atlanta"])
    assert not boards.keep({"title": "Analytics Engineer", "location": ""}, ["analyst"], [], [])  # whole words


def test_run_filters_sorts_and_survives_a_failing_board():
    watch = WATCH + [{"name": "Gone Example", "ats": "greenhouse", "board": "missing"},
                     {"name": "Bad Example", "ats": "workday", "board": "x"}]
    jobs, results = boards.run(watch, titles=["analyst"], exclude=["senior"], fetch=fake_fetch, workers=2)
    assert [j["title"] for j in jobs] == ["Reporting Analyst", "Data Analyst, Growth", "Business Intelligence Analyst"]
    by = {r.company: r for r in results}
    assert (by["Acme Example"].fetched, by["Acme Example"].kept) == (3, 1)
    assert by["Gone Example"].error.startswith("HTTP 404") and by["Bad Example"].error.startswith("unknown ats")


def test_bad_payload_is_an_error_not_a_crash():
    r = boards.fetch_company(WATCH[0], fetch=lambda url: ["not", "a", "dict"])
    assert r.error.startswith("unexpected payload") and r.jobs == []
    r = boards.fetch_company(WATCH[0], fetch=lambda url: (_ for _ in ()).throw(TimeoutError("slow")))
    assert r.error.startswith("network error")


def test_cli_writes_boards_json(tmp_path, monkeypatch, capsys):
    wl = tmp_path / "watch.json"
    wl.write_text(json.dumps(WATCH))
    monkeypatch.setattr(boards, "http_json", fake_fetch)
    out = tmp_path / "boards.json"
    assert boards.main([str(wl), "--title", "analyst", "--location", "tn", "--out", str(out)]) == 0
    rows = json.loads(out.read_text())
    assert [r["title"] for r in rows] == ["Business Intelligence Analyst"]
    assert "1 job(s) kept from 3/3 board(s)" in capsys.readouterr().out


def test_watchlist_example_is_well_formed():
    wl = json.loads((Path(__file__).parent.parent / "prompts" / "watchlist.example.json").read_text())
    assert len(wl) >= 15 and {w["ats"] for w in wl} == {"greenhouse", "lever", "ashby"}
    assert all(set(w) == {"name", "ats", "board"} and w["board"] for w in wl)
