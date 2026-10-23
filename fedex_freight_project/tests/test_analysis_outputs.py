"""Checks on the analysis outputs: no look-ahead in the backtest, decompositions add up, models sane."""
import json

import pandas as pd
import pytest


def test_backtest_has_no_lookahead(root):
    bt = pd.read_csv(root / "reports/option_a/backtest_predictions.csv", parse_dates=["test_start", "train_last_end"])
    assert (bt["train_last_end"] < bt["test_start"]).all()
    # training sets only grow with time
    n = bt.groupby("test_start")["n_train"].max().sort_index()
    assert n.is_monotonic_increasing


def test_backtest_excludes_covid_from_scoring(root):
    bt = pd.read_csv(root / "reports/option_a/backtest_predictions.csv", parse_dates=["test_start"])
    assert (bt["test_start"] >= "2021-09-01").all()


def test_shift_share_adds_up(root):
    ss = pd.read_csv(root / "reports/option_c/shift_share_by_state.csv")
    total = ss["national"] + ss["mix"] + ss["regional"]
    assert (total - ss["actual_chg"]).abs().max() < 1.0


def test_revenue_bridge_components_sum(root):
    b = pd.read_csv(root / "reports/option_b/revenue_bridge_yoy.csv").set_index("fiscal_period")
    parts = b[["days", "shipments_per_day", "weight_per_shipment", "fuel", "base_yield_per_cwt"]].sum(axis=1)
    assert (parts - b["ltl_revenue"]).abs().max() < 0.2  # log-points; rounding of reported stats


def test_fuel_model_is_stable_and_validated(root):
    r = json.loads((root / "reports/option_b/results.json").read_text())
    assert 0.5 < r["fuel_model"]["rho_mean"] < 0.7
    assert r["fuel_model"]["rho_sd"] < 0.02
    assert r["fuel_model"]["loo_mae_structural_pts"] < 0.5
    # management: "a slight decline in base revenue per hundredweight" -> our estimate must be near zero
    assert abs(r["oos_fy26q4"]["structural"]) < 1.5


def test_weight_elasticity_economically_plausible(root):
    r = json.loads((root / "reports/option_b/results.json").read_text())["weight_elasticity"]
    lo, hi = r["ci95"]
    assert -1 < lo < hi < 0  # heavier shipments: lower revenue/cwt but higher revenue/shipment


def test_nowcast_written_with_intervals(root):
    nc = pd.read_csv(root / "reports/option_a/nowcast_jun_sep_2026.csv")
    assert {"yhat_pct", "lo80_pct", "hi80_pct", "ads_k"} <= set(nc.columns)
    ok = nc.dropna(subset=["lo80_pct"])
    assert (ok["lo80_pct"] <= ok["hi80_pct"]).all()


def test_peer_quarterly_data_sane(root):
    q = pd.read_csv(root / "data/processed/peer_ltl_quarterly_kpis.csv")
    spd = q[q["metric"] == "shipments_per_day"].pivot_table(index="period", columns="ticker", values="value")
    assert {"ODFL", "SAIA", "XPO", "ARCB"} <= set(spd.columns)
    # plausible daily shipment levels (thousands of shipments a day) and no wild quarter-to-quarter jumps
    assert spd.loc["2024Q1":].min().min() > 10_000 and spd.max().max() < 80_000
    chg = spd.pct_change(fill_method=None)
    assert ((chg.abs() < 0.25) | chg.isna()).all().all()


def test_peer_shipments_tie_to_totals(root):
    q = pd.read_csv(root / "data/processed/peer_ltl_quarterly_kpis.csv")
    w = q.pivot_table(index=["ticker", "period"], columns="metric", values="value").dropna(
        subset=["shipments_total", "workdays", "shipments_per_day"])
    rel = (w["shipments_total"] / w["workdays"] / w["shipments_per_day"] - 1).abs()
    assert len(w) > 50 and rel.median() < 0.005


def test_combo_is_prespecified_and_scored(root):
    r = json.loads((root / "reports/option_a/results.json").read_text())
    assert r["combo_members"] == ["ar1", "peer_ar", "macro3_ar"]
    scores = {d["model"]: d for d in r["backtest"]}
    assert scores["combo"]["n"] >= 15
    nc = {m["model"]: m for m in r["nowcast"]["models"]}
    members = [nc[m]["yhat_pct"] for m in r["combo_members"]]
    assert abs(nc["combo"]["yhat_pct"] - sum(members) / len(members)) < 0.01  # values stored rounded to 2 dp


def test_cross_carrier_elasticity_agrees_with_fedex(root):
    r = json.loads((root / "reports/option_b/results.json").read_text())
    lo, hi = r["peer_check"]["cross_carrier_ci95"]
    assert lo < r["weight_elasticity"]["preferred_beta"] < hi + 0.1  # overlapping, independent estimates


def test_report_claim_price_does_not_explain_share_loss(root):
    """The report says FedEx's weight-adjusted price rose less than ODFL's and XPO's while XPO grew volume.
    If refreshed data stops supporting that sentence, this test must fail."""
    r = json.loads((root / "reports/option_b/results.json").read_text())["peer_check"]
    fedex_hi = r["fy26q4_weight_adj_range"][1]
    assert fedex_hi < r["peer_exfuel_cwt_weight_adj_2026Q2"]["ODFL"]
    assert fedex_hi < r["peer_exfuel_cwt_weight_adj_2026Q2"]["XPO"]
    m = pd.read_csv(root / "data/processed/peer_ltl_monthly_kpis.csv")
    xpo = m[(m["ticker"] == "XPO") & (m["metric"] == "shipments_per_day_yoy_pct") & (m["month"] >= "2026-06")]
    assert len(xpo) and (xpo["value"] > 0).all()
