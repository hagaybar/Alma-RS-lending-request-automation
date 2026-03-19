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
- `config/` — JSON config files (example checked in, prod/sandbox gitignored)
- `batch/` — Windows batch files for launching
- `input/` — Watched folder for incoming TSV files from Power Automate
- `processed/` — Completed files moved here with timestamp prefix
- `output/logs/` — Processor and heartbeat logs
- `output/reports/` — CSV processing reports

## Key Patterns

- **Dry-run by default**: Must pass `--live` explicitly to make API calls
- **Single file architecture**: All processor logic in one file (~1100 lines)
- **Identifier auto-detection**: PMID (6-9 digits) vs DOI (starts with 10.) — ignores user-provided type
- **Error isolation**: One file's error never stops the batch; errors logged, processing continues
- **File-as-state**: Files in `input/` = pending, files in `processed/` = done (timestamp-prefixed)

## Environment

- Python 3.12+, managed via Poetry
- `ALMA_SB_API_KEY` — Required for SANDBOX environment
- `ALMA_PROD_API_KEY` — Required for PRODUCTION environment
- Depends on `almaapitk` (git dependency, pinned to v0.2.2)

## Deployment

- Runs on a **remote physical Windows machine** (not WSL/cloud)
- **Production mode**: Windows Task Scheduler fires `batch/rs_forms_scheduled.bat` every 1 minute in single-run mode (`--live` without `--watch`)
- **Lock file**: `output/.processor.lock` prevents overlapping executions; includes PID-based stale-lock detection
- **Three scheduled-mode output channels**:
  - Per-file log (`output/file_logs/`) — detailed trace for each processed TSV
  - Daily CSV report (`output/reports/processed_{YYYYMMDD}.csv`) — tabular summary
  - Daily run log (`output/logs/runs_{YYYYMMDD}.log`) — heartbeat confirming every invocation
- **Batch files**: `batch/rs_forms_scheduled.bat` (production) and `batch/rs_forms_scheduled_sandbox.bat` (testing)
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
