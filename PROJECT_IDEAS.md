# Project Ideas: AI Engineering & Data Science

A curated shortlist of portfolio projects for job hunting, split by track. Each includes the core skill it demonstrates, a suggested stack, and a stretch goal to make it stand out. Pick 2-3 total rather than starting all of them — depth beats breadth in interviews.

## AI Engineering

### 1. RAG system over a real document set
Build retrieval-augmented generation over something non-trivial (your own notes, a company's public docs, legal/medical text) rather than a toy PDF.
- **Demonstrates:** chunking strategy, embeddings, vector search, prompt design, evaluation of hallucination rate
- **Stack:** Claude/OpenAI API, a vector DB (Chroma, pgvector, or Qdrant), LangChain or plain Python
- **Stretch:** add re-ranking, citation grounding (answers link back to source spans), and a small eval set with precision/recall on retrieval

### 2. Multi-agent task orchestration
An agent system where a planner delegates subtasks to specialized tool-using agents (e.g., a research agent + a coding agent + a critic agent).
- **Demonstrates:** tool use, structured outputs, agent-to-agent handoff, failure recovery
- **Stack:** Claude Agent SDK / OpenAI function calling, a simple task queue
- **Stretch:** add a human-in-the-loop approval step and cost/latency tracking per agent

### 3. LLM evaluation & guardrails harness
A reusable framework that scores model outputs against a rubric (correctness, tone, safety) and flags regressions across prompt/model versions.
- **Demonstrates:** eval design, statistical thinking about non-deterministic systems, CI integration
- **Stack:** Python, pytest-style eval runner, an LLM-as-judge pattern, small labeled dataset
- **Stretch:** wire it into GitHub Actions so every prompt change runs the eval suite automatically

### 4. Production-style inference API
Wrap a fine-tuned or prompted model behind a real service: auth, rate limiting, streaming responses, observability.
- **Demonstrates:** systems engineering around ML, not just modeling
- **Stack:** FastAPI, Docker, Redis for rate limiting, OpenTelemetry or basic logging/metrics
- **Stretch:** load test it (Locust) and publish the latency/throughput numbers

### 5. Fine-tuning / LoRA on a narrow task
Fine-tune a small open model (Llama, Mistral, Qwen) for one specific job — e.g., structured data extraction from messy text.
- **Demonstrates:** understanding of when fine-tuning beats prompting, dataset curation, quantitative before/after comparison
- **Stack:** Hugging Face `transformers` + `peft`, a single GPU (Colab/Lambda), a hand-labeled eval set
- **Stretch:** quantize and benchmark inference cost vs. the prompted baseline

## Data Science

### 6. End-to-end predictive model with honest evaluation
Pick a dataset with a real decision behind it (churn, pricing, fraud, readmission risk) and take it from raw data to a deployed prediction, including a clear discussion of what the model gets wrong.
- **Demonstrates:** feature engineering, leakage awareness, calibration, business framing
- **Stack:** pandas/scikit-learn or XGBoost, a simple Streamlit dashboard for exploring predictions
- **Stretch:** add SHAP explanations and a section on what you'd need before trusting this in production

### 7. Time series forecasting with backtesting
Forecast something with real seasonality (demand, traffic, energy usage) and evaluate with proper walk-forward backtesting, not a single train/test split.
- **Demonstrates:** avoiding the most common time-series mistakes, uncertainty quantification
- **Stack:** Prophet/statsmodels or a gradient-boosted approach, `sktime` for backtesting
- **Stretch:** compare a classical model against an LLM-based forecaster and report where each wins

### 8. Experiment design / A-B testing simulator
Simulate an A/B test pipeline: power analysis, sequential testing, and a report that correctly interprets (or debunks) a "significant" result.
- **Demonstrates:** statistical rigor, the skill most DS portfolios skip
- **Stack:** Python, `statsmodels`, a notebook with simulated traffic data
- **Stretch:** implement CUPED variance reduction and show the effect on required sample size

### 9. Data pipeline + analytics on a messy public dataset
Build an ETL pipeline that ingests a genuinely messy public dataset (government open data, scraped data) into a clean warehouse schema, then answer 3-4 non-obvious questions with it.
- **Demonstrates:** data cleaning judgment, SQL fluency, pipeline reliability
- **Stack:** dbt or plain SQL, DuckDB/Postgres, Airflow or a lightweight scheduler
- **Stretch:** add data quality tests (Great Expectations) that fail the pipeline on bad input

### 10. Combined track: LLM-assisted data analysis agent
A natural-language-to-insight tool: user asks a question in plain English, agent writes and executes SQL/pandas, validates the result, and explains it.
- **Demonstrates:** the intersection recruiters increasingly screen for — DS judgment plus AI engineering execution
- **Stack:** Claude/GPT with code execution, a real dataset (not iris/titanic), guardrails against bad queries
- **Stretch:** add a self-correction loop where the agent checks its own SQL against the schema before running it

## Picking what to build

- If targeting **AI engineering roles**: prioritize #1, #2, #4 — they show you can ship production LLM systems, not just call an API.
- If targeting **data science roles**: prioritize #6, #7, #8 — they show statistical judgment, which is what separates DS from analyst titles.
- If targeting roles that blur the two (increasingly common): #10 is the strongest single project, since it forces both skill sets in one place.
- Whatever you pick, write the README as if a hiring manager has 90 seconds: problem, approach, one chart of results, one paragraph of limitations. The limitations paragraph is what signals seniority.
