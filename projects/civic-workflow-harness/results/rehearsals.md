# Deployment and rollback rehearsals

Generated 2026-11-04T00:18:11.767Z by `node deploy/rehearse.js --runs 3` on linux 6.18.44-fc-v230, Node v22.23.4, 4 CPU(s).
Each run starts from an empty deploy directory. Rollback time is measured from the first rollback step (stop 1.1.0) to the 20th smoke test passing on 1.0.0.

| Run | Install 1.0.0 | Upgrade to 1.1.0 (smoke) | Rollback to 1.0.0 (smoke) | Rollback time | Data path | Post-upgrade permit kept | Result |
|---|---|---|---|---|---|---|---|
| 1 | 0.35 s (17/20 pass, 3 skip, 0 fail) | 0.39 s (20/20 pass, 0 skip, 0 fail) | 20/20 pass, 0 skip, 0 fail | **0.39 s** | down-migration (post-upgrade records kept) | yes | PASS |
| 2 | 0.30 s (17/20 pass, 3 skip, 0 fail) | 0.37 s (20/20 pass, 0 skip, 0 fail) | 20/20 pass, 0 skip, 0 fail | **0.38 s** | down-migration (post-upgrade records kept) | yes | PASS |
| 3 | 0.30 s (17/20 pass, 3 skip, 0 fail) | 0.36 s (20/20 pass, 0 skip, 0 fail) | 20/20 pass, 0 skip, 0 fail | **0.37 s** | down-migration (post-upgrade records kept) | yes | PASS |

All runs passed: **yes**. Rollback time min / median / max: 0.37 s / 0.38 s / 0.39 s. All under 10 minutes: **yes**.

The install run skips smoke checks 5-7 (they compare against permits seeded before the deploy, and a first install has none).
These are local single-machine timings with mock downstream services; a real platform adds artifact transfer, approvals and slower dependencies (see README limitations).
