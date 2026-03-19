# Task Scheduler Migration - Process Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  TASK SCHEDULER MIGRATION                     │
│            Watch Mode → Windows Task Scheduler               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 1: ANALYZE CURRENT CODE                               │
│  Agent reads resource_sharing_forms_processor.py             │
│  Outputs: lock file strategy, logging changes, batch spec    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 2: IMPLEMENT LOCK FILE MECHANISM                      │
│  Agent adds _acquire_lock(), _release_lock() methods         │
│  Modifies process_single_run() with try/finally lock         │
│  PID-based stale lock detection for crash recovery           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 3: UPDATE LOGGING FOR SCHEDULED MODE                  │
│  Agent switches single-run mode to TimedRotatingFileHandler  │
│  Daily rotation, 30-day retention                            │
│  Watch mode logging unchanged                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 4: CREATE SCHEDULED BATCH FILES                       │
│  Agent creates batch/rs_forms_scheduled.bat (prod)           │
│  Agent creates batch/rs_forms_scheduled_sandbox.bat          │
│  No --watch, no pause, exit with error code                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 5: RUN TESTS                                          │
│  Shell: poetry run pytest -v                                 │
│  Verify no regressions from changes                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 6: QUALITY VERIFICATION                               │
│  Agent reviews ALL changes against plan                      │
│  Scores implementation 0-100                                 │
│  Checks: lock file, logging, batch files, no regressions    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  ◆ BREAKPOINT: Human Review                                  │
│  Review changes, test results, quality score                 │
│  Approve or reject before generating docs                    │
└──────────────────────────┬───────────────────────────────────┘
                           │ (approved)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 7: GENERATE DEPLOYMENT DOCUMENTATION                  │
│  Agent creates docs/TASK_SCHEDULER_SETUP.md                  │
│  Updates CLAUDE.md deployment section                        │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
                      ✅ COMPLETE
```
