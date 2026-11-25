# Open tasks

Last updated: 2026-11-25

## Issues
- #54 (failure-mode audit: map the run context, then find unintended loops and side effects; filed in 13 repos 2026-11-10) — not started; can be done without outside input

## Other
- Adopt `reconcile=True` on Alma creates (almaapitk 0.7.0 is in prod since 2026-11-25; finds the request a timed-out create actually saved) — separate change, needs a SANDBOX test on masedet
- Remote test runner (run DevSandbox jobs on masedet without logging in) — claude-wsl owns it in hagaybar/masedet-ws-ops#17; the draft plan sits untracked in `docs/dashboards/` here: commit it or delete it, Hagay's call
- Stale branches, all landed: `chore/almaapitk-0.7.0` (#56), `docs/prod-runbook-paths` (#60), `docs/slim-claude-md` (#58), `release/failed-folder` (#53) — delete, on Hagay's OK
- Track the prod batch file `batch/rs_forms_monitor_prod.bat` for parity with its sandbox sibling (runbook §7 TODO)
