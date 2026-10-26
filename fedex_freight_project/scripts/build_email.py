"""Draft the short follow-up message (reports/email_draft.md) and copy its one attachment, the project summary,
under a clean name into reports/email_attachments/ (gitignored)."""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
ATT = REP / "email_attachments"
ATT.mkdir(exist_ok=True)
files = {"SaiTejaKoppolu_FedExFreight_ProjectSummary.pdf": "summary/Koppolu_FedEx_Freight_project_summary.pdf"}
for old in ATT.glob("SaiTejaKoppolu_FedExFreight_*"):
    if old.name not in files:
        old.unlink()
for name, src in files.items():
    shutil.copyfile(REP / src, ATT / name)

body = """Subject: Intern-Data Scientist applicant: a FedEx Freight project

Hi [Name],

I applied for the Intern-Data Scientist role (Pricing Science & Analysis). To show my interest, I built a short project
on FedEx Freight's pricing and market share from real public data, including a forecast locked before the October 29
report. The one-page summary is attached.

Could you forward it to the team lead or hiring manager? I'd love a quick call to walk them through it.

Thank you,
Sai Teja Koppolu
skoppolu388@gmail.com | +1 901-654-6846
"""
(REP / "email_draft.md").write_text(body)
print(body)
