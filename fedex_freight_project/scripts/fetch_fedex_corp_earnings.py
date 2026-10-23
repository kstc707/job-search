"""Download FedEx Corp (CIK 1048911) earnings-release 8-K exhibits (Item 2.02) from SEC EDGAR.

These pre-spin-off releases report the FedEx Freight segment's quarterly results and LTL
operating statistics, giving a longer history than FedEx Freight Holding Co.'s own filings.
"""
import json
import pathlib
import sys
import time
import urllib.request

UA = "Sai Teja Koppolu skppolu1@memphis.edu"
CIK = 1048911
OUT = pathlib.Path(sys.argv[1])


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    time.sleep(0.25)  # stay well under SEC's 10 requests/second limit
    return body


subs = json.loads((OUT / "submissions_CIK0001048911.json").read_text())
r = subs["filings"]["recent"]
for i, form in enumerate(r["form"]):
    if form != "8-K" or "2.02" not in r["items"][i]:
        continue
    acc = r["accessionNumber"][i].replace("-", "")
    date = r["filingDate"][i]
    base = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{acc}"
    idx = json.loads(get(f"{base}/index.json"))
    for item in idx["directory"]["item"]:
        name = item["name"]
        if not name.lower().endswith((".htm", ".html")) or "index" in name or name == r["primaryDocument"][i]:
            continue
        if name.startswith("R") and name[1:-4].isdigit():  # XBRL viewer pages
            continue
        dest = OUT / f"{date}_{name}"
        if dest.exists():
            continue
        body = get(f"{base}/{name}")
        if body.lstrip()[:200].lower().find(b"<html") < 0 and b"<document" not in body[:500].lower():
            print("WARN not html?", dest.name)
        dest.write_bytes(body)
        print(date, name, len(body))
