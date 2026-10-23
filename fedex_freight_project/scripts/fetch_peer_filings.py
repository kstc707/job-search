"""Download public LTL peers' 8-K documents (earnings releases and operating updates) from SEC EDGAR.

Peers: Old Dominion (ODFL), Saia (SAIA), XPO (XPO), ArcBest (ARCB). For every 8-K filed since 2017 with
Item 2.02 (results), 7.01 (Reg FD, e.g. mid-quarter operating updates) or 8.01 (other events), every
HTML document in the filing is saved as data/raw/sec_edgar/peers/<TICKER>/<filing date>_<name>.

Usage: python scripts/fetch_peer_filings.py data/raw/sec_edgar/peers [TICKER ...]
"""
import json
import pathlib
import sys
import time
import urllib.request

UA = "Sai Teja Koppolu skppolu1@memphis.edu"
PEERS = {"ODFL": 878927, "SAIA": 1177702, "XPO": 1166003, "ARCB": 894405}
ITEMS = ("2.02", "7.01", "8.01")
SINCE = "2017-01-01"
OUT = pathlib.Path(sys.argv[1])
TICKERS = sys.argv[2:] or list(PEERS)


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            time.sleep(0.4)  # SEC fair-access limit is 10 req/s; 4 parallel tickers stay under it
            return body
        except Exception as e:  # noqa: BLE001 - retry transient network errors
            print("retry", url, e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed: {url}")


for ticker in TICKERS:
    cik = PEERS[ticker]
    d = OUT / ticker
    d.mkdir(parents=True, exist_ok=True)
    sub_path = d / f"submissions_CIK{cik:010d}.json"
    if not sub_path.exists():
        sub_path.write_bytes(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    r = json.loads(sub_path.read_text())["filings"]["recent"]
    n = 0
    for i, form in enumerate(r["form"]):
        if form != "8-K" or r["filingDate"][i] < SINCE or not any(x in r["items"][i] for x in ITEMS):
            continue
        acc = r["accessionNumber"][i].replace("-", "")
        date = r["filingDate"][i]
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
        marker = d / f".done_{acc}"
        if marker.exists():
            continue
        idx = json.loads(get(f"{base}/index.json"))
        for item in idx["directory"]["item"]:
            name = item["name"]
            if not name.lower().endswith((".htm", ".html")) or "index" in name.lower():
                continue
            if name.startswith("R") and name[1:-4].isdigit():  # XBRL viewer pages
                continue
            body = get(f"{base}/{name}")
            if b"<html" not in body[:3000].lower() and b"<document" not in body[:3000].lower() \
                    and b"<?xml" not in body[:200].lower():
                print("WARN not html?", ticker, date, name)
            (d / f"{date}_{name}").write_bytes(body)
            n += 1
        marker.write_text(r["items"][i] + "\n")
    print(ticker, "new documents:", n)
