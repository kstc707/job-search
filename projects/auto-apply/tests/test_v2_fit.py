from datetime import datetime, timezone

from auto_apply.v2.fit import posting_skills, score, tier_jobs, years_asked

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
KB = {"python", "sql", "excel", "power bi", "pandas", "a/b testing", "statistics", "dashboards", "kpis", "reporting"}


def job(title="Data Analyst", location="Memphis, TN", posted="2026-10-20T12:00:00Z", description=""):
    return {"title": title, "company": "Acme", "location": location, "posted": posted, "description": description}


def test_skill_terms_and_years():
    text = "Requires SQL, Power BI dashboards, Python (pandas) and 2-4 years of experience. Tableau a plus."
    assert posting_skills(text) == {"sql", "power bi", "dashboards", "python", "pandas", "tableau"}
    assert years_asked(text) == 2
    assert years_asked("No experience needed") is None
    assert "r" not in posting_skills("R&D team")


def test_strong_local_fit_is_tier_a():
    f = score(job(description="SQL, Excel, Power BI dashboards and KPIs reporting. 1+ years."), KB, now=NOW)
    assert f.tier == "A" and f.score >= 70
    assert f.missing == []


def test_gaps_and_distance_lower_the_tier():
    desc = "Spark, Airflow, dbt, Snowflake, Kubernetes and Python; 3 years."
    f = score(job(title="Analytics Engineer", location="Seattle, WA", posted="2026-10-01T00:00:00Z",
                  description=desc), KB, now=NOW)
    assert f.tier in ("B", "C") and f.score < 70
    assert set(f.missing) >= {"spark", "airflow", "dbt", "snowflake", "kubernetes"}


def test_knockouts_force_tier_c():
    for desc in ["Must be a U.S. citizen.", "Active Secret clearance required.", "Must be currently enrolled in a degree program."]:
        assert score(job(description=desc), KB, now=NOW).tier == "C", desc


def test_many_years_cost_the_experience_points():
    f = score(job(description="SQL and Excel. 7+ years of experience."), KB, now=NOW)
    assert f.parts["experience"] == 0 and f.parts["years_asked"] == 7


def test_tier_jobs_orders_best_first():
    rows = tier_jobs([job(location="Austin, TX", description="Tableau, Looker, SAS"),
                      job(description="SQL, Excel, Power BI")], KB, now=NOW)
    assert [r["fit"]["tier"] for r in rows][0] == "A"
    assert rows[0]["fit"]["score"] >= rows[1]["fit"]["score"]


def test_non_us_remote_and_generic_titles_score_lower():
    desc = "SQL, Excel, Power BI dashboards, KPIs, reporting."
    us = score(job(title="Data Analyst", location="Remote", description=desc), KB, now=NOW)
    uk = score(job(title="Data Analyst", location="Remote - UK", description=desc), KB, now=NOW)
    generic = score(job(title="Credit Risk Analyst", location="Remote", description=desc), KB, now=NOW)
    assert us.parts["location"] == 12 and (uk.tier, uk.knockout) == ("C", "outside the US")
    assert us.parts["title"] == 20 and generic.parts["title"] == 10


def test_postings_naming_few_skills_give_little_evidence():
    one = score(job(description="Strong Excel skills."), KB, now=NOW)
    five = score(job(description="Python, SQL, Excel, Power BI, pandas."), KB, now=NOW)
    assert one.parts["skills"] == 9 and five.parts["skills"] == 45


def test_fintech_and_healthcare_get_priority():
    desc = "Python, SQL, pandas, statistics, dashboards."
    base = score(job(title="Data Scientist", location="Austin, TX", description=desc), KB, now=NOW)
    fin = score({**job(title="Data Scientist", location="Austin, TX", description=desc), "industry": "fintech"}, KB, now=NOW)
    health = score(job(title="Data Scientist", location="Austin, TX",
                       description=desc + " Improve patient outcomes for hospitals and clinical teams."), KB, now=NOW)
    once = score(job(title="Data Scientist", location="Austin, TX", description=desc + " See our patient privacy notice."), KB, now=NOW)
    assert fin.score == base.score + 10 and fin.parts["industry"] == "fintech"
    assert health.parts["industry"] == "healthcare" and health.parts["priority"] == 10
    assert once.parts["priority"] == 0


def test_ai_titles_count_as_data_roles():
    f = score(job(title="Applied AI Engineer, Agents", description="Python, LLM, RAG, FastAPI, Docker."), KB | {"llm", "rag", "fastapi", "docker"}, now=NOW)
    assert f.parts["title"] == 20 and f.parts["family"] == "ml_ai"


def test_outside_us_only_when_no_us_option():
    from auto_apply.v2.fit import outside_us
    for loc in ["Paris, France (Remote)", "São Paulo (Remote)", "Remote Canada", "Singapore (Remote)", "Toronto; Ottawa"]:
        assert outside_us(loc), loc
    for loc in ["Remote - United States", "US-SF, US-NYC, US-Remote", "New York; London", "Austin, TX", "Remote", ""]:
        assert not outside_us(loc), loc
