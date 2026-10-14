from auto_apply.guard import check_resume, normalize_text, parse_instructions
from conftest import GOOD_RESUME, INSTRUCTIONS


def test_parse_never_claim_splits_slash_groups_but_keeps_short_pairs():
    rules = parse_instructions(INSTRUCTIONS)
    assert rules.never_claim == [
        "Docker", "Kubernetes", "CI/CD", "PySpark", "Spark", "GCP", "BigQuery", "Vertex AI", "Tableau",
    ]


def test_parse_bans_only_quotes_after_the_negation():
    rules = parse_instructions(INSTRUCTIONS)
    assert "student" in rules.banned_phrases
    assert "Statistics graduate (MS)" not in rules.banned_phrases
    assert {"results-driven", "synergy"} <= set(rules.banned_phrases)


def test_parse_handles_empty_instructions():
    rules = parse_instructions(None)
    assert rules.never_claim == [] and rules.banned_phrases == []


def test_clean_resume_has_no_findings(profile):
    assert check_resume(GOOD_RESUME, profile, parse_instructions(INSTRUCTIONS)) == []


def test_flags_never_claim_tools_case_insensitively(profile):
    text = GOOD_RESUME + "Built dashboards in tableau and pipelines on BigQuery with ci/cd."
    rules = parse_instructions(INSTRUCTIONS)
    terms = {f.detail for f in check_resume(text, profile, rules) if f.rule == "never-claim"}
    assert terms == {
        "resume mentions 'Tableau'", "resume mentions 'BigQuery'", "resume mentions 'CI/CD'",
    }


def test_word_boundaries_avoid_false_positives(profile):
    # "students" is not "student"; "Sparkline" is not "Spark".
    text = GOOD_RESUME + "Added a Sparkline chart for students."
    assert check_resume(text, profile, parse_instructions(INSTRUCTIONS)) == []


def test_banned_phrase_is_an_error(profile):
    text = GOOD_RESUME + "Results-driven graduate student."
    rules = parse_instructions(INSTRUCTIONS)
    rules_hit = {f.rule for f in check_resume(text, profile, rules) if f.severity == "error"}
    assert rules_hit == {"banned-phrase"}


def test_changed_title_is_an_error(profile):
    text = GOOD_RESUME.replace("Product Analyst", "Senior Product Analyst").replace(
        "Data Analyst Intern", "Data Analyst"
    )
    errors = [f for f in check_resume(text, profile, parse_instructions(None)) if f.severity == "error"]
    assert [f.rule for f in errors] == ["fixed-title"]
    assert "Data Analyst Intern" in errors[0].detail


def test_merged_employer_entry_matches_three_word_prefix(profile):
    # "University of Springfield Help Desk" appears only as "University of Springfield".
    findings = check_resume(GOOD_RESUME, profile, parse_instructions(None))
    assert not [f for f in findings if f.rule == "fixed-employer"]


def test_missing_employer_and_email_mismatch_are_warnings(profile):
    text = GOOD_RESUME.replace("Acme", "Initech").replace("alex@example.com", "a.r@example.org")
    findings = check_resume(text, profile, parse_instructions(None))
    assert {(f.severity, f.rule) for f in findings} == {
        ("warning", "fixed-employer"), ("warning", "contact-mismatch"),
    }


def test_normalize_rejoins_hyphenated_line_breaks():
    assert normalize_text("Data Ana-\nlyst   Intern") == "Data Analyst Intern"
