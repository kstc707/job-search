"""Settings fixed by ds/PREREGISTRATION.md. Changing any of these is a deviation and must be logged."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, PROC, OUT = ROOT / "data/raw", ROOT / "data/processed", ROOT / "reports/ds"

CARRIERS = ["FDX", "ODFL", "SAIA", "XPO", "ARCB"]
PEERS = ["ODFL", "SAIA", "XPO", "ARCB"]
REPORT_LAG_DAYS = 45            # a quarter's results are treated as published 45 days after quarter end
MACRO_LAG_MONTHS = 1            # monthly macro for month m is usable once month m+1 has ended
COVID = ("2020-03-01", "2021-08-31")
TEST_FROM = "2022-01-01"        # scored test period
BURN_IN_FROM = "2018-12-31"     # earlier origins only produce residuals for conformal calibration
INNER_ORIGINS = 8               # nested tuning: last 8 issue dates of each training set
INTERVAL = 0.80
CONFORMAL_MIN_RESIDUALS = 15
SEED = 20261023

MACRO = {"ipman": "IPMAN", "tonnage": "TRUCKD11", "cass": "FRGSHPUSM649NCIS", "ppi_ltl": "PCU484122484122",
         "dgorder": "DGORDER", "isratio": "ISRATIO"}
DIFF_SERIES = {"isratio"}        # ratios enter as differences, not log changes

FEATURE_GROUPS = {
    "own_history": ["y_l1", "y_l2", "y_l4", "dy_l1"],
    "own_monthly": ["own_m", "own_m_n"],
    "market": ["mkt_m", "mkt_m_n", "mkt_l1"],
    "macro": ["ipman", "tonnage", "cass", "dgorder", "isratio", "diesel"],
    "price_mix": ["cwt_yoy_l1", "wps_yoy_l1", "ppi_ltl"],
    "carrier": ["carrier_code"],
}
