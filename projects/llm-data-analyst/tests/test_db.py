from llm_data_analyst.db import Database


def test_load_csv_and_schema(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("id,name,amount\n1,a,10.5\n2,b,20.0\n")

    db = Database()
    db.load_csv("data", str(csv_path))

    schema = db.schema_description()
    assert "Table data" in schema
    assert "id" in schema


def test_run_query_returns_columns_and_rows(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("id,name,amount\n1,a,10.5\n2,b,20.0\n")

    db = Database()
    db.load_csv("data", str(csv_path))

    columns, rows = db.run_query("SELECT SUM(amount) AS total FROM data")

    assert columns == ["total"]
    assert rows[0][0] == 30.5
