import pytest

from auto_apply.filler.answers import ASK, AnswerBank, match_option
from auto_apply.filler.schema import Option, parse_job_url, questions_from_api
from conftest import PROFILE

# Shape of a Greenhouse job API response (made-up job).
API = {
    "title": "Data Analyst",
    "questions": [
        {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
        {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
        {"label": "Resume/CV", "required": True, "fields": [
            {"name": "resume", "type": "input_file"}, {"name": "resume_text", "type": "textarea"}]},
        {"label": "Cover Letter", "required": False, "fields": [{"name": "cover_letter", "type": "input_file"}]},
        {"label": "Are you legally authorized to work in the United States?", "required": True, "fields": [
            {"name": "question_1", "type": "multi_value_single_select",
             "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
        {"label": "Will you now or in the future require sponsorship?", "required": True, "fields": [
            {"name": "question_2", "type": "multi_value_single_select",
             "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
        {"label": "Why do you want to join?", "required": False, "fields": [
            {"name": "question_3", "type": "textarea"}]},
        {"label": "Certifications", "required": False, "fields": [
            {"name": "question_4", "type": "multi_value_multi_select",
             "values": [{"label": "CFA", "value": 7}, {"label": "CPA", "value": 8}]}]},
    ],
    "location_questions": [],
    "compliance": [{"type": "eeoc", "questions": [
        {"label": "Gender", "required": False, "fields": [
            {"name": "gender", "type": "multi_value_single_select",
             "values": [{"label": "Male", "value": 1}, {"label": "Decline To Self Identify", "value": 3}]}]}]}],
    "demographic_questions": None,
}

RULES = [
    {"match": "sponsorship", "answer": ASK, "note": "decide once"},
    {"match": "authori[sz]ed to work", "answer": "Yes"},
    {"match": "gender", "answer": "decline"},
    {"match": "certification", "answer": ["CFA"]},
]


@pytest.fixture
def bank():
    return AnswerBank(PROFILE, RULES, {"resume": "/tmp/r.pdf", "cover_letter": None})


def by_label(plan, label):
    return next(r for r in plan if r.question.label.startswith(label))


@pytest.mark.parametrize("url,expected", [
    ("https://job-boards.greenhouse.io/acme/jobs/123", ("acme", "123")),
    ("https://boards.eu.greenhouse.io/acme/jobs/456?gh_src=x", ("acme", "456")),
    ("https://boards.greenhouse.io/embed/job_app?for=acme&token=789", ("acme", "789")),
])
def test_parse_job_url(url, expected):
    assert parse_job_url(url) == expected


def test_career_page_urls_are_rejected_not_guessed():
    with pytest.raises(ValueError, match="not a hosted Greenhouse URL"):
        parse_job_url("https://acme.com/careers?gh_jid=123")


def test_questions_include_compliance_sections():
    qs = questions_from_api(API)
    assert [q.section for q in qs][-1] == "compliance:eeoc"
    assert len(qs) == 9  # no race field in API, so no added Hispanic question


def test_match_option_exact_prefix_substring_and_ambiguity():
    opts = [Option("Yes", 1), Option("No", 0), Option("Decline To Self Identify", 3)]
    assert match_option("yes", opts) == "Yes"
    assert match_option("decline", opts) == "Decline To Self Identify"
    assert match_option("maybe", opts) is None
    assert match_option("New", [Option("New York", 1), Option("New Jersey", 2)]) is None


def test_plan_fills_profile_files_and_rules(bank):
    plan = bank.plan(questions_from_api(API))
    assert by_label(plan, "First Name").value == "Alex"
    assert by_label(plan, "Email").source == "profile"
    resume = [r for r in plan if r.question.label == "Resume/CV"]
    assert len(resume) == 1 and resume[0].field.type == "input_file"  # paste box dropped
    assert by_label(plan, "Are you legally").value == "Yes"
    assert by_label(plan, "Gender").value == "Decline To Self Identify"
    assert by_label(plan, "Certifications").value == ["CFA"]


def test_ask_rule_blocks_required_question(bank):
    plan = bank.plan(questions_from_api(API))
    sponsor = by_label(plan, "Will you now")
    assert sponsor.status == "ask" and sponsor.blocking
    assert [r.question.label for r in plan if r.blocking] == [sponsor.question.label]


def test_optional_unknowns_are_skipped_not_blocking(bank):
    plan = bank.plan(questions_from_api(API))
    assert by_label(plan, "Why do you want").status == "skip"
    assert by_label(plan, "Cover Letter").status == "skip"
    assert not any(r.blocking for r in plan if not r.question.required)


def test_job_answers_override_rules(bank):
    bank.job_answers = {"will you now or in the future require sponsorship": "No"}
    plan = bank.plan(questions_from_api(API))
    assert by_label(plan, "Will you now").value == "No"
    assert not any(r.blocking for r in plan)


def test_answer_matching_no_option_blocks(bank):
    bank.rules.insert(0, (__import__("re").compile("authori"), "Absolutely", ""))
    r = by_label(bank.plan(questions_from_api(API)), "Are you legally")
    assert r.status == "no-option" and r.blocking


def test_single_select_rule_can_list_alternatives(bank):
    import re
    bank.rules.insert(0, (re.compile("legally"), ["Absolutely", "Yes"], ""))
    assert by_label(bank.plan(questions_from_api(API)), "Are you legally").value == "Yes"


def test_eeoc_race_adds_hispanic_question_first():
    import copy
    api = copy.deepcopy(API)
    api["compliance"][0]["questions"].append({"label": "Race", "required": False, "fields": [
        {"name": "race", "type": "multi_value_single_select", "values": [{"label": "Decline To Self Identify", "value": 8}]}]})
    labels = [q.label for q in questions_from_api(api)]
    assert labels.index("Are you Hispanic/Latino?") < labels.index("Race")


def test_checkbox_ids_and_demographic_ids():
    from auto_apply.filler.greenhouse import _css_id, _group
    assert _group("question_1[]") == "question_1" and _group("question_1") == "question_1"
    assert _css_id("demographic_605") == '[id="605"]'
