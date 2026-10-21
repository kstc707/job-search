"""The extension's answer engine (content/answers.js) must decide exactly as answers.py does.

Runs the same questions through auto_apply.filler.answers.AnswerBank and, via Node, through
answers.js, and compares status, value, source and note for every field. Run with the
auto-apply venv (run_tests.sh does): it imports auto_apply from projects/auto-apply.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "auto-apply"))

from auto_apply.filler.answers import AnswerBank  # noqa: E402
from auto_apply.filler.schema import Field, Option, Question  # noqa: E402

CANDIDATE = json.loads((HERE / "fixtures" / "candidate.json").read_text())
YN = ["Yes", "No"]

# (label, required, type, options, field name)
CASES = [
    ("First Name", True, "input_text", [], "first_name"),
    ("Last Name", True, "input_text", [], "last_name"),
    ("Email", True, "input_text", [], "email"),
    ("Phone", True, "input_text", [], "phone"),
    ("Full name", True, "input_text", [], "q1"),
    ("Legal name", True, "input_text", [], "q2"),
    ("E-mail", True, "input_text", [], "q3"),
    ("Mobile phone", False, "input_text", [], "q4"),
    ("Zip code", False, "input_text", [], "q5"),
    ("Home address", False, "textarea", [], "q6"),
    ("Preferred name", False, "input_text", [], "q7"),
    ("Resume/CV", True, "input_file", [], "resume"),
    ("Cover Letter", False, "input_file", [], "cover_letter"),
    ("Transcript", False, "input_file", [], "transcript"),
    ("Are you legally authorized to work in the United States?", True, "multi_value_single_select", YN, "q8"),
    ("Will you now or in the future require sponsorship?", True, "multi_value_single_select", YN, "q9"),
    ("Will you require visa sponsorship?", False, "radio", YN, "q10"),
    ("Gender", False, "multi_value_single_select", ["Male", "Female", "Decline To Self Identify"], "gender"),
    ("Gender", False, "native_select", ["Man", "Woman", "Non-binary"], "q11"),
    ("Do you identify as transgender?", True, "radio", ["Yes", "No", "Decline"], "q12"),
    ("Veteran Status", False, "native_select", ["I am a veteran", "I am not a veteran", "Decline to self-identify"], "q13"),
    ("Veteran Status", False, "native_select", ["I identify as one or more of the classifications of protected veteran",
                                                "I am not a protected veteran", "I don't wish to answer"], "q14"),
    ("Disability Status", False, "radio", ["Yes, I have a disability", "No, I do not have a disability", "I don't wish to answer"], "q15"),
    ("Race", False, "multi_value_multi_select", ["Asian", "White", "Decline to self-identify"], "q16"),
    ("Are you Hispanic/Latino?", False, "multi_value_single_select", ["Yes", "No", "Decline to self-identify"], "q17"),
    ("How did you hear about this job?", True, "native_select", ["Job Board", "LinkedIn", "Referral"], "q18"),
    ("How did you hear about this job?", True, "native_select", ["Indeed", "Other"], "q19"),
    ("Have you previously worked for Acme?", True, "yesno", YN, "q20"),
    ("Do you have a minimum of 7 years of experience building software?", True, "yesno", YN, "q21"),
    ("Do you have at least 2 years of experience with dbt?", True, "yesno", YN, "q22"),
    ("Do you have at least 2 years of experience with dbt?", False, "yesno", YN, "q23"),
    ("Desired salary", True, "input_text", [], "q24"),
    ("Desired salary", False, "input_text", [], "q25"),
    ("Are you willing to relocate?", True, "radio", YN, "q26"),
    ("Why do you want to work here?", True, "textarea", [], "q27"),
    ("Why do you want to work here?", False, "textarea", [], "q28"),
    ("Years of experience", False, "input_text", [], "q29"),
    ("I have read the privacy notice", True, "multi_value_multi_select", ["I agree"], "q30"),
    ("Website", False, "input_text", [], "q31"),
    ("Current location", True, "autocomplete", [], "q32"),
]

JOB_ANSWERS = {"Why do you want to work here?": "I like the team's work on public data."}


def questions():
    return [Question(label, req, [Field(name, ftype, [Option(o, o) for o in opts])])
            for label, req, ftype, opts, name in CASES]


def python_plan(job_answers):
    bank = AnswerBank(CANDIDATE["profile"], CANDIDATE["rules"], {"resume": "resume.pdf", "cover_letter": None}, job_answers)
    return [{"label": r.question.label, "type": r.field.type, "status": r.status, "value": r.value,
             "source": r.source, "note": r.note} for r in bank.plan(questions())]


def js_plan(job_answers, extras):
    payload = {
        "profile": CANDIDATE["profile"], "rules": CANDIDATE["rules"],
        "files": {"resume": "resume.pdf", "cover_letter": None}, "jobAnswers": job_answers, "extras": extras,
        "questions": [{"label": label, "required": req, "fields": [{"name": name, "type": ftype, "options": opts}]}
                      for label, req, ftype, opts, name in CASES],
    }
    out = subprocess.run(["node", str(HERE / "parity_cli.js")], input=json.dumps(payload),
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@pytest.mark.parametrize("job_answers", [{}, JOB_ANSWERS], ids=["rules", "with-job-answers"])
def test_js_engine_matches_python_exactly(job_answers):
    py, js = python_plan(job_answers), js_plan(job_answers, extras=False)
    assert len(py) == len(js)
    for p, j in zip(py, js):
        assert j == p, f"{p['label']}: python {p} != js {j}"


def test_extension_extras_only_add_answers_where_python_has_none():
    py, js = python_plan(JOB_ANSWERS), js_plan(JOB_ANSWERS, extras=True)
    for p, j in zip(py, js):
        if j != p:
            assert p["note"] == "no approved answer", f"{p['label']}: extras changed a decided answer: {p} -> {j}"
