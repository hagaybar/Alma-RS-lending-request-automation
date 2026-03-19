# Task Scheduler Migration Process

## Goal
Migrate the folder-monitoring script from continuous watch mode to Windows Task Scheduler single-run invocations, with a redesigned output structure.

## 7 Phases

| Phase | Type | Description |
|-------|------|-------------|
| 1. Analyze Code | Agent | Read current codebase, plan exact changes needed |
| 2. Lock File | Agent | Add `_acquire_lock()` / `_release_lock()` to prevent overlapping runs |
| 3. Output Structure | Agent | Implement 3 output channels (see below) |
| 4. Batch Files | Agent | Create `rs_forms_scheduled.bat` (prod) and sandbox variant |
| 5. Run Tests | Shell | `poetry run pytest -v` — verify no regressions |
| 6. Quality Check | Agent | Review all changes against plan, score 0-100 |
| 7. Docs | Agent | Create `TASK_SCHEDULER_SETUP.md`, update `CLAUDE.md` |

## New Output Structure (3 Channels)

| Channel | Path | Content |
|---------|------|---------|
| **Per-file log** | `output/file_logs/{YYYYMMDD}_{HHMMSS}_{filename}.log` | Detailed step-by-step processing of each TSV file |
| **Daily processed report** | `output/reports/processed_{YYYYMMDD}.csv` | One line per file processed (timestamp, partner, identifier, title, status, request ID) |
| **Daily run log** | `output/logs/runs_{YYYYMMDD}.log` | One line per invocation — heartbeat showing script ran, files found, result |

Plus a general application log (`output/logs/processor.log`) with daily rotation.

## Breakpoints
- **1 breakpoint** after Phase 6 (quality verification) — human review before generating deployment docs

## Key Changes to `resource_sharing_forms_processor.py`
- New methods: `_acquire_lock()`, `_release_lock()`, `_write_file_processing_log()`, `_append_daily_report()`, `_write_run_log_entry()`
- Modified: `process_single_run()` (lock acquire/release in try/finally, run log entry)
- Modified: `process_tsv_file()` (per-file log output)
- Modified: `setup_logging()` (daily rotation for scheduled mode)
- Modified: `__init__()` (new `scheduled_mode` parameter)
- Modified: `main()` (pass `scheduled_mode` to constructor)

## New Files
- `batch/rs_forms_scheduled.bat` — Production Task Scheduler batch file
- `batch/rs_forms_scheduled_sandbox.bat` — Sandbox testing batch file
- `docs/TASK_SCHEDULER_SETUP.md` — Deployment guide
