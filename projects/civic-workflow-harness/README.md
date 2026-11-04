# Civic Workflow & Integration Test Harness

A mock building-permit workflow (draft to finaled) that talks to four downstream systems (payment,
GIS, document storage, notifications) over REST, plus a mock of those systems that injects faults on
demand, 50 tests for what goes wrong at the integration boundaries, and deployment and rollback scripts
that were rehearsed three times from a clean environment.

**Results (measured, reproducible with the commands below):**

| What | Result |
|---|---|
| `npm test` | **50 tests, 50 passing**: 11 missing/invalid fields, 12 duplicate/out-of-order/forged callbacks, 8 timeouts, 9 failed downstream services, 6 workflow rules, 4 migrations and release compatibility |
| Upgrade smoke suite (`smoke/run.js`) | **20 checks**, run after every deploy and every rollback; 20/20 passing after each upgrade and each rollback |
| Rollback rehearsals (`npm run rehearse`) | **3 of 3 passed**; 1.1.0 back to 1.0.0, smoke-green in **0.39 s, 0.38 s, 0.37 s** ([results/rehearsals.md](results/rehearsals.md)) |
| Failed-upgrade drill (`npm run drill`) | a bad build is caught by smoke check 12 and rolled back automatically in 0.34 s ([results/failed-upgrade-drill.md](results/failed-upgrade-drill.md)) |

Zero npm dependencies: Node 20+ only (`node:test`, `node:http`, `fetch`, `node:crypto`).

> **Vendor-neutral mock.** This is not Accela, EMSE, or any vendor's API. Event hooks use generic names
> (`beforeSubmit`, `afterPaymentReceived`, ...). It models the patterns a civic permitting platform needs
> (event scripts around state transitions, payment webhooks, GIS validation). Writing or testing real
> EMSE scripts requires authorized access to an Accela environment; nothing here touches one.

## The problem

Permit platforms fail at the seams, not in the happy path: a payment provider times out after taking
the money, sends the same webhook three times, or sends "pending" after "succeeded"; GIS is down at
submit time; the email gateway rejects everything for an hour. And each upgrade carries a data
migration that someone has to be able to undo at 2 a.m. This project builds those seams on purpose and
tests each one.

## Architecture

```
                         config/workflow.json  (states, transitions, required fields/documents,
                         config/fees.json       event hooks per transition, fee schedule)
                                   │
 client ──REST──▶ src/app.js ──▶ src/service.js ──▶ src/workflow/engine.js ──▶ hooks (beforeSubmit: validate
   │                  │               │                                          fields, GIS zoning, documents;
   │                  │               │                                          afterSubmit: fees; after*: notify)
   │                  │               ▼
   │                  │        src/store/store.js   JSON file, one writer at a time, atomic writes,
   │                  │        (permits, processed    schema version + numbered up/down migrations
   │                  │         webhook events,
   │                  │         reconciliation,
   │                  │         notification outbox)
   │                  ▼
   │           src/adapters/*   timeout per call (AbortController), retries with backoff for idempotent
   │                  │         calls only, idempotency keys, typed errors
   │                  ▼
   │           mocks/downstream.js   /payment  /gis  /documents  /notify   + POST /__faults
   │                  │
   └──◀── POST /callbacks/payment (HMAC-signed webhook) ◀──┘
```

### What fails how

| Downstream failure | Behaviour | Why |
|---|---|---|
| GIS timeout / 5xx | retried twice with backoff, then submit returns 504/503 and the permit stays draft | a read, so retrying is safe; approving work on an unverified parcel is worse than asking the applicant to retry |
| GIS 404 / zoning not allowed | 422 to the applicant, not retried | a real answer, not an outage |
| Payment 5xx | retried with the **same** Idempotency-Key, then 503; nothing recorded | the provider dedups the key, so a retry cannot double-charge |
| Payment timeout | **not** retried; 202 with payment `unknown` and a reconciliation item; a late callback or `POST /admin/reconcile` settles it | the charge may already exist: retrying blind, or reporting failure, are both wrong |
| Duplicate / replayed webhook | 200 `{duplicate: true}`, no state change (dedup on event id, durable across restarts) | providers retry deliveries |
| Out-of-order webhook | events carry a sequence; an older one arriving late is recorded as stale and ignored | "pending" after "succeeded" must not un-pay a permit |
| Bad signature, non-JSON body, amount mismatch, unknown charge | 401 / 400 / reconciliation item / orphan record | never trust the webhook body before checking it |
| Notification timeout / 5xx | the workflow step still succeeds; message stays in the outbox, retried, dead-lettered after 5 attempts and shown in `/health` | a missed email must never block a permit |
| Document upload failure | 503/504, nothing recorded, not retried | upload is not idempotent |

### Releases and rollback

`deploy/package.js` builds an artifact per version from `deploy/releases.json`. 1.0.0 pins schema 1;
1.1.0 pins schema 2 and ships migration 002 (GIS flood zone on permits, so high-risk zones require an
elevation certificate; SMS notification preference). A release only ships the migrations up to its
schema, so **rollback has to run the down migration with the newer release before switching back**,
which is what `deploy/rollback.js` does. The step-by-step procedure, triggers and checks are in
[RUNBOOK.md](RUNBOOK.md).

## Run it

```bash
cd projects/civic-workflow-harness
npm test                 # 50 tests, about 4 s, no network needed
npm run rehearse         # 3 clean install/upgrade/rollback rehearsals -> results/rehearsals.{md,json}
npm run drill            # bad upgrade caught by smoke, automatic rollback -> results/failed-upgrade-drill.md
```

Run the pieces by hand:

```bash
npm run mocks                                   # mock downstream on :4100 (terminal 1)
AUTO_MIGRATE=1 npm start                        # app on :3000, data in ./data (terminal 2)
BASE_URL=http://127.0.0.1:3000 npm run smoke    # 20 smoke checks against it (terminal 3)
curl -X POST localhost:4100/__faults -d '{"service":"gis","status":503}'   # break GIS, try a submit
```

Deploy and roll back with the scripts (the mock must be running on :4100):

```bash
node deploy/package.js 1.0.0 1.1.0
node deploy/deploy.js 1.0.0
node deploy/deploy.js 1.1.0
node deploy/rollback.js
```

## API

`POST /permits` · `GET /permits[?status=&tag=]` · `GET|PATCH /permits/:id` · `POST /permits/:id/documents`
· `POST /permits/:id/submit` · `POST /permits/:id/payments` · `POST /permits/:id/transitions`
(`start_review`, `approve`, `reject` with `reason`, `issue`) · `POST /permits/:id/inspections` ·
`POST /callbacks/payment` · `GET /health[?deep=1]` · `GET /version` · `GET /admin/outbox` ·
`POST /admin/outbox/flush` · `GET /admin/reconciliation` · `POST /admin/reconcile`.

Errors are `{"error": {"code", "message", "service?", "details?"}}`; clients branch on `code`.

## A bug the rehearsal tooling found

The first run of the backup-restore fallback (`rollback.js --force-restore`) failed 5 of 20 smoke checks.
Restoring the backup rewound the id counters, so the next payment reused an idempotency key the
provider had already seen: the provider returned the old, already-paid charge and sent no webhook, and
the permit sat in "pending" forever. Notification ids had the same flaw (the gateway would have
"deduplicated" a different applicant's email). Fix: idempotency keys and message ids carry a random
suffix, and a restore never rewinds counters (permit numbers are not reissued). After the fix the
restore path passes smoke.

## Limitations

- A mock, not a platform. The downstream services are one in-process mock with simplified contracts;
  real payment processors, GIS layers and Accela/EMSE have different APIs, auth, and failure modes.
- Single node. The store is one JSON file with one writer at a time, and the write lock is held during
  downstream calls (bounded by the adapter timeout). Fine for a harness; a real system needs a database
  with transactions and per-record locking.
- Rollback timings are local. 0.4 s is a scripted rollback on one machine with no artifact transfer,
  load balancer drain, change approval or data volume. The 10-minute target in the runbook is for a
  real environment; these rehearsals show the procedure works end to end, not how long a production
  rollback takes.
- The rehearsed rollback is a planned one after a healthy upgrade; the automatic rollback after a failed
  smoke test is exercised by one drill, not three.
- Admin endpoints have no authentication, webhook signatures have no timestamp window (replays are
  stopped by event-id dedup instead), and nothing is load-tested.
