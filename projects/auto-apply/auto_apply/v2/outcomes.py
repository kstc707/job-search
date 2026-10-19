"""Turn application emails into tracker status changes, with the email as evidence.

Input (JSON the agent fetched):
- tracker rows: [{"url", "Job", "Company", "Status", "Notes", "Apply URL"}...]
- inbox messages (Tsenta list-inbox-messages rows): [{"id", "from", "fromName", "subject",
  "snippet", "receivedAt", "category", "application": {"companyName",
  "trackedApplication": {"positionTitle"}}}...]

Output: a plan — updates for existing rows, new rows for applications the tracker never
had (manual or Tsenta-only), and emails that could not be matched. Nothing is written
here; the agent applies the plan and stamps each used email id into the row's Notes
("[outcome:<id>]") so a message is never applied twice.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

# What each email category means for the application.
CATEGORY_STATUS = {
    "ACKNOWLEDGMENT": "Applied",
    "ASSESSMENT": "Waiting",            # a form, test or AI screen: a step, not an interview
    "RECRUITER_MESSAGE": "Waiting",     # a person wrote: Sai must read it
    "INTERVIEW": "Interview Scheduled",
    "OFFER": "Offer",
    "REJECTION": "Rejected",
}
# How far along each status is. A later email only moves a row forward, except that a
# rejection or offer ends the application whatever came before.
RANK = {None: 0, "": 0, "Drafted": 0, "Skipped": 0, "Approved": 1, "Applied": 2,
        "Waiting": 3, "Interview Scheduled": 4, "Rejected": 5, "Offer": 6}
FINAL = {"Rejected", "Offer"}
NEEDS_SAI = {"RECRUITER_MESSAGE", "INTERVIEW", "OFFER", "ASSESSMENT"}

_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|group|the|plc|lp|holdings|usa|us)\b")


def norm_company(s: str | None) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    return " ".join(_SUFFIX.sub(" ", s).split())


def norm_title(s: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split())


def company_match(a: str, b: str) -> bool:
    a, b = norm_company(a), norm_company(b)
    if not a or not b:
        return False
    return a == b or a.startswith(b + " ") or b.startswith(a + " ") or \
        SequenceMatcher(None, a, b).ratio() >= 0.88


def title_score(a: str, b: str) -> float:
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class Evidence:
    message_id: str
    category: str
    received: str
    sender: str
    subject: str


@dataclass
class Update:
    row_url: str
    job: str
    company: str
    old_status: str | None
    new_status: str
    confidence: str            # high: company + title; medium: company with a single open row
    needs_sai: bool            # a person or a next step is waiting on Sai
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class NewRow:
    job: str
    company: str
    status: str
    needs_sai: bool
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Plan:
    updates: list[Update] = field(default_factory=list)
    new_rows: list[NewRow] = field(default_factory=list)
    unmatched: list[Evidence] = field(default_factory=list)
    skipped_seen: int = 0


def _company_title(msg: dict) -> tuple[str, str]:
    app = msg.get("application") or {}
    tracked = app.get("trackedApplication") or {}
    company = app.get("companyName") or msg.get("fromName") or ""
    return company, tracked.get("positionTitle") or ""


_ATS_DOMAINS = ("myworkday.com", "icims.com", "smartrecruiters.com", "recruitee-inbox", "greenhouse-mail.io",
                "lever.co", "ashbyhq.com", "breezy-mail.com", "ultipro.com", "brassring.com", "jobvite.com")
_SUBJECT_CO = re.compile(r"\b(?:to|at|with|from)\s+([A-Z][\w&.'’\- ]{1,40}?)(?:[!.,:|]|\s+-\s|$)")


def _fallback_companies(msg: dict) -> list[str]:
    """Company names guessed from an email with no linked application: the sender's ATS
    mailbox ("pwc@myworkday.com" -> "pwc") and "...applying to Acme" in the subject.
    Used only to find an EXISTING tracker row, never to create one."""
    out = []
    sender = (msg.get("from") or "").lower()
    local, _, domain = sender.partition("@")
    if any(d in domain for d in _ATS_DOMAINS):
        local = re.split(r"[+._-]", local)[0]
        if local and local not in ("no", "noreply", "notification", "notifications", "do", "careers", "jobs", "talent"):
            out.append(local)
    m = _SUBJECT_CO.search(msg.get("subject") or "")
    if m:
        out.append(m.group(1).strip())
    if msg.get("fromName"):
        out.append(msg["fromName"])
    return out


def _seen_ids(rows: list[dict]) -> set[str]:
    ids = set()
    for r in rows:
        # Notion returns Notes as escaped markdown, so the stamp can read \[outcome:id\]
        ids.update(re.findall(r"\\?\[outcome:([A-Za-z0-9_-]+)\\?\]", r.get("Notes") or ""))
    return ids


def _match(rows: list[dict], company: str, title: str, received: str = "") -> tuple[dict | None, str]:
    # An email cannot be about a row the tracker created after the email arrived.
    day = (received or "")[:10]
    same = [r for r in rows if company_match(r.get("Company") or "", company)
            and not (day and (r.get("date:Date:start") or "") > day)]
    if not same:
        return None, ""
    if title:
        best = max(same, key=lambda r: title_score(r.get("Job") or "", title))
        if title_score(best.get("Job") or "", title) >= 0.75:
            return best, "high"
        return None, ""  # the email names a different job at this company: another application
    if len(same) == 1:
        return same[0], "medium"
    return None, "ambiguous"  # several rows at this company and no title to choose: ask, don't guess


def build_plan(rows: list[dict], messages: list[dict]) -> Plan:
    plan = Plan()
    seen = _seen_ids(rows)
    by_row: dict[str, Update] = {}
    by_new: dict[tuple[str, str], NewRow] = {}
    for msg in sorted(messages, key=lambda m: m.get("receivedAt") or ""):
        cat = msg.get("category")
        if cat not in CATEGORY_STATUS:
            continue
        if msg.get("id") in seen:
            plan.skipped_seen += 1
            continue
        ev = Evidence(msg.get("id", ""), cat, msg.get("receivedAt", ""), msg.get("from", ""),
                      (msg.get("subject") or "")[:140])
        company, title = _company_title(msg)
        linked = bool((msg.get("application") or {}).get("companyName"))
        row, conf = (None, "")
        if linked:
            row, conf = _match(rows, company, title, msg.get("receivedAt") or "")
        else:
            for guess in _fallback_companies(msg):
                row, conf = _match(rows, guess, title, msg.get("receivedAt") or "")
                if row is not None or conf == "ambiguous":
                    break
            if row is None:
                plan.unmatched.append(ev)  # never create rows from a guessed company
                continue
            conf = "medium"
        if not company and row is None:
            plan.unmatched.append(ev)
            continue
        status = CATEGORY_STATUS[cat]
        if conf == "ambiguous":
            plan.unmatched.append(ev)  # Sai picks which of the company's rows it belongs to
            continue
        if row is None:
            if not title and not (msg.get("application") or {}).get("companyName"):
                plan.unmatched.append(ev)  # only a sender name: too weak to create a row
                continue
            key = (norm_company(company), norm_title(title))
            nr = by_new.setdefault(key, NewRow(title or "(title not in email)", company, status, False))
            if RANK[status] >= RANK[nr.status] or status in FINAL:
                nr.status = status
            nr.needs_sai |= cat in NEEDS_SAI
            nr.evidence.append(ev)
            continue
        up = by_row.get(row["url"])
        current = up.new_status if up else row.get("Status")
        if current in FINAL and status not in FINAL:
            continue  # an old acknowledgment arriving after the rejection changes nothing
        if not (RANK.get(status, 0) > RANK.get(current, 0) or (status in FINAL and status != current)):
            if up:
                up.evidence.append(ev)
            continue
        if up is None:
            up = by_row[row["url"]] = Update(row["url"], row.get("Job") or "", row.get("Company") or "",
                                             row.get("Status"), status, conf, False)
        up.new_status = status
        up.needs_sai |= cat in NEEDS_SAI
        up.evidence.append(ev)
    plan.updates = [u for u in by_row.values() if u.new_status != u.old_status]
    plan.new_rows = list(by_new.values())
    return plan


def summary(plan: Plan) -> str:
    out = [f"{len(plan.updates)} row update(s), {len(plan.new_rows)} application(s) missing from the tracker, "
           f"{len(plan.unmatched)} unmatched email(s), {plan.skipped_seen} already applied"]
    for u in sorted(plan.updates, key=lambda u: (not u.needs_sai, u.company)):
        flag = "  ← Sai" if u.needs_sai else ""
        out.append(f"  {u.company[:28]:28} {u.job[:38]:38} {u.old_status or '-':>10} → {u.new_status:<19} [{u.confidence}]{flag}")
    if plan.new_rows:
        out.append("missing from tracker:")
        for n in sorted(plan.new_rows, key=lambda n: (not n.needs_sai, n.company)):
            flag = "  ← Sai" if n.needs_sai else ""
            out.append(f"  {n.company[:28]:28} {n.job[:38]:38} {n.status}{flag}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.outcomes")
    p.add_argument("--tracker", required=True, help="JSON list of tracker rows")
    p.add_argument("--inbox", required=True, help="JSON list of inbox messages")
    p.add_argument("--out", help="write the plan as JSON")
    a = p.parse_args(argv)
    rows = json.load(open(a.tracker))
    msgs = json.load(open(a.inbox))
    plan = build_plan(rows, msgs)
    print(summary(plan))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(asdict(plan), f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
