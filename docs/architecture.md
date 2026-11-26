# Architecture and repo quirks

Moved from CLAUDE.md on 2026-11-24 (#57): reference material, read when needed. CLAUDE.md keeps
only what every session needs.

## Other commands

```bash
# Smoke test (verify dependencies)
poetry run python scripts/smoke_project.py
# Live watch mode (continuous monitoring)
poetry run python resource_sharing_forms_processor.py --config config/rs_forms_config.json --watch --live
```

Python 3.12+, managed with Poetry; depends on `almaapitk` from PyPI (version floor in `pyproject.toml`).

## Folder map

- `resource_sharing_forms_processor.py` — Single-file processor (main entry point)
- `rs_requests/` — request builders: `base.py` (interface), `lending.py`, `borrowing.py`, `metadata.py`, `errors.py` (canonical exception home), `pii.py` (PII masking)
- `input_borrowing/` — watched folder for borrowing files from Power Automate (the not-held fork)
- `config/` — JSON config files (example checked in, prod/sandbox gitignored)
- `batch/` — Windows batch files for launching
- `input/` — Watched folder for incoming TSV files from Power Automate
- `processed/` — Completed files moved here under their original input filename (numeric suffix `name (1).ext` only on a name collision)
- `failed_files/` — Files that failed, moved here after their first attempt, same naming rule (`file_processing.failed_folder`; defaults to a sibling of `processed/`)
- `output/logs/` — Processor and heartbeat logs
- `output/reports/` — CSV processing reports

## How it works

- **Why one attempt per file** (rule in CLAUDE.md, GH #48): retrying every run wrote a log and CSV row per attempt and let a stuck backlog fire months later (2026-10-22).
- **Pipeline + builders split**: The scheduled pipeline (file I/O, dry-run/live dispatch, reporting) lives in `resource_sharing_forms_processor.py` (~1500 lines); the request build/submit step lives behind `rs_requests/` builders (`lending.py`, `borrowing.py`)
- **Identifier auto-detection**: PMID (6-9 digits) vs DOI (starts with 10.) — ignores user-provided type
- **Error isolation**: One file's error never stops the batch; errors logged, processing continues
- **File-as-state**: Files in `input/` = pending, files in `processed/` = done (kept under the original input filename so downstream automation can verify processing by matching the same name), files in `failed_files/` = failed
- **Two request kinds, one pipeline**: Power Automate forks on a holdings check — held → `input/` → lending; not held → `input_borrowing/` → borrowing. Only the terminal build/submit step differs.

## Deployment details

- Runs on a **remote physical Windows machine** (not WSL/cloud)
- **Production mode**: a Windows scheduled task on the production workstation runs the processor in single-run mode (`--live` without `--watch`), **every 5 minutes**. It fires `batch/rs_forms_monitor_prod.bat`, which is **local-only and gitignored — not in this repo** (standing TODO: track it for parity with its sandbox sibling)
- **DevSandbox (SANDBOX) task**: `RS SB Lending-Borrowing (on demand)` runs `batch/rs_forms_scheduled_dev_sb.bat`. Since 2026-11-25 it has **no schedule**: start it by hand when testing (`Start-ScheduledTask -TaskName "RS SB Lending-Borrowing (on demand)"`). It replaced the 5-minute "RS Lending-Borrowing Request Monitor"; a backup of the old definition is kept on the workstation
- **Lock file**: `output/.processor.lock` prevents overlapping executions; includes PID-based stale-lock detection
- **Three scheduled-mode output channels**:
  - Per-file log (`output/file_logs/`) — detailed trace for each processed TSV
  - Daily CSV report (`output/reports/processed_{YYYYMMDD}.csv`) — tabular summary
  - Daily run log (`output/logs/runs_{YYYYMMDD}.log`) — heartbeat confirming every invocation
- **Batch files** — both tracked ones `cd` to the DevSandbox clone and run SANDBOX:
  - `batch/rs_forms_scheduled_dev_sb.bat` — single run, `config\tests-config.json --live`, started by the on-demand task above
  - `batch/rs_forms_monitor_sandbox.bat` — legacy watch mode, `config\rs_forms_config.json --watch --live`
- **Rollback**: Disable the scheduled task and run `batch/rs_forms_monitor_sandbox.bat` for legacy watch mode
- Host setup, folder layout, post-deploy checks and rollback for the production workstation are kept in the owner's private documentation

## Repo quirks

- Config files with `_prod` or `_sandbox` in the name are gitignored
- The `processed_files` set in watch mode is in-memory only — restarting the process re-scans, but files already moved to `processed/` won't be re-processed
- TSV files have NO header row — 7 tab-separated columns in fixed order
- External ID includes timestamp to seconds, so reprocessing within the same second could collide
- A borrowing create can time out and still save. The file then goes to
  `failed_files/`, not back through the next run (GH #48); re-sending it by hand
  can create it twice. Alma's `402362` duplicate rejection only stops the repeat
  when the customer parameter `check_patron_duplicate_borrowing_requests=true`. **PRODUCTION was
  deliberately left unchanged at go-live (2026-10-22)**: duplicates are caught by
  monitoring `[BORROWING-UNCONFIRMED]` in the processor log instead (guidebook §8.3–8.4).
  Don't flip the parameter or treat it as a missing precondition
- **`401604` is not a bug and not rare.** Alma's *Self Ownership* check is
  title-level (matches Title / ISBN-ISSN / LCCN / System Control Number) and
  never consults coverage dates, while Power Automate's LibKey check is
  article-level. Both are right, and they disagree on every article in a
  journal we hold for other years — `docs/BORROWING_REQUESTS.md` §10. Since
  2026-09-03 the builder clears it: one retry with `override_blocks`, stamped
  into `note`, gated by `borrowing.override_self_ownership` (default true).
  The override is applied **only on that retry** — the same flag also clears
  genuine patron blocks, and only the self-ownership case was approved
- `lcc_number_template` is still unresolved (awaiting the RS librarians); config-driven, empty means omit.

Alma API quirks (`401604` self-ownership, `402362` duplicates, `owner` vs `pickup_location`,
`agree_to_copyright_terms`) live in the `alma-resource-sharing` skill; the evidence for borrowing
values is in [BORROWING_REQUESTS.md](BORROWING_REQUESTS.md).
