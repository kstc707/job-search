import re

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|copy|pragma|call|grant|revoke|export|import)\b",
    re.IGNORECASE,
)


class GuardError(ValueError):
    pass


def validate_read_only_sql(sql: str) -> None:
    """Reject anything but a single read-only SELECT/WITH statement."""
    if not sql or not sql.strip():
        raise GuardError("Empty SQL query.")

    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if len(statements) != 1:
        raise GuardError("Only a single SQL statement is allowed.")

    statement = statements[0]
    if not statement.lower().startswith(("select", "with")):
        raise GuardError("Only SELECT (or WITH ... SELECT) queries are allowed.")

    if _FORBIDDEN.search(statement):
        raise GuardError("Query contains a forbidden keyword; only read-only SELECTs are allowed.")
