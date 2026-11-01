"""Collector parsing and storage, on recorded samples (no network)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from scamwatch.collectors import keyword_pattern
from scamwatch.collectors.ctlog import parse_entry
from scamwatch.collectors.lists import parse_domain_list, parse_tranco, parse_url_list, parse_whoisds, whoisds_token
from scamwatch.collectors.rdap import parse_rdap
from scamwatch.http import Fetcher

FIX = Path(__file__).parent / "fixtures"


def _zip(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


def test_domain_list_skips_comments_and_blanks():
    assert parse_domain_list("# header\n\nUSPS-Fee.top\n! note\nexample.org  extra\n") == [
        "usps-fee.top",
        "example.org",
    ]


def test_url_list_keeps_only_urls():
    assert parse_url_list("https://a.top/x\nnot a url\nhttp://b.xyz\n") == ["https://a.top/x", "http://b.xyz"]


def test_tranco_zip():
    assert parse_tranco(_zip("top-1m.csv", "1,google.com\n2,ups.com\n")) == [(1, "google.com"), (2, "ups.com")]


def test_whoisds_zip_and_token():
    assert parse_whoisds(_zip("domain-names.txt", "a.com\nusps-x.top\n")) == ["a.com", "usps-x.top"]
    assert whoisds_token(date(2026, 10, 31)) == "MjAyNi0xMC0zMS56aXA="  # the token in WhoisDS's own links


def test_keyword_pattern_matches_brand_strings():
    kw = keyword_pattern()
    assert kw.search("fedex-redelivery.top") and kw.search("track-usps.xyz") and kw.search("dhl-fee.com")
    assert not kw.search("example.org")


def test_ct_entries_decode():
    entries = json.loads((FIX / "ct_entries.json").read_text())
    for i, e in enumerate(entries):
        parsed = parse_entry(i, e["leaf_input"], e["extra_data"])
        assert parsed is not None and parsed.names
        assert parsed.timestamp.year >= 2026 and parsed.timestamp.tzinfo is not None


def test_ct_rejects_garbage():
    assert parse_entry(0, "AAAA", "") is None


def test_rdap_parse():
    doc = {
        "events": [{"eventAction": "registration", "eventDate": "2026-10-29T08:15:00Z"}],
        "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Example Registrar"]]]}],
    }
    assert parse_rdap(doc) == (datetime(2026, 10, 29, 8, 15, tzinfo=UTC), "Example Registrar")
    assert parse_rdap({}) == (None, None)


def test_fetcher_retries_then_succeeds():
    import httpx

    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503 if len(calls) < 3 else 200, text="ok")

    waits = []
    f = Fetcher(min_interval=0, transport=httpx.MockTransport(handler), sleep=waits.append)
    assert f.get("https://example.test/x").text == "ok"
    assert len(calls) == 3 and waits[:2] == [2.0, 4.0]  # backs off 2s, then 4s


def test_fetcher_does_not_retry_a_404():
    import httpx
    import pytest

    calls = []
    f = Fetcher(
        min_interval=0,
        transport=httpx.MockTransport(lambda r: calls.append(1) or httpx.Response(404)),
        sleep=lambda s: None,
    )
    with pytest.raises(httpx.HTTPStatusError):
        f.get("https://example.test/missing")
    assert len(calls) == 1
