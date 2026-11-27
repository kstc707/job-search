# Pickup ETA and late-window alerts (Cainiao LaDe)

When a courier accepts a pickup, predict when they will arrive and whether they will miss the customer's
time window, so the customer hears about a delay **before** the window passes, not after.

Built on real operations data: **1.42 million pickups by 4,494 couriers in Shanghai over six months**
(LaDe-P, Cainiao). Python service with a PostgreSQL store, LightGBM models tracked in MLflow, a FastAPI
API, a Streamlit operations page, pytest in GitHub Actions and a Docker image.

## Results (test month: October, 283,113 pickups, trained on May–August, tuned on September)

| Arrival time (ETA) | Mean abs. error | Median abs. error | Within 30 min |
|---|---|---|---|
| Region median duration (planned baseline) | 158.9 min | 62 min | 26% |
| "Courier arrives mid-window" rule | 59.3 min | 39 min | 39% |
| **LightGBM** | **48.8 min** | **32 min** | **47%** |

The fair comparison is the window rule, not the region baseline: the customer's window already tells you
most of the answer. LightGBM is **18% better** than the window rule (69% better than the region baseline).

| Late-window alerts, flagging 5% of pickups | Late pickups caught | Precision |
|---|---|---|
| Least time left before window end | 4% | 2% |
| Courier's past late rate (one number, no model) | 49% | 24% |
| **LightGBM** (threshold set on September, applied unchanged) | **53%** (3,639 of 6,858) | **26%** |

- 2.4% of pickups are late, so a flagged pickup is **11 times** as likely to be late as an average one.
- Warnings go out a median **207 minutes** before the window closes.
- ROC AUC 0.884 and PR AUC 0.298, against a base rate of 0.024.
- **Honest reading:** a single rule, the courier's own history, gets most of the way. The model adds
  4 points of recall, about 260 more customers warned per month. Courier history carries 47% of the
  model's split gain.

**What operations should change** (from `lade_eta/hotspots.py`, all on October data):
- The least reliable 5% of couriers (132 of 2,639) account for **83% of late pickups**; the top 1%
  account for 52%. Lateness is a courier problem much more than a city-wide one.
- Pickups accepted while the courier already had **more than 30 open tasks** ran late 10.3% of the
  time (6,890 pickups), against 2.2% otherwise. Recommendation: cap open tasks at 30.
- Each hotspot region gets one written recommendation with its numbers, e.g. region 53: *"Couriers 1022,
  15584, 13516 hold 70% of this region's 883 late pickups."*

**Service:**
- `/at-risk` returns exactly the same flagged orders as the offline test scoring at three replay times
  (201, 277 and 72 orders).
- A GiST index cut the open-task query from 3.3 s to 0.48 s.
- Load test (Locust, 20 users, 60 s, one 4-core machine also running Postgres and Locust):
  `/predict` at 92 requests/s, median 50 ms, p95 270 ms, 0 failures. Before the fixes below: 26
  requests/s, p95 830 ms.

## Why the pickup data, not the delivery data

The plan was to flag packages "before a promised delivery window is missed". LaDe's **delivery** files
have no promised window; only the **pickup** files carry the customer's requested window
(`time_window_start/end`). Inventing a promise for deliveries would make the late label made-up, so the
alerts are built where the promise is real: customer pickup windows.

## How it works

```
Hugging Face CSV ──ingest.py──▶ PostgreSQL `pickups` ──features.py──▶ LightGBM ETA + late risk (train.py, MLflow)
                    (quality checks)                                         │
                                                                  artifacts/bundle.joblib
                                                                             │
     repository.py (SQL: open tasks, courier workload, history) ──▶ api.py ──▶ notify.py (customer text)
                                                    dashboard/app.py ◀── test_scored.parquet + hotspots.py
```

| File | What it does |
|---|---|
| `lade_eta/settings.py` | All configuration from `LADE_*` environment variables or `.env` |
| `lade_eta/ingest.py` | Download, parse times, 4 counted quality rules, bulk `COPY` into PostgreSQL |
| `lade_eta/schema.sql` | Table and indexes (GiST range index for "open at time T") |
| `lade_eta/features.py` | 18 features known at accept time; history from earlier days only |
| `lade_eta/models.py` | Baselines and LightGBM wrappers behind one `fit/predict` interface |
| `lade_eta/train.py` | Time split, training, threshold for the alert budget, metrics, MLflow |
| `lade_eta/store.py` | Serving-time history snapshot; same numbers as training (tested) |
| `lade_eta/repository.py` | Live state from PostgreSQL (or pandas, for tests) |
| `lade_eta/api.py` | `/health`, `/predict`, `/at-risk`; JSON access logs |
| `lade_eta/notify.py` | Customer message; gives a time only when the ETA is past the window |
| `lade_eta/hotspots.py` | Hotspot table and one rule-based recommendation per region |
| `dashboard/app.py` | Streamlit operations page |
| `locustfile.py` | Load test with real October tasks |

## Decisions and why

- **Prediction time = when the courier accepts.** Every feature must be known then. Courier workload is
  counted from tasks already accepted and not yet picked up. History (late rate, typical minutes per
  courier, area and region) uses only outcomes from earlier days. A test rewrites a day's outcomes and
  checks that day's features do not move.
- **Time-ordered split.** The service predicts future days. Shuffling would leak each courier's later
  behaviour into training. The late rate also drifts (June 4.7%, July 1.6%), and a random split would
  hide that.
- **Alert threshold set on September, applied unchanged to October.** This is how it would run in
  production. Choosing it on the test month would overstate recall.
- **Training and serving share one feature definition.** `store.py` recomputes history from a snapshot,
  and `repository.py` computes workload in SQL. Tests check both match the training features exactly,
  and the API's October scores match the offline scores.
- **GiST index on `(courier_id, tsrange(accept_time, pickup_time))`.** "Was this task open at T" is a
  range question. A B-tree on `accept_time` still scans most of the table, because most tasks were
  accepted before T. Query time fell from 3.3 s to 0.48 s.
- **Throughput fixes, measured before changing anything:**
  - Each request costs about 30 ms, mostly pandas, which holds Python's lock, so one process saturates
    near 26 requests/s.
  - Fixes: 4 worker processes, a connection pool (opening a connection cost 8 ms), and one LightGBM
    thread per request.
- **Deterministic training** (`deterministic=True`, fixed seed): two runs give identical metrics.
- **Rule-based recommendations, not a language model.** Every sentence on the operations page is
  computed from counts in the same table.

Rejected:
- **Using the ETA alone to flag late pickups.** It catches only 6.5% of late pickups: L1 regression
  predicts typical times, not tails.
- **Day-of-week features.** LaDe publishes month and day but not the year, so the weekday is unknown.

## Limitations

- **Replay, not live.** "Now" is a time passed to `/at-risk`. Live use would need a stream of
  accept/pickup events into the same table.
- **Calibration.** In the riskiest tenth of pickups, predicted risk averages 10.7% while 16.2% were
  late. Rankings are good, but the scores are not probabilities to quote to customers. Recalibrating
  on recent weeks would fix this.
- **The recommendations are associations.** High-workload pickups run late more often, but a cap's
  effect should be tested on a few regions first (an A/B test or a staged rollout).
- **Thin data at the extremes.** The "51+ open tasks" bucket has only 20 pickups.
- **Simple courier history.** A courier's first days fall back to the city-wide rate. History is
  cumulative, with no decay, so a courier who improved keeps their old record for a while.
- **Docker image not yet built locally.** It could not be built in the development container: Docker Hub
  and its mirror returned 429 (rate limit). CI builds it and smoke-tests `/health` on every push.

## Run it

```bash
cd projects/lade-pickup-eta
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                        # point LADE_DATABASE_URL at your PostgreSQL 16
python -m lade_eta ingest                   # downloads Shanghai pickups (228 MB) and loads PostgreSQL
python -m lade_eta train                    # about 2 minutes; writes artifacts/ and logs to MLflow
python -m lade_eta serve                    # http://localhost:8000/docs
streamlit run dashboard/app.py              # operations page
```

```bash
curl "localhost:8000/at-risk?as_of=2022-10-12T10:00:00&limit=5"
```

Tests: `pytest` (27 tests). Set `TEST_DATABASE_URL` to a disposable database to include the 4 tests
that check the SQL against the pandas version. MLflow runs: `mlflow ui --backend-store-uri
sqlite:///artifacts/mlflow.db`. Docker: `docker compose up` (database and API) after training.

Data: [Cainiao-AI/LaDe](https://huggingface.co/datasets/Cainiao-AI/LaDe) (Apache-2.0), paper
[arXiv:2306.10675](https://arxiv.org/abs/2306.10675). The data is not committed. The timestamps have no
year, so 2022 is used only for date arithmetic.
