# Alma RS Lending Request Automation

Automated processing of Resource Sharing lending requests from Microsoft Forms (via Power Automate/SharePoint) to Alma ILS, with citation metadata enrichment from PubMed and Crossref.

## Commands

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Smoke test (verify dependencies)
poetry run python scripts/smoke_project.py

# Dry-run (validate only, no API calls — default)
poetry run python resource_sharing_forms_processor.py --config config/rs_forms_config.json

# Live single-run
poetry run python resource_sharing_forms_processor.py --config config/rs_forms_config.json --live

# Live watch mode (continuous monitoring)
poetry run python resource_sharing_forms_processor.py --config config/rs_forms_config.json --watch --live
```

## Architecture

- `resource_sharing_forms_processor.py` — Single-file processor (main entry point)
- `rs_requests/` — request builders: `base.py` (interface), `lending.py`, `borrowing.py`, `metadata.py`, `errors.py` (canonical exception home), `pii.py` (PII masking)
- `input_borrowing/` — watched folder for borrowing files from Power Automate (the not-held fork)
- `config/` — JSON config files (example checked in, prod/sandbox gitignored)
- `batch/` — Windows batch files for launching
- `input/` — Watched folder for incoming TSV files from Power Automate
- `processed/` — Completed files moved here under their original input filename (numeric suffix `name (1).ext` only on a name collision)
- `output/logs/` — Processor and heartbeat logs
- `output/reports/` — CSV processing reports

## Key Patterns

- **Dry-run by default**: Must pass `--live` explicitly to make API calls
- **Pipeline + builders split**: The scheduled pipeline (file I/O, dry-run/live dispatch, reporting) lives in `resource_sharing_forms_processor.py` (~1500 lines); the request build/submit step lives behind `rs_requests/` builders (`lending.py`, `borrowing.py`)
- **Identifier auto-detection**: PMID (6-9 digits) vs DOI (starts with 10.) — ignores user-provided type
- **Error isolation**: One file's error never stops the batch; errors logged, processing continues
- **File-as-state**: Files in `input/` = pending, files in `processed/` = done (kept under the original input filename so downstream automation can verify processing by matching the same name)
- **Two request kinds, one pipeline**: Power Automate forks on a holdings check — held → `input/` → lending; not held → `input_borrowing/` → borrowing. Only the terminal build/submit step differs.
- **`SHEB` is ambiguous**: a *partner code* on the lending path, a *proxy user code* on the borrowing path. Never move one between paths.
- **Borrowing field values are evidence-backed**: `docs/BORROWING_REQUESTS.md` derives them from 1912 real requests. Change a value there, with evidence, before changing it in code.

## Environment

- Python 3.12+, managed via Poetry
- `ALMA_SB_API_KEY` — Required for SANDBOX environment
- `ALMA_PROD_API_KEY` — Required for PRODUCTION environment
- Depends on `almaapitk` (PyPI, pinned `>=0.5.1` — floor ships `build_user_rs_request` + the `validate=` pre-flight, and the PubMed `MedlineDate` year fix borrowing needs; the 0.4.5 logging credential-leak fix is included)

## Deployment

- Runs on a **remote physical Windows machine** (not WSL/cloud)
- **Production mode**: Windows Task Scheduler on masedet runs the processor in single-run mode (`--live` without `--watch`). It fires `batch/rs_forms_monitor_prod.bat`, which is **local-only and gitignored — not in this repo**. Per [docs/masedet-prod-runbook.md](docs/masedet-prod-runbook.md) §7 the real cadence is **every 5 minutes**, not the 1 minute these docs used to claim; that section also carries the standing TODO to track the prod batch for parity with its sandbox sibling
- **Lock file**: `output/.processor.lock` prevents overlapping executions; includes PID-based stale-lock detection
- **Three scheduled-mode output channels**:
  - Per-file log (`output/file_logs/`) — detailed trace for each processed TSV
  - Daily CSV report (`output/reports/processed_{YYYYMMDD}.csv`) — tabular summary
  - Daily run log (`output/logs/runs_{YYYYMMDD}.log`) — heartbeat confirming every invocation
- **Batch files** — both tracked ones `cd` to `D:\Scripts\DevSandbox\` and run SANDBOX:
  - `batch/rs_forms_scheduled_dev_sb.bat` — scheduled single-run, `config\tests-config.json --live`
  - `batch/rs_forms_monitor_sandbox.bat` — legacy watch mode, `config\rs_forms_config.json --watch --live`
- **Rollback**: Disable the scheduled task and run `batch/rs_forms_monitor_sandbox.bat` for legacy watch mode
- See [docs/TASK_SCHEDULER_SETUP.md](docs/TASK_SCHEDULER_SETUP.md) for full setup instructions

## Branches

- `main` — Development branch (use for all coding)
- `prod` — Production branch. **Never commit or code directly on prod.** All changes reach prod only via merge from `main` (or from feature branches into `main` first).

## Gotchas

- Config files with `_prod` or `_sandbox` in the name are gitignored
- The `processed_files` set in watch mode is in-memory only — restarting the process re-scans, but files already moved to `processed/` won't be re-processed
- TSV files have NO header row — 7 tab-separated columns in fixed order
- External ID includes timestamp to seconds, so reprocessing within the same second could collide
- Borrowing `owner` is a plain string but `pickup_location` is wrapped `{"value": ...}` — the most common cause of a borrowing `BAD_REQUEST`
- `agree_to_copyright_terms` must be `true` — Alma rejects `false` at create (401897; settled 2026-07-30, guidebook §4.6). `lcc_number_template` is still unresolved (awaiting the RS librarians); config-driven, empty means omit
- A borrowing create can time out and still save — recovery is Alma's own `402362`
  duplicate rejection on the next run's re-POST (see the Decision record in Task 5),
  which depends on `check_patron_duplicate_borrowing_requests=true` in config
- **`401604` is not a bug and not rare.** Alma's *Self Ownership* check is
  title-level (matches Title / ISBN-ISSN / LCCN / System Control Number) and
  never consults coverage dates, while Power Automate's LibKey check is
  article-level. Both are right, and they disagree on every article in a
  journal we hold for other years — `docs/BORROWING_REQUESTS.md` §10. Since
  2026-09-03 the builder clears it: one retry with `override_blocks`, stamped
  into `note`, gated by `borrowing.override_self_ownership` (default true).
  The override is applied **only on that retry** — the same flag also clears
  genuine patron blocks, and only the self-ownership case was approved
