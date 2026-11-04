# Drill: failed upgrade with automatic rollback

Generated 2026-11-04T00:15:56.257Z by `node deploy/drill-failed-upgrade.js`.

- Bad build: 1.1.0 artifact with the technology fee changed from 4% to 5%.
- Smoke on 1.1.0: 16 passed, 1 failed, 3 skipped. Failed: #12 submit assesses fees from the fee schedule (fee 94500, expected 93600).
- Automatic rollback to 1.0.0: smoke green in 0.34 s; data path: down-migration (post-upgrade records kept).
- Live release afterwards: 1.0.0. Result: **PASS**.

```
[deploy] (none) -> 1.0.0 (schema 1)
[deploy] backup: (no data yet)
[deploy] migrate: {"from":0,"to":1,"applied":["up 1"]}
[deploy] smoke 17/20 passed, 0 failed, 3 skipped; 325 ms
[deploy] 1.0.0 -> 1.1.0 (schema 2)
[deploy] backup: ./.deploy/drill-failed-upgrade/backups/2026-11-04T00-15-55-566Z-pre-deploy-1.1.0.json
[deploy] migrate: {"from":1,"to":2,"applied":["up 2"]}
  FAIL 12. submit assesses fees from the fee schedule - fee 94500, expected 93600
[deploy] smoke 16/20 passed, 1 failed, 3 skipped; 350 ms
[deploy] smoke failed: rolling back automatically
[rollback] 1.1.0 -> 1.0.0 (reason: smoke_failed)
[rollback] down-migrate with 1.1.0: {"from":2,"to":1,"applied":["down 2"]}
[rollback] data: down-migration (post-upgrade records kept); snapshot ./.deploy/drill-failed-upgrade/backups/2026-11-04T00-15-55-912Z-pre-rollback-from-1.1.0.json
[rollback] smoke 17/20 passed, 0 failed, 3 skipped; 343 ms
```
