"""Detector features, the brand-as-a-word rule, generator B and RDAP routing."""

from __future__ import annotations

import random

import pytest

from scamwatch.analysis.features import FEATURES, brand_token, features
from scamwatch.analysis.model import MODEL_FEATURES
from scamwatch.collectors.rdap import parse_bootstrap, rdap_url
from scamwatch.synthetic import generator_b

# real names seen in the collected data (Nov 2026), with what the rule should say
BRAND_CASES = {
    "usps.com-trackdqf.top": "USPS",
    "8r5p3cvcxno.wusps.xyz": "USPS",
    "uspss.pages.dev": "USPS",
    "black-queen-d446.mylogindhlupdate.workers.dev": "DHL",
    "dhl-logisticservices.live": "DHL",
    "dhlentrega.eu.cc": "DHL",
    "fedex-vipvujg.shop": "FedEx",
    "19563-ups-fth-overview.pages.dev": "UPS",
    "upstrack-help.top": "UPS",
    "groups.radio.fm": None,
    "connectedcaregroups.com": None,
    "skinnymixessyrups.shop": None,
    "tarncuspsettlements.digital": None,
    "wtrdhldkzjbzooorcockuircvajr.fis.iad.test.prod.sadbirds.aws.dev": None,
    "uuidhlevv2.urawatchdog.sfdc.net": None,
    "doucs-epris-doups.top": None,
}


@pytest.mark.parametrize("fqdn,brand", BRAND_CASES.items())
def test_brand_as_a_word(fqdn, brand):
    assert brand_token(fqdn) == brand


def test_brand_token_is_never_a_stage2_input():
    assert "brand_token" in FEATURES and "brand_token" not in MODEL_FEATURES


def test_feature_signals():
    f = features("usps.com-trackdqf.top")
    assert f["com_dash_trick"] == 1 and f["brand_only_in_subdomain"] == 1 and f["common_tld"] == 0
    assert features("abc.pages.dev")["hosting_platform"] == 1
    assert features("fedx-help.com")["near_brand_spelling"] == 1


def test_generator_b_keeps_structure_not_names():
    rng = random.Random(1)
    out = generator_b.mutate(rng, "usps.com-trackdqf.top", "top")
    assert out.startswith("usps.com-track") and out.endswith(".top") and out != "usps.com-trackdqf.top"
    rows = generator_b.generate([("fedex-vipvujg.shop", "shop", "scam")], n=5, seed=3)
    # brand and ending kept, the rest re-filled with the same shape ("vip" is not a kept word)
    assert all(
        d.startswith("fedex-")
        and d.endswith(".shop")
        and len(d) == len("fedex-vipvujg.shop")
        and d != "fedex-vipvujg.shop"
        for d, _ in rows
    )


def test_rdap_goes_straight_to_the_registry():
    servers = parse_bootstrap(
        {
            "services": [
                [["com", "net"], ["https://rdap.verisign.com/com/v1/"]],
                [["top"], ["http://x/", "https://rdap.zdnsgtld.com/top"]],
            ]
        }
    )
    assert rdap_url("example.com", servers) == "https://rdap.verisign.com/com/v1/domain/example.com"
    assert rdap_url("usps-fee.top", servers) == "https://rdap.zdnsgtld.com/top/domain/usps-fee.top"
    assert rdap_url("x.unknownending", servers).startswith("https://rdap.org/")
