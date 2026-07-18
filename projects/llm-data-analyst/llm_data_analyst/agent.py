import re
from dataclasses import dataclass

from .db import Database
from .sql_guard import validate_read_only_sql

MAX_ATTEMPTS = 3

SQL_SYSTEM_PROMPT = """You are a data analyst assistant. You are given a DuckDB table schema and a
question in plain English. Respond with a single read-only SQL query (SELECT only) that answers the
question. Output only the SQL — no explanation, no markdown fences."""

EXPLAIN_SYSTEM_PROMPT = """You are a data analyst assistant. Given a user's question, the SQL query
used to answer it, and the resulting rows, write a concise plain-English answer (2-4 sentences).
Cite concrete numbers from the result. Do not restate the SQL."""


@dataclass
class AgentResult:
    question: str
    sql: str
    columns: list
    rows: list
    answer: str
    attempts: int


class DataAnalystAgent:
    """Turns a natural-language question into a validated SQL query, executes it,
    and explains the result — retrying with the error fed back to the model on
    failure, up to MAX_ATTEMPTS."""

    def __init__(self, db: Database, llm):
        self.db = db
        self.llm = llm

    def ask(self, question: str) -> AgentResult:
        schema = self.db.schema_description()
        error_context = ""
        last_sql = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            sql = self._generate_sql(question, schema, error_context)
            last_sql = sql
            try:
                validate_read_only_sql(sql)
                columns, rows = self.db.run_query(sql)
                answer = self._explain(question, sql, columns, rows)
                return AgentResult(question, sql, columns, rows, answer, attempt)
            except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure feeds back into the retry loop
                error_context = (
                    f"The previous query failed with this error:\n{exc}\n"
                    f"Previous query:\n{sql}\nFix it and return only the corrected SQL."
                )

        raise RuntimeError(
            f"Failed to answer question after {MAX_ATTEMPTS} attempts. Last SQL tried: {last_sql}"
        )

    def _generate_sql(self, question: str, schema: str, error_context: str) -> str:
        prompt = f"Schema:\n{schema}\n\nQuestion: {question}\n"
        if error_context:
            prompt += f"\n{error_context}\n"
        raw = self.llm.complete(system=SQL_SYSTEM_PROMPT, user=prompt)
        return self._strip_sql(raw)

    @staticmethod
    def _strip_sql(raw: str) -> str:
        text = raw.strip()
        text = re.sub(r"^```sql\s*|^```\s*|```$", "", text, flags=re.MULTILINE).strip()
        return text

    def _explain(self, question: str, sql: str, columns: list, rows: list) -> str:
        preview = self._format_rows(columns, rows)
        prompt = f"Question: {question}\nSQL: {sql}\nResult:\n{preview}"
        return self.llm.complete(system=EXPLAIN_SYSTEM_PROMPT, user=prompt)

    @staticmethod
    def _format_rows(columns: list, rows: list, limit: int = 20) -> str:
        lines = [", ".join(columns)]
        for row in rows[:limit]:
            lines.append(", ".join(str(value) for value in row))
        if len(rows) > limit:
            lines.append(f"... ({len(rows) - limit} more rows)")
        return "\n".join(lines)
