from auto_apply.guard import check_resume, normalize_text, parse_instructions
from conftest import GOOD_RESUME, INSTRUCTIONS


def test_parse_ignores_never_claim_tool_lists():
    rules = parse_instructions(INSTRUCTIONS)
    assert not {"Docker", "Tableau", "CI/CD"} & set(rules.banned_phrases)


def test_parse_bans_only_quotes_after_the_negation():
    rules = parse_instructions(INSTRUCTIONS)
    assert "student" in rules.banned_phrases
    assert "Statistics graduate (MS)" not in rules.banned_phrases
    assert {"results-driven", "synergy"} <= set(rules.banned_phrases)


def test_parse_handles_empty_instructions():
    rules = parse_instructions(None)
    assert rules.banned_phrases == []


def test_clean_resume_has_no_findings(profile):
    assert check_resume(GOOD_RESUME, profile, parse_instructions(INSTRUCTIONS)) == []


def test_tools_from_a_never_claim_list_are_allowed(profile):
    text = GOOD_RESUME + "Built dashboards in tableau and pipelines on BigQuery with ci/cd."
    assert check_resume(text, profile, parse_instructions(INSTRUCTIONS)) == []


def test_word_boundaries_avoid_false_positives(profile):
    # "students" is not "student".
    text = GOOD_RESUME + "Added a chart for students."
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


def test_drafted_answers_only_flag_banned_phrases():
    from auto_apply.guard import GuardRules, check_answers
    rules = GuardRules(banned_phrases=["results-driven"])
    found = check_answers({
        "Do you have experience with Tableau?": "Yes",
        "Describe a project": "Built CI/CD for reports",
        "Why us?": "I am a results-driven analyst",             # banned phrase
        "_note": "ignored",
    }, rules)
    assert [f.rule for f in found] == ["answer-banned-phrase"]
