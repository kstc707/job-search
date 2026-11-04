import pytest

from permit_reports import db, generator


@pytest.fixture(scope="session")
def conn():
    if not db.reachable():
        pytest.skip("SQL Server not reachable (start it with docker compose up -d; set MSSQL_SA_PASSWORD)")
    db.ensure_database()
    c = db.connect()
    _, rows = db.query(c, "SELECT OBJECT_ID('dbo.Permit')")
    loaded = False
    if rows[0][0] is not None:
        _, n = db.query(c, "SELECT (SELECT COUNT(*) FROM dbo.Permit) + (SELECT COUNT(*) FROM dbo.Fee) "
                           "+ (SELECT COUNT(*) FROM dbo.Inspection)")
        loaded = n[0][0] == 100_000
    if not loaded:
        db.run_script(c, "01_schema.sql")
        db.run_script(c, "02_indexes.sql")
        generator.load(c, generator.generate())
    yield c
    c.close()
