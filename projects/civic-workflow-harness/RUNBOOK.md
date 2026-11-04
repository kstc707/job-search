# Runbook: deploy and roll back the permit workflow service

Scope: upgrading the permit workflow service from one packaged release to the next (example: 1.0.0 to
1.1.0, which adds data-store migration 002) and rolling it back. Every step below is what
`deploy/deploy.js` and `deploy/rollback.js` do; the manual commands are listed so an operator can run or
check any step by hand. Rehearsed three times from a clean environment: see
[results/rehearsals.md](results/rehearsals.md).

Deploy directory: `$DEPLOY_DIR` (default `.deploy/`). It holds `releases/`, `current.json`,
`data/store.json`, `backups/`, `env.json`, `app.pid`, `app.log` and `history.jsonl`.

## 1. Before the change window

| Check | How | Pass when |
|---|---|---|
| Release is packaged and its manifest pins the expected schema | `node deploy/package.js 1.1.0`, then read `$DEPLOY_DIR/releases/1.1.0/release.json` | `version` 1.1.0, `schemaVersion` 2 |
| Unit and integration tests pass on the commit being released | `npm test` | 50 passing, 0 failing |
| Previous release artifact is still on disk (rollback target) | `ls $DEPLOY_DIR/releases/1.0.0` | present |
| Current state is known | `cat $DEPLOY_DIR/current.json`; `curl $PUBLIC_URL/health` | `version` matches `current.json`, `status` ok |
| No dead-lettered notifications or open reconciliation items you would lose track of | `curl $PUBLIC_URL/health` | `outbox.dead` 0 and `openReconciliation` 0, or noted in the change ticket |
| Downstream services up (payment, GIS, documents, notification) | `curl $PUBLIC_URL/health?deep=1` | every dependency `up` (deploy.js refuses to start otherwise) |
| Release notes and the rollback decision owner are in the change ticket | change ticket | named owner |

Communication: post the window, the expected user impact (a few seconds of 503s while the process
restarts), and the rollback owner in the team channel before starting.

## 2. Deploy

```bash
node deploy/deploy.js 1.1.0
```

Steps (stop at the first failure):

1. **Pre-check downstream services.** Any `/health` not 200: abort, nothing has changed.
2. **Stop the running release** (`SIGTERM`, 10 s grace, then `SIGKILL`). Stopping first makes the backup
   a consistent snapshot.
3. **Back up the data store** to `backups/<timestamp>-pre-deploy-1.1.0.json`. The path is written to
   `current.json` as the restore point.
4. **Migrate up with the new release**: `node releases/1.1.0/src/store/migrate-cli.js --data data --to 2`.
   On failure: the backup is restored, the previous release is restarted, deploy exits non-zero.
5. **Switch** `current.json` to `{version: 1.1.0, previous: 1.0.0, backup: <path>}`.
6. **Start** the new release and poll `/health` until it reports `version` 1.1.0 (15 s limit). A release
   that finds a store schema it does not understand exits during startup, and the deploy fails here.
7. **Smoke test**: the 20 checks in `smoke/run.js` (health, version, schema, dependencies, pre-existing
   records, a full create/document/submit/pay/callback/review/issue/inspect flow, replayed and forged
   callbacks, release-specific fields, notifications).
8. **Smoke failed: automatic rollback** (section 4), deploy exits non-zero. Smoke passed: record the
   result in `history.jsonl`, deploy exits 0.

## 3. Verify after deploy

- `curl $PUBLIC_URL/version`: `version` 1.1.0, `schemaVersion` 2.
- `curl $PUBLIC_URL/health?deep=1`: `status` ok, `storeSchemaVersion` 2, every dependency `up`.
- `tail -5 $DEPLOY_DIR/history.jsonl`: last line `"action":"deploy","ok":true`.
- Watch `app.log` and `/health` (`outbox.dead`, `openReconciliation`) for 30 minutes.

## 4. Roll back

### Triggers (any one)

- Smoke test failure after deploy (automatic).
- `/health` not ok, or the process restarting, after deploy.
- Fee totals, payment state or notifications wrong for real applicants.
- `outbox.dead` or `openReconciliation` rising after the deploy.
- Decision by the rollback owner. Do not debug in production past 15 minutes; roll back first.

### Procedure

```bash
node deploy/rollback.js            # to current.json's "previous"
node deploy/rollback.js --to 1.0.0 # explicit target
```

1. **Stop** the current release.
2. **Snapshot** the store as it is now (`backups/<timestamp>-pre-rollback-from-1.1.0.json`). This file
   holds everything written since the upgrade; it is never deleted by the tooling.
3. **Down-migrate with the newer release** (`releases/1.1.0/src/store/migrate-cli.js --to 1`). The older
   release does not ship migration 002, so it cannot undo it. Migration 002's down step keeps every
   permit, including ones created after the upgrade; it moves the v1.1-only fields (flood zone, SMS
   preference) into an archive that a later re-upgrade restores, and re-addresses pending SMS
   notifications to email.
4. **Fallback**: if the down migration fails (or `--force-restore` is passed), restore the pre-deploy
   backup from `current.json`. Records created after the upgrade then exist only in the snapshot from
   step 2 and must be re-entered by hand. The id counters are taken from the snapshot so no permit
   number is issued twice.
5. **Switch** `current.json` to the target, **start** it, poll `/health`.
6. **Smoke test** the 20 checks against the rolled-back release. Rollback is complete when they pass.

Target: previous version serving and smoke-green within 10 minutes of the decision. Rehearsed: 0.37 to
0.43 s for steps 1-6 on a single machine (results/rehearsals.md).

### After a rollback

- Post in the team channel: what triggered it, current version, whether the fallback restore was used.
- If the fallback restore was used: list the permits that exist only in the pre-rollback snapshot and
  contact those applicants.
- `POST /admin/reconcile` to settle any payment whose outcome was unknown, then
  `POST /admin/outbox/flush`.
- Open a ticket with the smoke output from `app.log` / `history.jsonl` before retrying the upgrade.

## 5. Drills

- `npm run rehearse`: three clean runs of install 1.0.0, seed, upgrade 1.1.0, roll back, verify.
- `npm run drill`: a deliberately bad 1.1.0 build (fee schedule changed) is caught by smoke check 12
  and rolled back automatically (results/failed-upgrade-drill.md).
