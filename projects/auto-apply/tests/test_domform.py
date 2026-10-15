"""Lever/Ashby forms read from the page: planning logic, no browser or network."""

from auto_apply.filler.answers import ASK, AnswerBank, match_option
from auto_apply.filler.domform import apply_url, detect_ats, questions_from_raw
from auto_apply.filler.schema import Option
from conftest import PROFILE

YN = [{"label": "Yes", "value": "Yes"}, {"label": "No", "value": "No"}]

# Shape returned by the page reader (made-up form mixing Lever and Ashby patterns).
RAW = [
    {"label": "Full name", "required": True, "fields": [{"name": '[name="name"]', "type": "input_text", "options": []}]},
    {"label": "Email", "required": True, "fields": [{"name": '[name="email"]', "type": "input_text", "options": []}]},
    {"label": "Phone", "required": True, "fields": [{"name": '[id="p1"]', "type": "input_text", "options": []}]},
    {"label": "Phone — communicationConsent", "required": True, "fields": [
        {"name": '[name="communicationConsent"]', "type": "radio", "options": [
            {"label": "Yes - I consent to receiving text messages", "value": "#c1"},
            {"label": "No - I do not consent to receiving text messages", "value": "#c2"}]}]},
    {"label": "Preferred name", "required": False, "fields": [{"name": '[id="pn"]', "type": "input_text", "options": []}]},
    {"label": "Resume/CV", "required": True, "fields": [{"name": '[id="resume-upload-input"]', "type": "input_file", "options": []}]},
    {"label": "Veteran status", "required": False, "fields": [{"name": '[name="eeo[veteran]"]', "type": "native_select", "options": [
        {"label": "I am a veteran", "value": "I am a veteran"},
        {"label": "I am not a veteran", "value": "I am not a veteran"},
        {"label": "Decline to self-identify", "value": "Decline to self-identify"}]}]},
    {"label": "Do you have a minimum of 7 years of experience building software?", "required": True,
     "fields": [{"name": '[data-field-path="a"]', "type": "yesno", "options": YN}]},
    {"label": "Do you have at least 2 years of experience with dbt?", "required": True,
     "fields": [{"name": '[data-field-path="b"]', "type": "yesno", "options": YN}]},
    {"label": "Export control: list your citizenships", "required": True,
     "fields": [{"name": '[name="cards[x][field0]"]', "type": "textarea", "options": []}]},
]

RULES = [
    {"match": "communicationConsent", "answer": ["No - I do not consent", "No"]},
    {"match": r"veteran\s*status", "answer": ["No", "I am not a protected veteran", "I am not a veteran"]},
    {"match": "years of experience", "answer": "3"},
]


def plan():
    bank = AnswerBank(PROFILE, RULES, {"resume": "r.pdf", "cover_letter": None})
    return {r.question.label: r for r in bank.plan(questions_from_raw(RAW))}


def test_detect_and_apply_url():
    assert detect_ats("https://jobs.lever.co/acme/abc") == "lever"
    assert detect_ats("https://jobs.ashbyhq.com/acme/abc?src=x") == "ashby"
    assert detect_ats("https://job-boards.greenhouse.io/acme/jobs/1") == "greenhouse"
    assert detect_ats("https://acme.wd5.myworkdayjobs.com/x") is None
    assert apply_url("https://jobs.lever.co/acme/abc/", "lever") == "https://jobs.lever.co/acme/abc/apply"
    assert apply_url("https://jobs.ashbyhq.com/acme/abc?src=x", "ashby") == "https://jobs.ashbyhq.com/acme/abc/application"


def test_contact_fields_come_from_profile_by_label():
    p = plan()
    assert p["Full name"].value == "Alex Rivera" and p["Full name"].source == "profile"
    assert p["Email"].value == "alex@example.com"
    assert p["Phone"].value == "+15550100"
    assert p["Preferred name"].status == "skip"  # not "Name": never filled from the profile


def test_choice_groups_pick_one_option():
    p = plan()
    assert p["Phone — communicationConsent"].value == "No - I do not consent to receiving text messages"
    assert p["Veteran status"].value == "I am not a veteran"
    assert p["Resume/CV"].value == "r.pdf"


def test_no_does_not_match_inside_not():
    opts = [Option("I am a veteran", 1), Option("I am not a veteran", 2)]
    assert match_option("No", opts) is None
    assert match_option("not a veteran", opts) == "I am not a veteran"


def test_years_questions_derive_no_or_ask():
    p = plan()
    seven = p["Do you have a minimum of 7 years of experience building software?"]
    assert (seven.status, seven.value) == ("fill", "No")  # asks more than you have: always true
    two = p["Do you have at least 2 years of experience with dbt?"]
    assert two.status == "ask" and two.blocking  # skill-specific: never assumed


def test_unknown_required_question_blocks():
    r = plan()["Export control: list your citizenships"]
    assert r.status == "missing" and r.blocking
