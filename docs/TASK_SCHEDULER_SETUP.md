# Task Scheduler Setup Guide

Deploy the RS Forms Processor as a Windows Task Scheduler job that runs every minute in single-run mode, replacing the legacy watch-mode batch file.

---

## 1. Prerequisites

| Requirement | How to verify |
|-------------|---------------|
| Python 3.12+ installed and in PATH | `python --version` in cmd |
| Poetry installed and in PATH | `poetry --version` in cmd |
| Repository cloned to `D:\Scripts\Alma-RS-lending-request-automation` | Directory exists with `pyproject.toml` |
| Dependencies installed | Run `poetry install` in the repo root |
| Production config created | `config\rs_forms_config_prod.json` exists (not tracked by git) |

---

## 2. Environment Variables

### Why System-level?

Task Scheduler can run tasks under the SYSTEM account or a service account that does **not** load User-level environment variables. If `ALMA_PROD_API_KEY` is set only at the User level, the scheduled task will fail with a missing API key error.

### Setting the variable

1. Open **System Properties** (Win+Pause, or `sysdm.cpl`).
2. Click **Environment Variables**.
3. Under **System variables** (bottom pane), click **New**.
4. Variable name: `ALMA_PROD_API_KEY`
5. Variable value: *(your production API key)*
6. Click OK through all dialogs.
7. **Reboot** (or at minimum restart the Task Scheduler service) so the new variable is picked up.

### Verification

Open a **new** cmd window and run:

```
echo %ALMA_PROD_API_KEY%
```

It should print the key value, not `%ALMA_PROD_API_KEY%`.

---

## 3. Task Scheduler Configuration (Step by Step)

### 3.1 Open Task Scheduler

Run `taskschd.msc`, or search for "Task Scheduler" in the Start menu.

### 3.2 Create Task

In the right-hand **Actions** pane, click **Create Task** (not "Create Basic Task").

### 3.3 General tab

| Setting | Value |
|---------|-------|
| Name | `RS-Forms-Processor` |
| Description | Process incoming RS lending request TSV files from Power Automate |
| Security options | **Run whether user is logged on or not** |
| Privileges | Check **Run with highest privileges** |

### 3.4 Trigger tab

1. Click **New**.
2. Begin the task: **At startup**.
3. Under **Advanced settings**:
   - Check **Repeat task every**: `1 minute`
   - For a duration of: `Indefinitely`
   - Check **Enabled**
4. Click OK.

This causes the task to fire once at boot, then repeat every minute indefinitely.

### 3.5 Action tab

1. Click **New**.
2. Action: **Start a program**.
3. Program/script:

   ```
   D:\Scripts\Alma-RS-lending-request-automation\batch\rs_forms_scheduled.bat
   ```

4. Start in (optional):

   ```
   D:\Scripts\Alma-RS-lending-request-automation
   ```

5. Click OK.

### 3.6 Conditions tab

| Setting | Value |
|---------|-------|
| Start only if the computer is on AC power | **Unchecked** |
| Wake the computer to run this task | Leave unchecked (machine is always on) |

### 3.7 Settings tab

| Setting | Value |
|---------|-------|
| Allow task to be run on demand | Checked |
| If the task fails, restart every | `1 minute`, up to `3` additional attempts |
| Stop the task if it runs longer than | `3 days` (safety net) |
| If the running task does not end when requested, force it to stop | Checked |
| If the task is already running, then the following rule applies | **Do not start a new instance** |

The "Do not start a new instance" setting works alongside the application-level lock file (`output/.processor.lock`) to provide two layers of overlap protection.

### 3.8 Save

Click OK. You will be prompted for the account password (the account under which the task runs). Enter it and click OK.

---

## 4. Verification

After the task has been running for a few minutes, verify each output channel.

### 4.1 Daily run log (heartbeat)

```
output\logs\runs_{YYYYMMDD}.log
```

Each invocation appends a one-line entry regardless of whether files were found:

```
2026-03-19 14:05:02 | files_found=0 | files_processed=0 | status=success | duration=0.3s
2026-03-19 14:06:01 | files_found=1 | files_processed=1 | status=success | duration=2.1s
```

If this file is empty or missing, the task is not running.

### 4.2 Daily processed report

```
output\reports\processed_{YYYYMMDD}.csv
```

A CSV with one row per successfully processed file. Contains columns: Timestamp, Filename, Partner_Code, Identifier_Type, Identifier, Title, Status, Request_ID, External_ID, Error_Message.

This file is only created when at least one TSV file is processed that day.

### 4.3 Per-file processing logs

```
output\file_logs\{YYYYMMDD_HHMMSS}_{original_filename}.log
```

One file per processed TSV, containing the full processing trace: identifier detection, metadata fetch, user lookup, lending request creation, and file move result.

### 4.4 General application log

```
output\logs\processor.log
```

Rotating daily log (30-day retention) with full DEBUG-level output from every run. This is the primary log for diagnosing processing errors.

### 4.5 Heartbeat checks log

```
output\logs\heartbeat_checks.log
```

Rotating log (10-day retention) recording every folder scan. Useful for confirming the processor is checking the input folder at the expected frequency.

---

## 5. Troubleshooting

### Stale lock file

**Symptom:** Every run logs "Exiting due to active lock from another instance" but no other instance is running.

**Cause:** A previous run crashed or was killed before releasing the lock.

**Fix:** Delete `output\.processor.lock`. The processor includes automatic stale-lock detection (it checks whether the PID in the lock file is still alive), but if the machine was rebooted and the PID was reused by a different process, manual deletion may be needed.

### Environment variable not visible

**Symptom:** The processor fails with an API key error.

**Cause:** `ALMA_PROD_API_KEY` is set at the User level, not the System level.

**Fix:** Move the variable to System variables (see Section 2). Reboot or restart the Task Scheduler service.

### Poetry not found

**Symptom:** The batch file fails with `'poetry' is not recognized`.

**Cause:** Poetry's installation directory is not in the System PATH.

**Fix:** Either:
- Add Poetry to the System PATH (e.g., `C:\Users\<user>\AppData\Roaming\Python\Scripts` or wherever Poetry is installed), or
- Edit `batch\rs_forms_scheduled.bat` to use the full path to `poetry.exe`.

### No heartbeat entries in run log

**Symptom:** `output\logs\runs_{YYYYMMDD}.log` does not exist or has no recent entries.

**Fix:**
1. Open Task Scheduler and check the task's **Last Run Result** and **Last Run Time**.
2. Right-click the task and select **Run** to trigger it manually.
3. Check the **History** tab for error codes.
4. Verify the batch file path in the Action tab is correct.

### Task runs but processes no files

**Symptom:** Heartbeat shows `files_found=0` even though TSV files are in the input folder.

**Fix:**
1. Verify the `input_path` in `config\rs_forms_config_prod.json` points to the correct folder.
2. Confirm files have a `.tsv` extension (case-sensitive on some configurations).
3. Check that files are not locked by another process (e.g., antivirus scanning).

---

## 6. Rollback to Watch Mode

If you need to revert to the legacy continuous-monitoring mode:

1. **Disable** (do not delete) the `RS-Forms-Processor` task in Task Scheduler.
2. Open a command prompt or terminal on the machine.
3. Run the watch-mode batch file:

   ```
   D:\Scripts\Alma-RS-lending-request-automation\batch\rs_forms_monitor_sandbox.bat
   ```

   For production, create or use an equivalent production watch-mode batch file that points to the production config.

4. The watch-mode process will run continuously in the foreground until stopped with Ctrl+C.

**Note:** When switching back to the scheduled task later, stop the watch-mode process first to avoid two instances processing the same files.

---

## 7. Output Structure Reference

All output is written under the `output/` directory relative to the repository root.

| Channel | Path | Frequency | Purpose |
|---------|------|-----------|---------|
| Per-file log | `output/file_logs/{timestamp}_{filename}.log` | One per processed TSV file | Detailed processing trace for a single submission |
| Daily report | `output/reports/processed_{YYYYMMDD}.csv` | Appended per processed file, one file per day | Tabular summary of all files processed that day |
| Daily run log | `output/logs/runs_{YYYYMMDD}.log` | Appended every run (every minute), one file per day | Heartbeat confirming the scheduler is firing |
| Application log | `output/logs/processor.log` | Continuous (daily rotation, 30-day retention) | Full DEBUG-level operational log |
| Heartbeat log | `output/logs/heartbeat_checks.log` | Continuous (daily rotation, 10-day retention) | Folder-scan activity log |
| Lock file | `output/.processor.lock` | Created at run start, deleted at run end | Prevents overlapping executions |

### Directory tree

```
output/
  .processor.lock              (transient, only exists during a run)
  file_logs/
    20260319_140601_submission.log
    20260319_140705_submission.log
  logs/
    processor.log              (current day, rotated daily)
    processor.log.2026-03-18   (previous days, up to 30)
    heartbeat_checks.log       (current day, rotated daily)
    runs_20260319.log
  reports/
    processed_20260319.csv
```
