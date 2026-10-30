"""Checks that keep the lab honest: deterministic data, no answer-key leakage, a clean
out-of-time split, and controls that fire on the patterns they are written for."""

import pandas as pd
import pytest

from fraudlab import detect
from fraudlab.features import FEATURES, UnionFind, build, claim_text
from fraudlab.generate import generate


@pytest.fixture(scope="module")
def small():
    d = generate(n_accounts=400, seed=3)
    f, _ = build(d.shipments, d.claims, d.truth)
    return d, f


def test_generation_is_deterministic():
    a, b = generate(n_accounts=150, seed=11), generate(n_accounts=150, seed=11)
    pd.testing.assert_frame_equal(a.shipments, b.shipments)
    pd.testing.assert_frame_equal(a.claims, b.claims)


def test_every_scheme_is_planted(small):
    d, _ = small
    assert set(d.truth.scheme) == {"ATO", "UNDER", "RING"}


def test_features_never_use_the_answer_key():
    banned = {"fraud", "schemes", "dollars_at_risk", "is_fraud", "scheme", "lost_revenue"}
    assert not banned & set(FEATURES)


def test_train_and_test_months_do_not_overlap():
    assert not set(detect.TRAIN_MONTHS) & set(detect.TEST_MONTHS)
    assert min(detect.TEST_MONTHS) > max(detect.TRAIN_MONTHS)


def test_text_similarity_ignores_same_account_and_future_claims():
    claims = pd.DataFrame({
        "account_id": ["A1", "A1", "A2"], "month": [1, 1, 0],
        "narrative": ["never received package refund now", "never received package refund now",
                      "box arrived crushed laptop broken"],
        "claim_type": ["not_received"] * 3, "amount": [1, 1, 1],
    })
    out = claim_text(pd.concat([claims, claims.assign(account_id=["B1", "B2", "B3"], month=[5, 5, 5])]))
    # A1's two identical stories are the same account: not counted against each other
    assert out.loc[0, "near_dup_claims"] == 0
    # the copies filed in month 5 by other accounts are in A1's future: also not counted
    assert out.loc[0, "max_sim_other_account"] == 0


def test_rules_fire_on_the_patterns_they_target():
    f = pd.DataFrame({"volume_ratio": [6.0, 1.0], "n_ship": [40, 40], "new_device_share": [0.9, 0.0],
                      "new_dest_share": [0.9, 0.0], "low_weight_share": [0.6, 0.0],
                      "max_device_accounts": [5, 1], "n_claims": [4, 0], "not_received_share": [1.0, 0.0],
                      "drop_dest_share": [0.7, 0.0], "billed": [100.0, 100.0]})
    out = detect.apply_rules(f)
    assert out.loc[0, list(detect.RULES)].all()
    assert not out.loc[1, list(detect.RULES)].any()


def test_union_find_links_accounts_transitively():
    uf = UnionFind()
    uf.union("A", "B")
    uf.union("B", "C")
    assert uf.find("A") == uf.find("C") != uf.find("D")


def test_hybrid_queue_beats_rules_on_dollars(small):
    _, f = small
    scored = detect.fit_models(detect.apply_rules(f))
    res = detect.evaluate(scored, capacities=(10,))["methods"]
    assert res["hybrid"]["at_capacity"][10]["dollar_share"] >= res["rules"]["at_capacity"][10]["dollar_share"]
