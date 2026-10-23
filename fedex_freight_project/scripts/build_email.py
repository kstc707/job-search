"""Draft the short follow-up email (reports/email_draft.md) and gather the attachments under clean names in
reports/email_attachments/ (gitignored; the resume is added by hand as SaiTejaKoppolu_Resume.pdf)."""
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
H = json.loads((REP / "site/headline.json").read_text())
fc = "−" + H["fdx_nc"][1:] if H["fdx_nc"].startswith("-") else H["fdx_nc"]
ATT = REP / "email_attachments"
ATT.mkdir(exist_ok=True)
files = {"SaiTejaKoppolu_FedExFreight_ProjectSummary.pdf": "summary/Koppolu_FedEx_Freight_project_summary.pdf",
         "SaiTejaKoppolu_FedExFreight_Overview.pdf": "overview/Koppolu_FedEx_Freight_overview.pdf",
         "SaiTejaKoppolu_FedExFreight_Video.mp4": "video/Koppolu_FedEx_Freight_overview.mp4"}
for name, src in files.items():
    shutil.copyfile(REP / src, ATT / name)

body = f"""Subject: Intern-Data Scientist applicant: a FedEx Freight project built from real public data

Hi [Name],

I recently applied for the Intern-Data Scientist role at FedEx Freight. To show how interested I am, I built a project
from real public FedEx Freight data (SEC filings and its published fuel surcharge table) on one question: how much of
its lost LTL volume is price, and how much is something else?

In short: price explains the 2022-23 share loss, but not the losses since, which points to customer retention rather
than price. I also locked a forecast of June-September shipments ({fc}%) before the October 29 report.

I've attached my resume, a one-page project summary, a one-page overview and a 2-minute video. I'd welcome an
interview call, or an introduction to the hiring manager or the data science team, to walk you through it.

Thank you,
Sai Teja Koppolu
+1 901-343-7273 | github.com/kstc707
"""
(REP / "email_draft.md").write_text(body)
print(body)
