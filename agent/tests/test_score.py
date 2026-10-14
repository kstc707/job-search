"""Tests for the knockout screen and fit score. Fixtures are synthetic: no real candidate data."""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jobagent import jd, score, screen  # noqa: E402

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config.example.json")))
TODAY = dt.date(2026, 10, 13)

FACTS = """# Facts
- Built dashboards in Power BI with DAX for weekly crime and arrest trend reporting.
- Wrote SQL and Python (pandas) to clean court records and reconcile 4 record types.
- Trained logistic regression and gradient boosting models; reported AUC and recall.
"""

ANALYST = ("Crime Analyst. Analyze crime trends and arrest data, build dashboards in Power BI, "
           "write SQL queries, and brief leadership on weekly trends. 1+ years of experience.")
ENGINEER = ("Platform Engineer. Build services in Java and Kubernetes on AWS with Docker, "
            "Spark pipelines and Terraform. 2 years of experience.")

MAP = """| Responsibility | Evidence | Where |
|---|---|---|
| Analyze crime trends | Weekly arrest trend reporting | DA |
| Build dashboards | Power BI, 32 DAX measures | Project |
| GIS mapping | GAP | — |
| Preferred: IACA membership | GAP | — |
"""


def test_jd_header_is_optional():
    meta, text = jd.parse('{"title": "Analyst", "yearsOfExperienceMin": 2}\n\nThe posting.')
    assert meta["title"] == "Analyst" and text == "The posting."
    assert jd.parse("Just text.") == ({}, "Just text.")


def test_screen_knockouts():
    assert screen.screen({"title": "Data Analyst"}, ANALYST, CFG) == []
    assert "requires U.S. citizenship" in screen.screen(
        {}, "* U.S. Citizenship with the ability to obtain a security clearance.", CFG)
    assert "requires a security clearance" in screen.screen({}, "Active Secret clearance.", CFG)
    assert screen.screen({"title": "Senior Data Scientist"}, "", CFG)[0].startswith("senior title")
    assert screen.screen({}, "Requires 5+ years of professional experience.", CFG) == [
        "asks for 5+ years (limit 2)"]
    assert screen.screen({}, "Must be currently enrolled in a degree program.", CFG) == ["student-only"]


def test_sponsorship_only_matters_when_needed():
    text = "We are unable to sponsor visas for this role."
    assert screen.screen({}, text, CFG) == []
    needs = {**CFG, "work_authorization": {**CFG["work_authorization"], "needs_sponsorship": True}}
    assert screen.screen({}, text, needs) == ["no visa sponsorship"]


def test_required_years_prefers_feed_value():
    assert screen.required_years({"yearsOfExperienceMin": 3}, "1 year of experience") == 3
    assert screen.required_years({}, "2+ years of SQL experience and 4 years of experience") == 4
    assert screen.required_years({}, "No experience needed.") is None


def test_terms_match_plurals_and_respect_case():
    assert "dashboards" in score.terms_in("built a dashboard")
    assert "R" in score.terms_in("Python or R")
    assert "R" not in score.terms_in("our team")
    assert "REST" not in score.terms_in("the rest of the team")


def test_prebuild_gate_ranks_fit_above_misfit():
    fit = score.score({"title": "Crime Analyst"}, ANALYST, CFG, FACTS, today=TODAY)
    misfit = score.score({"title": "Platform Engineer"}, ENGINEER, CFG, FACTS, today=TODAY)
    assert fit["decision"] == "build" and fit["score"] > misfit["score"]
    assert "parse" in fit["estimated"] and "signal" in fit["estimated"]
    assert set(misfit["missing_terms"]) >= {"Java", "Kubernetes", "AWS", "Docker"}


def test_knockout_zeroes_the_score():
    r = score.score({"title": "Crime Analyst"}, ANALYST + " U.S. citizenship required.", CFG,
                    FACTS, today=TODAY)
    assert r["score"] == 0 and r["decision"] == "skip"


def test_postbuild_uses_map_and_signal():
    meta = {"title": "Crime Analyst", "datePosted": "2026-10-12"}
    base = score.score(meta, ANALYST, CFG, FACTS, jd_map_text=MAP, resume_text=FACTS, today=TODAY)
    assert base["parts"]["required"] == 20.0          # 2 of 3 required rows covered
    assert base["parts"]["preferred"] == 0.0          # the preferred row is a GAP
    assert base["parts"]["freshness"] == 10
    hot = score.score(meta, ANALYST, CFG, FACTS, jd_map_text=MAP, resume_text=FACTS,
                      signal=1.0, today=TODAY)
    assert hot["score"] == base["score"] + 8          # 15 instead of the neutral 7
    assert base["decision"] in ("review", "auto", "skip")


def test_parse_points():
    good = "Alex Rivera\nalex.rivera@example.com\nProfessional Summary\nEducation\n" \
           "Technical Skills\nProfessional Experience\nProjects\n"
    assert score.parse_points(good, CFG) == 10
    assert score.parse_points("Projects\nEducation\n", CFG) < 5


def test_rank_caps_and_drops_skips():
    rs = [{"score": s, "decision": d} for s, d in
          [(70, "build"), (90, "build"), (0, "skip"), (60, "build")]]
    assert [r["score"] for r in score.rank(rs, 2)] == [90, 70]


def test_screen_drops_jobs_that_exclude_opt():
    from jobagent import screen
    cfg = {"work_authorization": {"on_opt": True}}
    text = "We do not sponsor visas. Candidates on F-1, OPT, or STEM OPT are not eligible for this role."
    assert "does not accept OPT work authorization" in screen.screen({}, text, cfg)
    text2 = "The company will not support F-1 OPT or STEM OPT work authorization."
    assert "does not accept OPT work authorization" in screen.screen({}, text2, cfg)
    assert screen.screen({}, "Optimize reporting; option to work remote.", cfg) == []
    assert screen.screen({}, text, {"work_authorization": {"on_opt": False}}) == []
    # wording seen in real postings (Aperia, Public Storage)
    assert screen.screen({}, "candidates currently on F-1, OPT, STEM OPT status are not eligiable for this role.", cfg)
    assert screen.screen({}, "We do not provide training plans or support for F-1 OPT, STEM OPT extensions.", cfg)
