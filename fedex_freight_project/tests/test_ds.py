"""Tests for the ltlds package: point-in-time features, no look-ahead, evaluation statistics, share model."""
import hashlib
import sys

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def ltlds(root):
    sys.path.insert(0, str(root))
    import ltlds.evaluate as ev
    import ltlds.panel as pn
    import ltlds.share as sh
    return pn, ev, sh


def test_monthly_update_filed_after_tau_is_ignored(ltlds):
    pn, _, _ = ltlds
    p = pd.DataFrame({"ticker": ["A", "B"], "end": pd.to_datetime(["2026-06-30"] * 2), "known": pd.to_datetime(["2026-05-01"] * 2),
                      "spd": [100.0, 100.0], "y": [1.0, 1.0]})
    mon = pd.DataFrame({"ticker": ["A", "A", "B"], "month": pd.to_datetime(["2026-07-01", "2026-08-01", "2026-07-01"]),
                        "filed": pd.to_datetime(["2026-08-05", "2026-10-15", "2026-08-03"]), "y_m": [2.0, 50.0, -1.0]})
    mac = pd.DataFrame({"ipman": [1.0]}, index=pd.to_datetime(["2025-07-01"]))
    f = pn.window_features(p, mon, mac, "A", pd.Timestamp("2026-07-01"), pd.Timestamp("2026-09-30"), pd.Timestamp("2026-09-30"))
    assert f["own_m"] == 2.0 and f["own_m_n"] == 1  # the Aug value filed Oct 15 is not used
    assert f["mkt_m"] == -1.0 and f["mkt_m_n"] == 1


def test_macro_uses_only_published_months(ltlds):
    pn, _, _ = ltlds
    idx = pd.date_range("2025-01-01", "2026-12-01", freq="MS")
    mac = pd.DataFrame({"ipman": np.where(idx >= "2026-09-01", 1000.0, 100.0)}, index=idx)
    mac.loc[mac.index < "2026-01-01", "ipman"] = 100.0
    out = pn._macro_window_yoy(mac, pd.Timestamp("2026-07-01"), pd.Timestamp("2026-09-30"))
    assert abs(out["ipman"]) < 1e-9  # the (huge) September value is not yet published at Sep 30


def test_panel_valid_and_point_in_time(ltlds, root):
    pn, _, _ = ltlds
    p = pd.read_csv(root / "reports/ds/panel.csv", parse_dates=["end", "tau", "known"])
    assert pn.validate_panel(p) == []
    assert (p["known"] > p["tau"]).all()


def test_backtest_never_trains_on_unpublished_targets(root):
    bt = pd.read_csv(root / "reports/ds/backtest_predictions.csv", parse_dates=["tau", "train_last_known"])
    assert (bt["train_last_known"] < bt["tau"]).all()


def test_conformal_coverage_on_iid_noise(ltlds):
    _, ev, _ = ltlds
    rng = np.random.default_rng(0)
    taus = pd.date_range("2010-03-31", periods=400, freq="QE")
    bt = pd.DataFrame({"ticker": "X", "tau": taus, "y": rng.normal(0, 1, 400), "yhat": 0.0})
    out = ev.add_conformal(bt, level=0.8, min_res=30)
    iv = out.dropna(subset=["lo"])
    cov = ((iv["y"] >= iv["lo"]) & (iv["y"] <= iv["hi"])).mean()
    assert 0.74 <= cov <= 0.86


def test_diebold_mariano_detects_better_forecast(ltlds):
    _, ev, _ = ltlds
    rng = np.random.default_rng(1)
    taus = pd.date_range("2015-03-31", periods=60, freq="QE")
    y = rng.normal(0, 3, 60)
    good = pd.DataFrame({"ticker": "X", "tau": taus, "y": y, "yhat": y + rng.normal(0, 0.5, 60)})
    bad = pd.DataFrame({"ticker": "X", "tau": taus, "y": y, "yhat": y + rng.normal(0, 3, 60)})
    stat, p, T = ev.diebold_mariano(good, bad)
    assert stat < 0 and p < 0.01 and T == 60
    stat2, p2, _ = ev.diebold_mariano(bad, bad.assign(yhat=bad["yhat"] + rng.normal(0, 1e-6, 60)))
    assert p2 > 0.1


def test_changepoint_detector_recovers_known_shifts(ltlds):
    _, _, sh = ltlds
    x = np.r_[np.zeros(12), np.full(10, -5.0), np.full(12, 1.0)] + np.random.default_rng(2).normal(0, 0.5, 34)
    assert sh.optimal_partition(x, penalty=10.0) == [12, 22]
    assert sh.optimal_partition(np.random.default_rng(3).normal(0, 0.5, 34), penalty=10.0) == []


def test_shares_sum_to_one(root):
    s = pd.read_csv(root / "reports/ds/share_panel.csv")
    assert (s.groupby("cq")["share"].sum() - 1).abs().max() < 1e-9
    assert s.groupby("cq")["ticker"].nunique().eq(5).all()


def test_share_elasticity_is_negative_and_beats_placebo(root):
    import json
    r = json.loads((root / "reports/ds/share_results.json").read_text())
    prim = r["elasticity_specs"]["primary: peers, carrier FE, +lag"]
    assert prim["b0_ci"][1] < 0
    assert r["placebo"]["p_value"] < 0.05


def test_prospective_forecasts_match_their_hash(root):
    f = root / "ds/prospective_forecasts.csv"
    if not f.exists():
        pytest.skip("prospective forecasts not generated yet")
    digest = (root / "ds/prospective_forecasts.sha256").read_text().split()[0]
    assert hashlib.sha256(f.read_bytes()).hexdigest() == digest
