# LLM Data Analyst

A natural-language-to-insight agent: ask a plain-English question about a CSV, the agent writes
SQL, validates that it's read-only, runs it against a local DuckDB table, and explains the result
in plain English. If the generated SQL fails (bad column name, syntax error, or an attempt to
write/DDL), the error is fed back to the model and it retries, up to 3 attempts.

This is the hybrid project from [../../PROJECT_IDEAS.md](../../PROJECT_IDEAS.md#10-combined-track-llm-assisted-data-analysis-agent):
it exercises both data science judgment (schema reasoning, result interpretation) and AI
engineering execution (tool use, validation, self-correction loops).

## Architecture

```
question ─▶ DataAnalystAgent ─▶ LLM: question + schema ─▶ SQL
                  │                                          │
                  │                              sql_guard.validate_read_only_sql
                  │                                          │
                  │                              on failure: retry with error ◀┘
                  │                                          │
                  │                                     DuckDB: run_query
                  │                                          │
                  └──────────▶ LLM: question + SQL + rows ─▶ plain-English answer
```

- `llm_data_analyst/db.py` — DuckDB wrapper: loads a CSV as a table, exposes schema + query execution.
- `llm_data_analyst/sql_guard.py` — rejects anything that isn't a single `SELECT`/`WITH` statement (no DDL/DML, no multi-statement injection).
- `llm_data_analyst/llm_client.py` — thin wrapper around the Anthropic SDK behind a `complete(system, user) -> str` interface, so the agent doesn't depend on the SDK directly.
- `llm_data_analyst/agent.py` — the generate → validate → execute → explain loop, with retry-on-error.
- `llm_data_analyst/cli.py` — CLI entry point (single question or interactive REPL).

## Setup

```bash
cd projects/llm-data-analyst
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

Generate the sample dataset (already committed, but regeneratable):

```bash
python3 data/generate_sample_data.py
```

## Usage

```bash
python3 -m llm_data_analyst.cli --csv data/sample_sales.csv --question "Which region generated the most revenue in 2024?"
python3 -m llm_data_analyst.cli --csv data/sample_sales.csv   # interactive mode
```

## Tests

The test suite runs entirely offline — a `FakeLLM` stands in for the Anthropic client so the
retry loop and guard logic are covered without an API key or network access:

```bash
pytest
```

## Limitations

The SQL guard blocks write/DDL keywords and multi-statement input, but it's a keyword blocklist,
not a parser — it would not stop a sufficiently obfuscated statement, and DuckDB itself still runs
with whatever filesystem/table access the process has. It should be treated as a defense against
accidental bad queries from the model, not as an isolation boundary against an adversarial user; a
production version would run queries against a read-only connection or a sandboxed replica.
Result formatting also truncates to 20 rows before the "explain" call, so answers about datasets
with heavy tail distribution can miss outliers the model never saw.
