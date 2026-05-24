/**
 * @process project/pii-leak-isolation
 * @description Implement the approved PII-leak-isolation plan (issue #4) via TDD agent tasks,
 *              a local test-suite quality gate, and a single owner breakpoint before pushing
 *              to the public main branch.
 * @inputs { planPath: string, specPath: string }
 * @outputs { success: boolean }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

const implInstructions = (planTask) => [
  `Open the plan at the provided planPath and implement ${planTask} EXACTLY as written, including the exact code blocks.`,
  'Follow the TDD steps in order: write the failing test, run it to confirm it fails, implement the minimal code, run it to confirm it passes.',
  'Run pytest with env ALMA_SB_API_KEY=dummy ALMA_PROD_API_KEY=dummy. NEVER make live Alma API calls.',
  'Do NOT modify the almaapitk package.',
  'Make the git commit(s) exactly as that plan task specifies (commit per task).',
  'Verify the change was actually applied (files written, tests green) before reporting.',
  'Return ONLY the JSON summary object described in outputFormat.',
];

const implOutputSchema = {
  type: 'object',
  required: ['summary'],
  properties: {
    summary: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    commit: { type: 'string' },
    allTestsPassed: { type: 'boolean' },
  },
};

export async function process(inputs, ctx) {
  const planPath = inputs.planPath;
  const specPath = inputs.specPath;
  const common = { planPath, specPath };

  // ---- Phase 1: implementation (no breakpoints; plan already approved) ----
  const r1 = await ctx.task(gitHygieneTask, common);
  const r2 = await ctx.task(loggingHelpersTask, common);
  const r3 = await ctx.task(piiRoutingTask, common);
  const r4 = await ctx.task(testUserRetrievalTask, common);

  // ---- Phase 2: local quality gate ----
  const verify = await ctx.task(verifySuiteTask, {});

  // ---- Phase 3: single owner gate before pushing to the PUBLIC repo ----
  await ctx.breakpoint({
    question:
      'All PII-isolation tasks are implemented and the local test suite was verified. ' +
      'Approve pushing these commits to the PUBLIC main branch?',
    title: 'Approve push to public main',
    options: ['Approve push', 'Hold'],
    expert: 'owner',
    tags: ['deploy-gate'],
    context: { runId: ctx.runId },
  });

  const push = await ctx.task(pushTask, {});

  return {
    success: true,
    tasks: { r1, r2, r3, r4, verify, push },
    metadata: { processId: 'project/pii-leak-isolation', timestamp: ctx.now() },
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

export const gitHygieneTask = defineTask('impl-git-hygiene', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Plan Task 1: .a5c boundary isolation (git hygiene)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'senior engineer working in the Alma RS lending automation repo',
      task: 'Implement Task 1: gitignore + untrack .a5c/runs & .a5c/cache, scrub hardcoded abs paths in the committed process file, then commit.',
      context: { ...args, planTask: 'Task 1' },
      instructions: implInstructions('Task 1'),
      outputFormat: 'JSON: { summary, filesChanged[], commit, allTestsPassed }',
    },
    outputSchema: implOutputSchema,
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['impl', 'git'],
}));

export const loggingHelpersTask = defineTask('impl-logging-helpers', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Plan Tasks 2 & 3: mask_user_id + PiiConsoleFilter (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'senior Python engineer',
      task: 'Implement Task 2 (mask_user_id) and Task 3 (PiiConsoleFilter + attach to console handler) with TDD, committing per task.',
      context: { ...args, planTask: 'Task 2 and Task 3' },
      instructions: implInstructions('Task 2 and Task 3'),
      outputFormat: 'JSON: { summary, filesChanged[], commit, allTestsPassed }',
    },
    outputSchema: implOutputSchema,
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['impl', 'logging', 'tdd'],
}));

export const piiRoutingTask = defineTask('impl-pii-routing', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Plan Task 4: _log_pii helper + route PII call sites to file-only (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'senior Python engineer',
      task: 'Implement Task 4: add _log_pii helper and edit the call sites (lines ~366, 384, 398/400/403, 500, 657) so patron PII goes to the file log only and IDs are masked on console. Use TDD; commit.',
      context: { ...args, planTask: 'Task 4' },
      instructions: implInstructions('Task 4'),
      outputFormat: 'JSON: { summary, filesChanged[], commit, allTestsPassed }',
    },
    outputSchema: implOutputSchema,
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['impl', 'logging', 'tdd'],
}));

export const testUserRetrievalTask = defineTask('impl-test-user-retrieval', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Plan Task 5: test_user_retrieval contact masking + --show-raw (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'senior Python engineer',
      task: 'Implement Task 5: refactor test_user_retrieval.py to extract format_user_report, mask contact fields by default, gate the raw JSON dump behind --show-raw. Use TDD; commit.',
      context: { ...args, planTask: 'Task 5' },
      instructions: implInstructions('Task 5'),
      outputFormat: 'JSON: { summary, filesChanged[], commit, allTestsPassed }',
    },
    outputSchema: implOutputSchema,
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['impl', 'diagnostic', 'tdd'],
}));

export const verifySuiteTask = defineTask('verify-suite', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Plan Task 6: full test suite (local quality gate)',
  description: 'Run the full pytest suite with dummy keys; no live API calls.',
  shell: {
    command:
      'ALMA_SB_API_KEY=dummy ALMA_PROD_API_KEY=dummy poetry run pytest tests/ -v -p no:cacheprovider',
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['verify', 'tests'],
}));

export const pushTask = defineTask('push-main', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Push commits to public main',
  description: 'git push origin main (after owner approval).',
  shell: { command: 'git push origin main' },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['push', 'git'],
}));
