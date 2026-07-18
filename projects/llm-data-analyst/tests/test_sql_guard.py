import pytest

from llm_data_analyst.sql_guard import GuardError, validate_read_only_sql


def test_valid_select_passes():
    validate_read_only_sql("SELECT * FROM data")


def test_valid_with_cte_passes():
    validate_read_only_sql("WITH t AS (SELECT 1) SELECT * FROM t")


def test_empty_query_rejected():
    with pytest.raises(GuardError):
        validate_read_only_sql("   ")


def test_multiple_statements_rejected():
    with pytest.raises(GuardError):
        validate_read_only_sql("SELECT 1; DROP TABLE data;")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM data",
        "UPDATE data SET x = 1",
        "DROP TABLE data",
        "INSERT INTO data VALUES (1)",
        "ATTACH 'evil.db' AS evil",
        "PRAGMA table_info(data)",
        "CREATE TABLE evil AS SELECT * FROM data",
    ],
)
def test_forbidden_statements_rejected(sql):
    with pytest.raises(GuardError):
        validate_read_only_sql(sql)


def test_non_select_start_rejected():
    with pytest.raises(GuardError):
        validate_read_only_sql("EXPLAIN SELECT * FROM data")
