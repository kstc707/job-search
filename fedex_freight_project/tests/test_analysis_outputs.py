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
