import pytest

# A made-up candidate. Real profile data stays in runs/ (git-ignored).
PROFILE = {
    "personalInformation": {
        "firstName": "Alex", "lastName": "Rivera", "email": "alex@example.com",
        "phone": "+15550100", "city": "Springfield", "state": "Illinois",
        "country": "United States",
    },
    "workAuthorization": {"isAuthorizedToWork": True, "needsSponsorship": False},
    "education": [{"university": "University of Springfield", "degree": "MS", "major": "Statistics"}],
    "workExperience": [
        {"role": "Data Analyst Intern", "company": "Springfield County Clerk"},
        {"role": "Teaching Assistant, Statistics", "company": "University of Springfield"},
        {"role": "Support Technician", "company": "University of Springfield Help Desk"},
        {"role": "Product Analyst", "company": "Acme"},
    ],
}

INSTRUCTIONS = (
    "Only reframe facts already in my profile. "
    "Never claim: Docker, Kubernetes, CI/CD, PySpark/Spark, GCP/BigQuery/Vertex AI, Tableau. "
    "Call me a 'Statistics graduate (MS)', never a 'student'. "
    "No filler phrases like 'results-driven', 'synergy'. "
    "Keep job titles exactly as in profile."
)

GOOD_RESUME = """
Alex Rivera · alex@example.com
Statistics graduate (MS) who builds SQL and Python reporting.
Data Analyst Intern | Springfield County Clerk
Teaching Assistant, Statistics & Support Technician | University of Springfield
Product Analyst | Acme
Coached students on regression models in Python.
"""


@pytest.fixture
def profile():
    import copy
    return copy.deepcopy(PROFILE)
