# masedet PROD Deployment & Dependency-Bump Runbook

**Purpose:** how this repo actually runs in production on the `masedet` Windows box, and the exact procedure for safely shipping a change — especially an `almaapitk` (or any dependency) bump — to prod. Captured 2026-06-02 from an operator interview + the live prod batch file, so future bumps don't have to reverse-engineer it.

> Scope note: this documents **observed reality** on masedet. Where it disagrees with `CLAUDE.md` / `docs/TASK_SCHEDULER_SETUP.md`, the discrepancies are listed in §7 — reconcile those separately. No real partner codes / user IDs / keys appear here (per repo hard rules).

---

## 1. masedet architecture (branch-isolated)

Two roots on the masedet box, one per branch — this is what keeps a clean dev environment separate from prod:

| Root | Branch | Role |
|---|---|---|
| `D:\Scripts\DevSandbox\<repo>\` | **main** | Dev/test. This is where the offline suite + SANDBOX smoke are run before promoting. |
| `D:\Scripts\Prod\<repo>\` | **prod** | Production. The scheduled job runs from here. |

For this repo: `D:\Scripts\DevSandbox\Alma-RS-lending-request-automation` (main) and `D:\Scripts\Prod\Alma-RS-lending-request-automation` (prod).

**Auto-deploy (PowerShell, config-driven):**
- Updates each repo **per branch** from GitHub: when a branch is updated on GitHub, the matching masedet folder is `git pull`-ed later (when configured and no errors).
- Handles Poetry: each branch has a flag (set **true** for this repo) that triggers `Run-PoetryInstall(repoDir, repoName, logFile)` — so a changed `poetry.lock` is installed into that checkout's venv automatically. **This is why a dependency bump actually lands on prod instead of silently no-op-ing.**

**Prod scheduled job:**
- Windows Task Scheduler, **every 5 minutes**, runs `D:\Scripts\Prod\Alma-RS-lending-request-automation\batch\rs_forms_monitor_prod.bat`.
- That batch (local-only — **gitignored**, not in the repo) does:
  ```bat
  cd /d D:\Scripts\Prod\Alma-RS-lending-request-automation
  .venv\Scripts\python.exe resource_sharing_forms_processor.py --config config\rs_forms_config.json --live
  ```
- **Runs the in-project `.venv` Python directly** (NOT `poetry run` — a comment in the batch notes `poetry run` "might hang Task Scheduler"). Consequence: the bump only takes effect once `Run-PoetryInstall` has refreshed `D:\Scripts\Prod\...\.venv`.
- CLI semantics (`resource_sharing_forms_processor.py:1442-1452`): `--live` (no `--watch`) ⇒ **live, single-run, `scheduled_mode=True`**. So each 5-min fire is one scan-and-exit, with the scheduled-mode output channels (per-file logs, daily CSV report, daily runs heartbeat) active. The batch's "WATCH MODE / every 60 seconds / Ctrl+C" banner text is **stale** and does not reflect behavior.
- Overlap protection: `output\.processor.lock` (PID-based stale-lock detection) prevents two runs colliding.

**Runs as:** the interactive `masedet` user.

**Environment / keys:** both `ALMA_PROD_API_KEY` and `ALMA_SB_API_KEY` are set for the `masedet` user. The prod config (`config\rs_forms_config.json`, local-only/gitignored) selects `environment=PRODUCTION`, so the prod job uses `ALMA_PROD_API_KEY`.

---

## 2. How a change reaches prod (the pipeline)

```
local dev (WSL)  --push-->  GitHub main  --auto-deploy-->  masedet DevSandbox\ (main)  [dev/test]
                                  |
                          (ff-merge main->prod, push)
                                  v
                            GitHub prod   --auto-deploy-->  masedet Prod\ (prod) + Run-PoetryInstall
                                                                   |
                                                          Task Scheduler (5 min) runs .venv python --live
```

Key implication: **merging to `prod` is the deploy.** Once `prod` is pushed, the auto-deploy pulls it into `D:\Scripts\Prod\...`, runs `poetry install`, and the next 5-min task fire runs the new code with the new deps.

---

## 3. Dependency-bump procedure (the reusable gate)

This is the checklist we ran for `almaapitk 0.4.5 → 0.4.6`; reuse it for every bump. It mirrors the `Fetch_Alma_Analytics_Reports` model (audit + L2 + L3) and the consumer-rollout gate (meta-issue #158).

1. **Audit** — write `docs/almaapitk-audit.md` (or `<dep>-audit.md`): per-file diff of the new version vs installed, restricted to this repo's surface; classify breaking vs additive vs improvement. Verdict SAFE/NOT.
2. **L2 offline mock/golden** (`tests/test_l2_citation_golden.py`) — pin this repo's own logic with the toolkit boundary mocked. No network. Must stay green across the bump.
3. **L3 opt-in live SANDBOX smoke** (`tests/test_live_smoke.py`) — `RUN_LIVE_SMOKE=1`, creates one real lending request in **SANDBOX**, no teardown, **hard-refuses PRODUCTION**. Test data in gitignored `tests/live_smoke_data.json` (template: `tests/live_smoke_data.example.json`).
4. **Bump the pin** in `pyproject.toml`; `poetry update <dep>`; commit `poetry.lock`.
5. **Local offline gate**: `poetry run pytest` → green.
6. **Push `main`** → auto-deploy updates `masedet DevSandbox\` (main) + `Run-PoetryInstall`.
7. **masedet offline gate** (in `D:\Scripts\DevSandbox\<repo>`): `poetry run pytest` → **17 passed, 1 skipped** expected. This is the gate required before prod (the "prod gated on masedet" rule). *Cross-platform notes baked into the suite for masedet: `--basetemp=.pytest_tmp` (locked `%TEMP%\pytest-of-<user>`), and UTF-8 file reads (cp1255 Hebrew locale).*
8. **masedet SANDBOX smoke** (in `DevSandbox\`): fill `tests/live_smoke_data.json` with SANDBOX values, `RUN_LIVE_SMOKE=1 poetry run pytest tests/test_live_smoke.py` → creates a real SB request. Verify in the Alma SB UI (Lending Requests, by External Identifier). **Never run a write test against PRODUCTION.**
9. **Promote**: ff-merge `main` → `prod`, push `origin/prod`.
10. **Auto-deploy lands prod**: confirm the auto-deploy pulled prod and ran `Run-PoetryInstall` (check its log).
11. **Post-deploy verification on prod** — §4.

---

## 4. Post-deploy verification on prod

After the prod auto-deploy completes, confirm the bump actually took effect (the prod job runs `.venv\Scripts\python.exe` directly, so the in-project venv must be updated):

```powershell
cd D:\Scripts\Prod\Alma-RS-lending-request-automation
.venv\Scripts\python.exe -c "import almaapitk; print(almaapitk.__version__)"   # expect the bumped version
```

Then confirm the scheduled job is healthy on its next 5-min fire:
- **Daily run heartbeat** `output\logs\runs_YYYYMMDD.log` — a new line every fire (proves the task is invoking).
- **Processor log** `output\logs\processor.log` — no new tracebacks; Alma connection OK.
- **Daily report** `output\reports\processed_YYYYMMDD.csv` — files processed as expected.
- **No stuck lock**: `output\.processor.lock` should not persist with a dead PID.

---

## 5. Rollback procedure (proposed — no procedure existed before)

The trap: a manual `git checkout`/reset on prod is **undone by the next auto-deploy pull**. Roll back *with* the auto-deploy, not against it.

Use the committed **`scripts/rollback.sh`** — a portable, branch-/path-agnostic helper that defaults to `git revert` (forward-fix; never rewrites history, so the auto-deploy pulls it cleanly). Run it under Git Bash on masedet (or on the dev box). It is self-contained — copy it into any repo's `scripts/`.

**Recommended (forward-fix, survives auto-deploy):**
1. **Stop the bleeding**: disable the Windows scheduled task (Task Scheduler → disable the 5-min RS task) so no further prod runs.
2. **Revert + publish + resync deps**, from a checkout of the affected branch (e.g. `D:\Scripts\Prod\...` on `prod`). Pick the last-good ref with `--list`, then:
   ```bash
   scripts/rollback.sh --list                       # choose the last-good <ref>
   scripts/rollback.sh --to <ref> --push --poetry   # revert to <ref>, push, poetry install
   ```
   The revert is a normal commit, so the auto-deploy pulls it cleanly and `Run-PoetryInstall` restores the prior deps (the `--poetry` flag also syncs the local checkout immediately).
3. **Verify** the reverted state is green (`poetry run pytest`) and `almaapitk.__version__` is the prior version.
4. **Re-enable** the scheduled task.

**Emergency stop (no GitHub round-trip):**
1. Disable the scheduled task.
2. Pause the auto-deploy for the prod branch (set its config flag false / stop the auto-deploy task) so it won't re-pull.
3. In `D:\Scripts\Prod\...`: `scripts/rollback.sh --to <last-good> --hard --poetry` (destructive local reset; does not force-push).
4. Re-enable the task. Resume auto-deploy only after `prod` on GitHub is fixed, or it will pull the bad state back.

---

## 6. Running the SANDBOX smoke from masedet

Run from the **DevSandbox (main)** checkout — it has the new code + bumped deps, and `ALMA_SB_API_KEY` is already set for the `masedet` user. Prod stays untouched.

```powershell
cd D:\Scripts\DevSandbox\Alma-RS-lending-request-automation
copy tests\live_smoke_data.example.json tests\live_smoke_data.json   # then edit with SANDBOX values
$env:RUN_LIVE_SMOKE = "1"
poetry run pytest tests/test_live_smoke.py -v -s
```
The smoke pins `environment="SANDBOX"`, never reads `ALMA_PROD_API_KEY`, does not retry the write (no duplicate creates), and leaves the request in place (SANDBOX is disposable). `tests/live_smoke_data.json` is gitignored — keep real values out of tracked files.

---

## 7. Known discrepancies / cleanup TODOs

- **Batch name**: docs (`CLAUDE.md`, `TASK_SCHEDULER_SETUP.md`) reference `rs_forms_scheduled.bat`; prod actually runs `rs_forms_monitor_prod.bat` (local-only/gitignored).
- **Cadence**: docs say every **1 minute**; actual scheduled task is every **5 minutes**.
- **Stale batch banner**: ✅ corrected by hand on the prod box (banner now reads "scheduled single-run"). The batch is still local-only/gitignored, so the fix isn't version-controlled — decide whether to track `rs_forms_monitor_prod.bat` for parity with the sandbox sibling (one-time untracked-file removal on masedet needed if so).
- **Rollback**: ✅ `scripts/rollback.sh` committed (see §5).
- **Verify once**: confirm `Run-PoetryInstall` targets the in-project `.venv` the prod batch executes (`poetry config virtualenvs.in-project` semantics on masedet).
</content>
