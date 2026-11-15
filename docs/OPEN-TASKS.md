# Open tasks

Last updated: 2026-11-15

## PRs
- #56 (bump almaapitk to >=0.7.0; audit SAFE, 142 tests pass, CI green) — Hagay: run the SANDBOX end-to-end check (one lending + one borrowing form; the sandbox clone has no forms config), then merge to `main`, one clean DevSandbox cycle on masedet, then Hagay merges to `prod`

## Issues
- #55 (almaapitk 0.7.0 bump tracker, per `docs/almaapitk-bump-protocol.md`) — at the sandbox-check step; closes with PR #56 → prod
- #54 (failure-mode audit: map the run context, then find unintended loops and side effects; filed in 13 repos 2026-11-10, replaced #51) — not started; can be done without outside input
- #32 (borrowing: proxy-user resolution and velocity/terms-of-use limits on the 8 funnel accounts are unprobed) — question, needs a decision on probing

## Other
- Stale local branches `docs/prod-duplicate-check-decision`, `release/failed-folder`, `fix/failed-folder`, `worktree-docs-prod-duplicate-check-decision` (all landed via #49/#50/#53) — delete, on Hagay's OK
- Follow-up from the 0.7.0 bump: adopt `reconcile=True` on Alma creates (separate change, after #56 reaches prod)
- Track the prod batch file `batch/rs_forms_monitor_prod.bat` for parity with its sandbox sibling (runbook §7 TODO)
