import pytest

from email_uplift.data import EXPECTED_COLUMNS, prepare, validate_raw


def test_synthetic_fixture_matches_raw_schema(raw):
    assert list(raw.columns) == EXPECTED_COLUMNS
    validate_raw(raw, expected_rows=None)


def test_validate_rejects_wrong_row_count(raw):
    with pytest.raises(ValueError, match="rows"):
        validate_raw(raw)  # default expects 64,000


def test_validate_rejects_missing_column(raw):
    with pytest.raises(ValueError, match="columns"):
        validate_raw(raw.drop(columns="spend"), expected_rows=None)


def test_validate_rejects_spend_without_purchase(raw):
    bad = raw.copy()
    idx = bad.index[bad["conversion"] == 0][0]
    bad.loc[idx, "spend"] = 10.0
    with pytest.raises(ValueError, match="spend"):
        validate_raw(bad, expected_rows=None)


def test_prepare_fixes_typo_and_adds_labels(raw):
    df = prepare(raw)
    assert "Surburban" not in set(df["zip_code"])
    assert set(df["arm"]) == {"mens", "womens", "control"}
    assert not df[["recency_band", "spend_band", "customer_type", "past_purchase"]].isna().any().any()
    assert set(df["past_purchase"]) <= {"Men's only", "Women's only", "Both"}
