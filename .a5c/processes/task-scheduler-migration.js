/**
 * @process task-scheduler-migration
 * @description Migrate Python folder-monitoring script from continuous watch mode to
 * Windows Task Scheduler single-run invocations. Adds lock file mechanism, updates
 * logging for repeated invocations, creates scheduled batch file, and verifies tests.
 * @inputs { projectName: string, mainScript: string, targetQuality: number }
 * @outputs { success: boolean, changesApplied: array, testResults: object, artifacts: array }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectName = 'Alma RS Lending Request Automation',
    mainScript = 'resource_sharing_forms_processor.py',
    targetQuality = 85
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', `Starting Task Scheduler migration for ${projectName}`);

  // ============================================================================
  // PHASE 1: ANALYZE CURRENT CODE & PLAN CHANGES
  // ============================================================================

  ctx.log('info', 'Phase 1: Analyzing current code and planning changes');
  const analysisResult = await ctx.task(analyzeCodeTask, {
    projectName,
    mainScript
  });

  artifacts.push('analysis-report');

  // ============================================================================
  // PHASE 2: IMPLEMENT LOCK FILE MECHANISM
  // ============================================================================

  ctx.log('info', 'Phase 2: Implementing lock file mechanism');
  const lockFileResult = await ctx.task(implementLockFileTask, {
    projectName,
    mainScript,
    analysis: analysisResult
  });

  artifacts.push('lock-file-implementation');

  // ============================================================================
  // PHASE 3: UPDATE LOGGING FOR SCHEDULED MODE
  // ============================================================================

  ctx.log('info', 'Phase 3: Implementing new output structure');
  const loggingResult = await ctx.task(updateLoggingTask, {
    projectName,
    mainScript,
    analysis: analysisResult,
    outputRequirements: {
      perFileLog: 'A single detailed log file per TSV file processed, documenting all steps performed',
      dailyProcessedReport: 'A daily CSV report with one line per file processed, crucial info columns, appended throughout the day',
      dailyRunLog: 'A daily heartbeat log with one line per script invocation (ran, files found count, result)'
    }
  });

  artifacts.push('output-structure-update');

  // ============================================================================
  // PHASE 4: CREATE SCHEDULED BATCH FILE
  // ============================================================================

  ctx.log('info', 'Phase 4: Creating Windows batch file for scheduled mode');
  const batchFileResult = await ctx.task(createBatchFileTask, {
    projectName,
    analysis: analysisResult
  });

  artifacts.push('scheduled-batch-file');

  // ============================================================================
  // PHASE 5: RUN TESTS
  // ============================================================================

  ctx.log('info', 'Phase 5: Running test suite');
  const testResult = await ctx.task(runTestsTask, {
    projectName
  });

  // ============================================================================
  // PHASE 6: QUALITY VERIFICATION
  // ============================================================================

  ctx.log('info', 'Phase 6: Verifying implementation quality');
  const qualityResult = await ctx.task(qualityVerificationTask, {
    projectName,
    mainScript,
    lockFileResult,
    loggingResult,
    batchFileResult,
    testResult,
    targetQuality
  });

  // Breakpoint: Review all changes before finalizing
  await ctx.breakpoint({
    question: `Migration implementation complete. Quality score: ${qualityResult.score || 'pending'}. Test results: ${testResult.allPassed ? 'ALL PASSED' : 'FAILURES DETECTED'}. Review changes and approve?`,
    title: 'Task Scheduler Migration Review',
    context: {
      runId: ctx.runId,
      projectName,
      changesApplied: [
        'Lock file mechanism in process_single_run()',
        'Daily rotating log handler for single-run mode',
        'New batch/rs_forms_scheduled.bat',
      ],
      testResults: testResult,
      qualityScore: qualityResult
    }
  });

  // ============================================================================
  // PHASE 7: GENERATE DEPLOYMENT DOCUMENTATION
  // ============================================================================

  ctx.log('info', 'Phase 7: Generating Task Scheduler setup documentation');
  const docsResult = await ctx.task(generateDocsTask, {
    projectName,
    lockFileResult,
    loggingResult,
    batchFileResult
  });

  artifacts.push('deployment-docs');

  const endTime = ctx.now();

  return {
    success: true,
    projectName,
    changesApplied: [
      lockFileResult,
      loggingResult,
      batchFileResult,
      docsResult
    ],
    testResults: testResult,
    qualityScore: qualityResult,
    artifacts,
    duration: endTime - startTime,
    metadata: {
      processId: 'task-scheduler-migration',
      timestamp: startTime
    }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

export const analyzeCodeTask = defineTask('analyze-code', (args, taskCtx) => ({
  kind: 'agent',
  title: `Phase 1: Analyze current code - ${args.projectName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer and systems architect',
      task: `Analyze the current architecture of ${args.mainScript} in the project root. Focus on:
1. The process_watch_mode() method - understand the polling loop, signal handling, and processed_files tracking
2. The process_single_run() method - understand the existing single-run mode
3. The setup_logging() and setup_heartbeat_logger() methods
4. The main() function CLI argument parsing
5. The __init__() constructor - how config is loaded and clients initialized
6. The find_pending_tsv_files() method - how files are discovered
7. How files are moved to processed/ folder after processing

Produce a structured analysis of what needs to change for Task Scheduler migration:
- Lock file: where to add it in process_single_run(), what path to use, PID-based stale lock detection
- Logging: how to switch from per-invocation log files to daily rotating handler for single-run mode
- Batch file: what the new scheduled batch file should contain (no --watch, no pause, full paths)

Read the actual code files. Do NOT just describe what you think they contain.`,
      context: {
        projectName: args.projectName,
        mainScript: args.mainScript,
        projectRoot: '/home/hagaybar/projects/Alma-RS-lending-request-automation'
      },
      instructions: [
        'Read resource_sharing_forms_processor.py thoroughly',
        'Read batch/rs_forms_monitor_sandbox.bat',
        'Read config/rs_forms_config.example.json',
        'Analyze the watch mode vs single-run mode differences',
        'Identify exact line numbers and methods that need modification',
        'Document the lock file strategy (path, PID tracking, stale detection)',
        'Document the logging changes needed',
        'Document the batch file contents',
        'Return a structured analysis report'
      ],
      outputFormat: 'JSON with lockFileStrategy, loggingChanges, batchFileSpec, affectedMethods, riskAssessment'
    },
    outputSchema: {
      type: 'object',
      required: ['lockFileStrategy', 'loggingChanges', 'batchFileSpec', 'affectedMethods'],
      properties: {
        lockFileStrategy: { type: 'object' },
        loggingChanges: { type: 'object' },
        batchFileSpec: { type: 'object' },
        affectedMethods: { type: 'array', items: { type: 'string' } },
        riskAssessment: { type: 'array', items: { type: 'object' } }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['analysis', 'planning']
}));

export const implementLockFileTask = defineTask('implement-lock-file', (args, taskCtx) => ({
  kind: 'agent',
  title: `Phase 2: Implement lock file mechanism - ${args.projectName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer',
      task: `Add a file-based lock mechanism to resource_sharing_forms_processor.py to prevent overlapping executions when run from Windows Task Scheduler.

REQUIREMENTS:
1. Add a _acquire_lock() method to ResourceSharingFormsProcessor class that:
   - Creates a .lock file in the output directory (self.output_dir / '.processor.lock')
   - Writes the current PID and timestamp to it as JSON
   - Before creating: checks if lock file exists, reads PID, checks if process is still alive
   - If lock exists and process alive: log warning and return False
   - If lock exists but process dead (stale lock): log info, remove stale lock, proceed
   - If no lock: create it and return True

2. Add a _release_lock() method that removes the lock file

3. Modify process_single_run() to:
   - Call _acquire_lock() at the start, return early if False
   - Call _release_lock() in a finally block at the end

4. Use os.getpid() for PID, and for stale lock detection on Windows, try to check if the PID exists using os.kill(pid, 0) with a try/except (works cross-platform)

5. Import any needed modules (os if not already imported)

IMPORTANT: Read the current file first, then make targeted edits. Do NOT rewrite the entire file. Preserve all existing functionality.`,
      context: {
        projectRoot: '/home/hagaybar/projects/Alma-RS-lending-request-automation',
        mainScript: args.mainScript,
        analysis: args.analysis
      },
      instructions: [
        'Read resource_sharing_forms_processor.py first',
        'Add os to imports if not present',
        'Add _acquire_lock() method to the class',
        'Add _release_lock() method to the class',
        'Modify process_single_run() to use the lock',
        'Run poetry run pytest to verify tests still pass',
        'Return summary of changes made'
      ],
      outputFormat: 'JSON with filesModified, methodsAdded, methodsModified, summary'
    },
    outputSchema: {
      type: 'object',
      required: ['filesModified', 'summary'],
      properties: {
        filesModified: { type: 'array', items: { type: 'string' } },
        methodsAdded: { type: 'array', items: { type: 'string' } },
        methodsModified: { type: 'array', items: { type: 'string' } },
        summary: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['implementation', 'lock-file', 'critical']
}));

export const updateLoggingTask = defineTask('update-logging', (args, taskCtx) => ({
  kind: 'agent',
  title: `Phase 3: Implement new output structure - ${args.projectName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer',
      task: `Redesign the output/logging/reporting structure in resource_sharing_forms_processor.py to support 3 distinct output channels for Task Scheduler mode. Read the current code first.

THREE OUTPUT CHANNELS REQUIRED:

1. PER-FILE PROCESSING LOG (new):
   - One detailed log file per TSV file processed
   - Path: output/file_logs/{YYYYMMDD}_{HHMMSS}_{original_filename}.log
   - Content: every step performed for that file — identifier detection result, metadata fetch result (title, authors, journal), user lookup result, lending request creation result (request ID, external ID), move-to-processed result
   - Written during process_tsv_file() — create a file-specific logger or write directly
   - This gives a complete audit trail for each individual request

2. DAILY PROCESSED REPORT (replaces per-session CSV):
   - One CSV file per day, appended to throughout the day
   - Path: output/reports/processed_{YYYYMMDD}.csv
   - One line per file processed with crucial columns: Timestamp, Filename, Partner_Code, Identifier_Type, Identifier, Title, Status, Request_ID, External_ID, Error_Message
   - If file doesn't exist yet for today: create with header row
   - If exists: append without header
   - This replaces the current per-invocation processing_report_{timestamp}.csv

3. DAILY RUN LOG (heartbeat, replaces current heartbeat logger):
   - One log file per day, appended to
   - Path: output/logs/runs_{YYYYMMDD}.log
   - One line per script invocation: timestamp, files_found_count, files_processed_count, status (success/error), duration_seconds
   - Written at the END of process_single_run() or in run() method
   - Even if 0 files found, log that the run happened (heartbeat)
   - Use simple file append, not the logging module

ALSO:
- Keep a general application log using TimedRotatingFileHandler (daily, 30 days) for DEBUG-level operational logs
  - Path: output/logs/processor.log (daily rotation)
  - This replaces the per-invocation processor_{timestamp}.log for scheduled mode
- For watch mode: keep all current behavior unchanged (backward compatible)
- Add a scheduled_mode parameter to __init__ (default False), store as self.scheduled_mode
- In main(), set scheduled_mode=True when --watch is NOT passed

IMPORTANT: Read the current file first. Make targeted edits. Do NOT rewrite the entire file. Preserve all existing watch mode behavior.`,
      context: {
        projectRoot: '/home/hagaybar/projects/Alma-RS-lending-request-automation',
        mainScript: args.mainScript,
        analysis: args.analysis,
        outputRequirements: args.outputRequirements
      },
      instructions: [
        'Read resource_sharing_forms_processor.py first thoroughly',
        'Add scheduled_mode parameter to __init__',
        'Create a method _write_file_processing_log() for per-file logs',
        'Modify process_tsv_file() to call _write_file_processing_log() at the end',
        'Create a method _append_daily_report() that writes/appends to daily CSV',
        'Modify generate_csv_report() or process_single_run() to use _append_daily_report()',
        'Create a method _write_run_log_entry() for daily run heartbeat',
        'Call _write_run_log_entry() at end of process_single_run()',
        'Modify setup_logging() to use TimedRotatingFileHandler for scheduled mode',
        'Modify main() to pass scheduled_mode when --watch is not used',
        'Ensure output/file_logs/ directory is created',
        'Preserve all existing logging behavior for watch mode',
        'Return summary of all changes made'
      ],
      outputFormat: 'JSON with filesModified, methodsAdded, methodsModified, summary'
    },
    outputSchema: {
      type: 'object',
      required: ['filesModified', 'summary'],
      properties: {
        filesModified: { type: 'array', items: { type: 'string' } },
        methodsAdded: { type: 'array', items: { type: 'string' } },
        methodsModified: { type: 'array', items: { type: 'string' } },
        summary: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['implementation', 'logging', 'output-structure']
}));

export const createBatchFileTask = defineTask('create-batch-file', (args, taskCtx) => ({
  kind: 'agent',
  title: `Phase 4: Create scheduled batch file - ${args.projectName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Windows systems administrator and Python developer',
      task: `Create a new Windows batch file at batch/rs_forms_scheduled.bat for running the processor via Windows Task Scheduler.

REQUIREMENTS:
1. No @echo off with TITLE (keep it clean for scheduled/headless execution)
2. cd /d to the production directory (use D:\\Scripts\\Alma-RS-lending-request-automation as the production path, matching the pattern from the existing sandbox batch file)
3. Run: poetry run python resource_sharing_forms_processor.py --config config\\rs_forms_config_prod.json --live
4. NO --watch flag (single-run mode)
5. NO pause at the end (runs headless)
6. Exit with the script's exit code (exit /b %ERRORLEVEL%)
7. Add a comment header explaining this is for Task Scheduler use

Also create batch/rs_forms_scheduled_sandbox.bat with the same structure but pointing to the sandbox config and DevSandbox path for testing.

IMPORTANT: Read the existing batch/rs_forms_monitor_sandbox.bat first to understand the current pattern.`,
      context: {
        projectRoot: '/home/hagaybar/projects/Alma-RS-lending-request-automation',
        analysis: args.analysis
      },
      instructions: [
        'Read the existing batch/rs_forms_monitor_sandbox.bat',
        'Create batch/rs_forms_scheduled.bat for production Task Scheduler use',
        'Create batch/rs_forms_scheduled_sandbox.bat for sandbox testing',
        'Return summary of files created'
      ],
      outputFormat: 'JSON with filesCreated, summary'
    },
    outputSchema: {
      type: 'object',
      required: ['filesCreated', 'summary'],
      properties: {
        filesCreated: { type: 'array', items: { type: 'string' } },
        summary: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['implementation', 'batch-file', 'deployment']
}));

export const runTestsTask = defineTask('run-tests', (args, taskCtx) => ({
  kind: 'shell',
  title: `Phase 5: Run test suite - ${args.projectName}`,
  shell: {
    command: 'cd /home/hagaybar/projects/Alma-RS-lending-request-automation && poetry run pytest -v 2>&1'
  },
  labels: ['testing', 'verification']
}));

export const qualityVerificationTask = defineTask('quality-verification', (args, taskCtx) => ({
  kind: 'agent',
  title: `Phase 6: Quality verification - ${args.projectName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior QA engineer and code reviewer',
      task: `Review all changes made to resource_sharing_forms_processor.py and the new batch files against the original migration plan. Verify:

1. LOCK FILE MECHANISM:
   - _acquire_lock() exists and correctly writes PID + timestamp
   - _release_lock() exists and removes the lock file
   - process_single_run() uses try/finally with lock acquire/release
   - Stale lock detection works (checks if PID is alive)
   - Lock file path is in output directory

2. OUTPUT STRUCTURE (3 channels):
   a. Per-file processing log: _write_file_processing_log() exists, writes to output/file_logs/
   b. Daily processed report: _append_daily_report() exists, writes/appends to output/reports/processed_{YYYYMMDD}.csv
   c. Daily run log (heartbeat): _write_run_log_entry() exists, writes to output/logs/runs_{YYYYMMDD}.log
   - General app log uses TimedRotatingFileHandler for scheduled mode
   - Watch mode still uses original logging behavior

3. BATCH FILES:
   - batch/rs_forms_scheduled.bat exists with correct content (no --watch, no pause)
   - batch/rs_forms_scheduled_sandbox.bat exists for testing

4. NO REGRESSIONS:
   - Watch mode still works (--watch flag behavior unchanged)
   - Single-run mode still processes files correctly
   - All existing tests pass
   - No imports removed or broken
   - dry-run default behavior preserved

Score the implementation quality 0-100 based on completeness, correctness, and adherence to the plan.`,
      context: {
        projectRoot: '/home/hagaybar/projects/Alma-RS-lending-request-automation',
        mainScript: args.mainScript,
        testResult: args.testResult,
        targetQuality: args.targetQuality
      },
      instructions: [
        'Read resource_sharing_forms_processor.py and verify all changes',
        'Read batch/rs_forms_scheduled.bat and batch/rs_forms_scheduled_sandbox.bat',
        'Check that existing tests pass (review test output)',
        'Score quality 0-100',
        'List any issues found',
        'List any recommendations'
      ],
      outputFormat: 'JSON with score, issues, recommendations, checksPassedCount, checksTotalCount, summary'
    },
    outputSchema: {
      type: 'object',
      required: ['score', 'summary'],
      properties: {
        score: { type: 'number', minimum: 0, maximum: 100 },
        issues: { type: 'array', items: { type: 'string' } },
        recommendations: { type: 'array', items: { type: 'string' } },
        checksPassedCount: { type: 'number' },
        checksTotalCount: { type: 'number' },
        summary: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['quality', 'verification', 'review']
}));

export const generateDocsTask = defineTask('generate-docs', (args, taskCtx) => ({
  kind: 'agent',
  title: `Phase 7: Generate deployment docs - ${args.projectName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical writer and Windows systems administrator',
      task: `Create a deployment guide document at docs/TASK_SCHEDULER_SETUP.md with instructions for setting up Windows Task Scheduler for this script.

Include:
1. Prerequisites (Python, Poetry, environment variables)
2. Environment variable setup (ALMA_PROD_API_KEY must be system-level, not user-level)
3. Task Scheduler configuration step-by-step:
   - Task name: RS-Forms-Processor
   - Trigger: At system startup, repeat every 1 minute, indefinitely
   - Action: Start batch/rs_forms_scheduled.bat
   - Settings: "Do not start a new instance if already running"
   - Settings: "Run whether user is logged on or not"
   - Settings: "If task fails, restart every 1 minute, up to 3 attempts"
4. How to verify it's working (check logs, check processed folder)
5. Troubleshooting common issues (lock file stale, env vars missing, Poetry not in PATH)
6. How to switch back to watch mode if needed (rollback plan)
7. Update the CLAUDE.md file Deployment section to reflect that the migration is now implemented (not just planned)

IMPORTANT: Also update the project CLAUDE.md deployment section to reflect the new state.`,
      context: {
        projectRoot: '/home/hagaybar/projects/Alma-RS-lending-request-automation',
        lockFileResult: args.lockFileResult,
        loggingResult: args.loggingResult,
        batchFileResult: args.batchFileResult
      },
      instructions: [
        'Create docs/TASK_SCHEDULER_SETUP.md with comprehensive setup guide',
        'Update CLAUDE.md Deployment section to reflect implemented migration',
        'Return summary of files created/modified'
      ],
      outputFormat: 'JSON with filesCreated, filesModified, summary'
    },
    outputSchema: {
      type: 'object',
      required: ['filesCreated', 'summary'],
      properties: {
        filesCreated: { type: 'array', items: { type: 'string' } },
        filesModified: { type: 'array', items: { type: 'string' } },
        summary: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['documentation', 'deployment']
}));
