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


def test_pick_location_matches_city_and_state_by_code_or_name():
    from auto_apply.filler.domform import pick_location
    gh = ["West Memphis, Arkansas, United States", "Memphis, Florida, United States",
          "Memphis, Tennessee, United States"]
    assert pick_location(gh, "Memphis, TN") == 2
    assert pick_location(["Memphis, TN, USA", "Memphis, FL, USA"], "Memphis, TN") == 0
    assert pick_location(["Memphis, FL, USA"], "Memphis, TN") is None  # never a different place


def test_greenhouse_embed_url_and_hidden_location_fields():
    from auto_apply.filler.schema import form_url, questions_from_api
    assert form_url("https://job-boards.greenhouse.io/stripe/jobs/123") == \
        "https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=123"
    assert form_url("https://job-boards.eu.greenhouse.io/acme/jobs/9").startswith("https://job-boards.eu.greenhouse.io/embed/")
    data = {"questions": [], "location_questions": [
        {"label": "Latitude", "required": True, "fields": [{"name": "latitude", "type": "input_hidden", "values": []}]},
        {"label": "Location", "required": True, "fields": [{"name": "location", "type": "input_text", "values": []}]}]}
    assert [q.label for q in questions_from_api(data)] == ["Location"]


def test_alternatives_pick_one_checkbox_and_zip_from_profile():
    raw = [{"label": "I identify my race/ethnicity as (mark all that apply):", "required": True, "fields": [
                {"name": "r", "type": "multi_value_multi_select", "options": [
                    {"label": "Asian", "value": "#a"}, {"label": "I don't wish to answer", "value": "#d"}]}]},
           {"label": "Zip Code / Postal Code", "required": True,
            "fields": [{"name": "z", "type": "input_text", "options": []}]}]
    rules = [{"match": "race", "answer": ["decline", "I don't wish to answer"]}]
    profile = {"personalInformation": {**PROFILE["personalInformation"], "zipCode": "62701"}}
    plan = AnswerBank(profile, rules, {}).plan(questions_from_raw(raw))
    assert plan[0].value == ["I don't wish to answer"]
    assert plan[1].value == "62701"


def test_open_questions_are_written_for_drafting(tmp_path):
    import json
    from auto_apply.filler.cli import write_questions
    out = tmp_path / "questions.json"
    write_questions(list(plan().values()), out)
    rows = {r["label"]: r for r in json.loads(out.read_text())["questions"]}
    assert "Export control: list your citizenships" in rows
    assert rows["Do you have at least 2 years of experience with dbt?"]["options"] == ["Yes", "No"]
    assert "Full name" not in rows  # answered questions are not listed
