"""Text mining: link extraction, brand and lure tagging, campaign grouping, SmishTank parsing."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from scamwatch.analysis.texts import (
    brand_in_text,
    campaigns,
    defang_links,
    extract_urls,
    lure_of,
    message_frame,
    normalize,
    script_reuse,
    sender_type,
)
from scamwatch.collectors.smishtank import parse_dataset, parse_feed


def test_extracts_links_written_to_dodge_filters():
    assert extract_urls("Confirm your address at the link. 7knfu.za.com (Copy the link)") == ["https://7knfu.za.com"]
    assert extract_urls("Click here shm.to/ IRSDocs1040-doc to review") == ["https://shm.to/IRSDocs1040-doc"]
    assert extract_urls("visit hxxps://usps-help[.]top/pay now") == ["https://usps-help.top/pay"]
    assert extract_urls("HTTPS://USPS.COM-TRACK.XYZ/a.") == ["https://usps.com-track.xyz/a"]


def test_ignores_things_that_are_not_links():
    assert extract_urls("the U.S. Postal Service at 9 a.m. today") == []
    assert extract_urls("email help@usps.com for support") == []
    assert extract_urls("information.Confirm your details") == []  # 'confirm' is not a real ending
    assert extract_urls("version 1.2.3") == []


def test_brand_named_as_a_word():
    assert brand_in_text("USPS: your package is on hold") == "USPS"
    assert brand_in_text("Your FedEx parcel") == "FedEx"
    assert brand_in_text("UPS delivery attempt failed") == "UPS"
    assert brand_in_text("Join our groups for sign-ups") is None
    assert brand_in_text("The U.S. Postal Service could not deliver") == "USPS"


def test_lures():
    assert lure_of("cannot be delivered due to incomplete address information") == "update address"
    assert lure_of("A $1.99 redelivery fee is required") == "pay a fee"
    assert lure_of("Your package is on hold at our facility") == "failed or held delivery"
    assert lure_of("Hello there") == "other"


def test_sender_types():
    assert sender_type("+1 (872) 279-0672") == "Phone Number"
    assert sender_type("42003") == "Short Code"
    assert sender_type("abc@xyz.com") == "Email Address"
    assert sender_type("x", "Email To Text") == "Email To Text"


def test_same_script_with_different_links_is_one_campaign():
    texts = [
        "USPS - The package cannot be delivered due to incomplete address. Confirm at 7knfu.za.com",
        "USPS - The package cannot be delivered due to incomplete address. Confirm at 06ya2.za.com",
        "USPS - The package cannot be delivered due to incomplete address. Confirm at https://ertup.top/x",
        "IRS Notice: you have 2 tax documents waiting, review at shm.to/abc",
    ]
    ids = campaigns(texts)
    assert ids[0] == ids[1] == ids[2] and ids[3] != ids[0]
    assert "<num>" not in normalize("pay $1.99") and "<money>" in normalize("pay $1.99")


def test_script_reuse_only_looks_back_in_time():
    t = "USPS - package cannot be delivered due to incomplete address. Confirm at {}"
    rows = [
        {"text": t.format("aaa.top"), "sender": "", "posted_at": datetime(2023, 1, 1, tzinfo=UTC), "origin": "x"},
        {"text": t.format("bbb.top"), "sender": "", "posted_at": datetime(2023, 1, 2, tzinfo=UTC), "origin": "x"},
        {
            "text": "Netflix: payment failed, update at ccc.top",
            "sender": "",
            "posted_at": datetime(2023, 1, 3, tzinfo=UTC),
            "origin": "x",
        },
    ]
    d = script_reuse(message_frame(rows))
    assert list(d.known_script) == [False, True, False]  # first copy cannot be 'known'
    assert list(d.new_domain) == [True, True, True]


def test_display_is_defanged_and_names_hidden():
    out = defang_links("Hello Olivia, pay at https://usps-fee.top/p now")
    assert "usps-fee[.]top" in out and "hxxps://" in out and "Olivia" not in out


def test_parse_dataset_csv_latin1():
    csv_text = (
        "messageid,Fulltext,Sender,SenderType,timeReceived,MainText,Url,Brand,FullyQualifiedDomain\n"
        '5,x,+1 (872) 279-0672,Phone Number,"04/02/2022, 02:59:56",'
        '"Hi, you still owe UPS $4.10 \xb0 fees: ups-fee.top/x",,UPS,ups-fee.top\n'
    )
    rows = parse_dataset(csv_text.encode("latin-1"))
    assert rows[0]["external_id"] == "d1:5" and rows[0]["brand_claimed"] == "UPS"
    assert rows[0]["posted_at"] == datetime(2022, 4, 2, 2, 59, 56, tzinfo=UTC)
    assert rows[0]["urls"] == ["https://ups-fee.top/x", "https://ups-fee.top"]


def test_parse_feed():
    payload = json.loads(
        '{"smishes": [{"messageID": "4881", "timeReceived": 1793132052426, "sender": "+1 (202) 988-9294",'
        ' "messageContent": "USPS: update address at usps.com-help.top", "url": ""},'
        ' {"messageID": null, "messageContent": "no id"}]}'
    )
    rows = parse_feed(payload)
    assert len(rows) == 1 and rows[0]["external_id"] == "feed:4881"
    assert rows[0]["urls"] == ["https://usps.com-help.top"] and rows[0]["posted_at"].year == 2026


def test_message_frame_flags():
    df = message_frame(
        [
            {
                "text": "USPS: confirm address, reply Y then reopen: usps-a.top",
                "sender": "+44 7956 454509",
                "origin": "x",
            },
            {"text": "Your parcel is held, pay fee bit.ly/x", "sender": "abc@x.com", "origin": "x"},
        ]
    )
    assert list(df.delivery) == [True, True]
    assert df.reply_trick.iloc[0] and df.link_has_brand.iloc[0] and not df.link_has_brand.iloc[1]
    assert df.shortener.iloc[1] and df.country.iloc[0] == "+44"
    assert isinstance(df, pd.DataFrame)
