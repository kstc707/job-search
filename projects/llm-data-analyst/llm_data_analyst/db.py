import duckdb


class Database:
    """Thin wrapper around an in-memory DuckDB connection."""

    def __init__(self, path: str = ":memory:"):
        self.conn = duckdb.connect(path)

    def load_csv(self, table_name: str, csv_path: str) -> None:
        self.conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)",
            [csv_path],
        )

    def schema_description(self) -> str:
        tables = self.conn.execute("SHOW TABLES").fetchall()
        parts = []
        for (table_name,) in tables:
            columns = self.conn.execute(f"DESCRIBE {table_name}").fetchall()
            col_desc = ", ".join(f"{name} ({dtype})" for name, dtype, *_ in columns)
            parts.append(f"Table {table_name}: {col_desc}")
        return "\n".join(parts)

    def run_query(self, sql: str):
        result = self.conn.execute(sql)
        columns = [d[0] for d in result.description]
        rows = result.fetchall()
        return columns, rows
