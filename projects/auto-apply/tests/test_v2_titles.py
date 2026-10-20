import pytest

from auto_apply.v2.titles import check_text, choose, family, validate

CONFIG = {"jobs": [
    {"employer": "County Office", "base": "Data Analyst Intern", "fixed": True},
    {"employer": "State University", "base": "Graduate Assistant",
     "variants": {"ml_ai": "Graduate Assistant (Machine Learning & IT)",
                  "data_science": "Graduate Assistant (Machine Learning & IT)",
                  "bi": "Graduate Assistant (Data & IT Services)"}},
    {"employer": "Big Consultancy", "base": "Data Analyst",
     "variants": {"bi": "Data Analyst (Business Intelligence)",
                  "product": "Data Analyst (Product Analytics)"}},
]}


def test_families():
    cases = {
        "Data Analyst": "data_analyst",
        "Business Intelligence Analyst": "bi",
        "Data Analyst - Power BI": "bi",
        "Product Analyst, Growth": "product",
        "Associate Data Scientist": "data_science",
        "Machine Learning Engineer": "ml_ai",
        "Data Analyst, AI Products": "ml_ai",
        "Analytics Engineer": "data_engineering",
        "Business Systems Analyst": "business_analyst",
        "Reporting Analyst": "reporting",
        "Customer Success Specialist": "other",
    }
    assert {t: family(t) for t in cases} == cases


def test_plain_data_analyst_posting_keeps_every_base_title():
    fam, choices = choose(CONFIG, "Data Analyst")
    assert fam == "data_analyst"
    assert [c.title for c in choices] == ["Data Analyst Intern", "Graduate Assistant", "Data Analyst"]
    assert not any(c.changed for c in choices)


def test_bi_posting_uses_variants_but_never_the_fixed_intern_title():
    _, choices = choose(CONFIG, "BI Analyst")
    assert [c.title for c in choices] == [
        "Data Analyst Intern", "Graduate Assistant (Data & IT Services)", "Data Analyst (Business Intelligence)"]
    assert choices[0].reason == "fixed title"


def test_family_without_a_variant_falls_back_to_base():
    _, choices = choose(CONFIG, "Data Scientist")
    assert [c.title for c in choices] == [
        "Data Analyst Intern", "Graduate Assistant (Machine Learning & IT)", "Data Analyst"]


@pytest.mark.parametrize("bad, msg", [
    ({"jobs": [{"employer": "X", "base": "Data Analyst", "variants": {"bi": "BI Developer"}}]}, "verbatim"),
    ({"jobs": [{"employer": "X", "base": "Intern", "fixed": True, "variants": {"bi": "Intern (BI)"}}]}, "fixed"),
    ({"jobs": [{"employer": "X", "base": "Analyst", "variants": {"finance": "Analyst (Finance)"}}]}, "unknown family"),
])
def test_validate_rejects_titles_that_drop_the_base(bad, msg):
    with pytest.raises(ValueError, match=msg):
        validate(bad)


def test_check_text_finds_missing_titles():
    _, choices = choose(CONFIG, "BI Analyst")
    text = "Data Analyst Intern  County Office\nGraduate Assistant (Data &\nIT Services)\nData Analyst Big Consultancy"
    assert check_text(text, choices) == [
        "title 'Data Analyst (Business Intelligence)' (Big Consultancy) is not on the resume"]
