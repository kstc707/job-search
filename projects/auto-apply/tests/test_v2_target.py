from datetime import datetime, timezone

from auto_apply.v2.target import judge, location_tier, rank, title_target

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def test_titles():
    assert title_target("Data Analyst") == "in"
    assert title_target("Business Intelligence Analyst") == "in"
    assert title_target("Reporting Analyst - Remote") == "in"
    for t in ["Data Scientist", "ML Engineer", "Analytics Engineer", "AI Engineer", "Applied AI Engineer",
              "Software Engineer, Agents", "LLM Application Developer", "Data Engineer", "Data Analyst II",
              "Machine Learning Scientist", "Software Engineer - Data Platform"]:
        assert title_target(t) == "in", t
    for t in ["Senior Data Analyst", "Sr. Business Analyst", "Data Analyst Intern", "Analytics Manager",
              "Staff ML Engineer", "Lead AI Engineer", "Data Scientist III", "AI Sales Engineer"]:
        assert title_target(t) == "off", t
    for t in ["Customer Success Specialist", "Software Engineer", "Frontend Developer", "Research Scientist, Chemistry"]:
        assert title_target(t) == "other", t


def test_location_order_matches_sai():
    names = [location_tier(l)[1] for l in ["Memphis, TN", "Remote", "Atlanta, GA", "Birmingham, AL", "Austin, TX"]]
    assert names == ["Memphis", "Remote", "Atlanta", "Alabama", "Rest of US"]
    assert location_tier("Collierville, TN")[1] == "Memphis"
    assert location_tier("Alpharetta, GA")[1] == "Atlanta"


def test_freshness_and_ranking():
    jobs = [
        {"title": "Data Analyst", "location": "Austin, TX", "posted": "2026-10-18T12:00:00Z", "score": 90},
        {"title": "Data Analyst", "location": "Remote", "posted": "2026-10-18T00:00:00Z", "score": 70},
        {"title": "Data Analyst", "location": "Memphis, TN", "posted": "October 17, 2026", "score": 60},
        {"title": "Data Analyst", "location": "Memphis, TN", "posted": "2026-10-01T00:00:00Z", "score": 95},
        {"title": "Senior Data Scientist", "location": "Memphis, TN", "posted": "2026-10-19T00:00:00Z", "score": 99},
    ]
    out = rank(jobs, now=NOW)
    assert [(j["location"], v.keep) for j, v in out] == [
        ("Memphis, TN", True), ("Remote", True), ("Austin, TX", True), ("Memphis, TN", False), ("Memphis, TN", False)]
    assert "days ago" in out[3][1].reason and "off-target" in out[4][1].reason
    assert judge({"title": "Data Analyst", "location": "Remote"}, now=NOW).keep  # unknown date: kept


def test_one_role_per_company_keeps_the_best_ranked():
    jobs = [{"title": "Data Analyst", "company": "Hooli", "location": "Austin, TX", "posted": "2026-10-19T08:00:00Z"},
            {"title": "Data Scientist", "company": "Hooli Inc", "location": "Memphis, TN", "posted": "2026-10-19T08:00:00Z"},
            {"title": "Data Analyst", "company": "Initech", "location": "Remote", "posted": "2026-10-19T08:00:00Z"}]
    out = rank(jobs, now=NOW)
    kept = [(j["company"], j["location"]) for j, v in out if v.keep]
    assert kept == [("Hooli Inc", "Memphis, TN"), ("Initech", "Remote")]
    dropped = [v.reason for j, v in out if not v.keep]
    assert dropped == ["another role at this company ranks higher this run"]
