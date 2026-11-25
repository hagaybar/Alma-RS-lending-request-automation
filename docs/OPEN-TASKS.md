# Open tasks

Last updated: 2026-11-25

## Issues
- #54 (failure-mode audit: map the run context, then find unintended loops and side effects; filed in 13 repos 2026-11-10) — not started; can be done without outside input

## Other
- Adopt `reconcile=True` on Alma creates (almaapitk 0.7.0 is in prod since 2026-11-25; finds the request a timed-out create actually saved) — separate change, needs a SANDBOX test on masedet
- Remote test runner (run DevSandbox jobs on masedet without logging in) — claude-wsl owns it in hagaybar/masedet-ws-ops#17 and reads the draft plan from `docs/dashboards/masedet-remote-testing*` here (untracked, kept on purpose). Once claude-wsl no longer needs them, delete them — check with Hagay
- Track the prod batch file `batch/rs_forms_monitor_prod.bat` for parity with its sandbox sibling (runbook §7 TODO)
