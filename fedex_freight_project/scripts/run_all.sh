#!/usr/bin/env bash
# Rebuild every analysis output, figure, page and the brief, then run the tests. From the project root:
#   bash scripts/run_all.sh          (assumes data/raw is populated; see scripts/download_data.sh)
set -euo pipefail
PY=".venv/bin/python -I"
$PY scripts/parse_fedex_freight_segment.py data/raw/sec_edgar/fedex_corp_earnings data/processed/_fedex_corp_segment_rows.csv > /dev/null
$PY scripts/parse_fdxf_recast.py data/raw/sec_edgar/8-K_2026-08-06_ex99_recast_cy2025_cy2024.htm data/processed/fdxf_calendar_quarterly_kpis_recast.csv > /dev/null
[ -f data/processed/faf5_7_1.parquet ] || $PY scripts/faf5_to_parquet.py data/raw/faf5/FAF5.7.1/FAF5.7.1.csv data/processed/faf5_7_1.parquet
$PY scripts/parse_peer_kpis.py data/raw/sec_edgar/peers data/processed > reports/peer_parse_output.txt
$PY scripts/validate_peer_kpis.py data/processed > reports/peer_validation_output.txt
$PY scripts/eda.py > reports/eda_output.txt
$PY scripts/option_a_nowcast.py > reports/option_a_output.txt
$PY scripts/option_b_yield.py > reports/option_b_output.txt
$PY scripts/option_c_faf_lanes.py > reports/option_c_output.txt
$PY scripts/option_d_value_sensitivity.py > reports/option_d_output.txt
$PY scripts/make_report_figures.py
$PY scripts/ds_build_panel.py > reports/ds/panel_output.txt
$PY scripts/ds_nowcast_eval.py > reports/ds/nowcast_eval_output.txt   # ~20 min
$PY scripts/ds_nowcast_posthoc.py > reports/ds/posthoc_output.txt
$PY scripts/ds_conformal_groups.py > reports/ds/conformal_groups_output.txt
$PY scripts/ds_share_model.py > reports/ds/share_model_output.txt
# ds_prospective.py is NOT rerun: ds/prospective_forecasts.csv was locked on 2026-10-23 (see its .sha256)
$PY scripts/build_report.py
$PY scripts/build_brief.py
$PY scripts/build_email.py > /dev/null
$PY scripts/build_readme.py
.venv/bin/python -m pytest -q tests
