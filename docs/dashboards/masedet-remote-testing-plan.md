# masedet remote test runner: implementation plan

Draft 2026-11-25. Written by the sandbox agent in `Alma-RS-lending-request-automation` for the
agent that will build it. Overview page: [masedet-remote-testing.html](masedet-remote-testing.html).
Nothing is built yet.

## 1. Goal

Let a repo agent run real tests on masedet's **DevSandbox** clones and read the result, with
nobody logging in to masedet.

masedet is a physical Windows workstation, reachable only by remote desktop. It has no WSL, and
its firewall and access rules must not change. It already reaches out on its own in two ways:
a scheduled `git pull` from GitHub (`scripts_admin/auto_deploy.ps1` in `masedet-ws-ops`) and
OneDrive sync of the SharePoint library "masedet - Documents". This project uses only those two
channels. Nothing on masedet listens for incoming connections.

**Out of scope:** anything under `D:\Scripts\Prod\`, the `prod` branches, production Alma, and
running arbitrary commands.

## 2. The one design rule

**A request names a job from a fixed list. It never carries a command, a path or an argument.**

The commands live in a catalogue in `masedet-ws-ops`, which changes only through a pull request
the owner merges. Agents can write requests; they cannot change what a request is able to run.
Every other choice below follows from this.

## 3. Flow

```
agent sandbox                GitHub                    masedet                         SharePoint
─────────────                ──────                    ───────                         ──────────
tau-masedet run  ──push──►  masedet-jobs
                            requests/<id>.json  ◄─pull─ remote_jobs.ps1 (task, 5 min)
                                                        ├ validate against remote_jobs.json
                                                        ├ run job in D:\Scripts\DevSandbox\<repo>
                                                        ├ full log ──────────────────► _ops_shared\jobs\<id>\
tau-masedet wait ◄─fetch──  results/<id>.json   ◄─push─ └ summary
```

Expected round trip: 5 to 10 minutes.

## 4. Components

### 4.1 Requests repo: `masedet-jobs` (new, private)

```
requests/<id>.json     written by agents
results/<id>.json      written by masedet
README.md              what this repo is, and that nothing in it is executable
```

Request file:

```json
{
  "id": "20261125-141200-rs-pytest",
  "repo": "Alma-RS-lending-request-automation",
  "job": "pytest",
  "requested_by": "sandbox-agent",
  "requested_at": "2026-11-25T14:12:00+02:00"
}
```

- `id`: `[A-Za-z0-9-]{1,64}`, and it must equal the file name. Anything else is refused.
- Unknown fields are ignored. No field is ever passed to a shell.

### 4.2 Job catalogue: `masedet-ws-ops/config/remote_jobs.json`

```json
{
  "requests_clone": "D:\\_ops\\masedet-jobs",
  "shared_output_dir": "D:\\Tel-Aviv University\\masedet - Documents\\_ops_shared\\jobs",
  "log_file": "D:\\_ops\\logs\\remote_jobs.log",
  "lock_file": "D:\\_ops\\locks\\remote_jobs.lock",
  "max_request_age_minutes": 120,
  "allowed_root": "D:\\Scripts\\DevSandbox",
  "repos": {
    "Alma-RS-lending-request-automation": {
      "dir": "D:\\Scripts\\DevSandbox\\Alma-RS-lending-request-automation",
      "jobs": {
        "pytest": { "exe": ".venv\\Scripts\\python.exe", "args": ["-m", "pytest", "-q"],
                    "timeout_minutes": 10, "publish_tail_lines": 40 },
        "smoke":  { "exe": ".venv\\Scripts\\python.exe", "args": ["scripts\\smoke_project.py"],
                    "timeout_minutes": 5,  "publish_tail_lines": 20 }
      }
    }
  }
}
```

- `exe` + `args` as an array, started without a shell, so nothing is ever string-interpolated.
- `publish_tail_lines`: how many last lines of output may go into the GitHub summary. `0` means
  none. Set it above 0 only for jobs whose output is known to hold no personal data.
- The existing `status_collectors.json` already uses the `_ops_shared` folder; follow its style.
- Confirm the real DevSandbox folder names against `config/repos_to_deploy.json`.

### 4.3 Listener + executor: `masedet-ws-ops/scripts_admin/remote_jobs.ps1`

One script, one run per scheduled fire. Steps:

1. If `D:\_ops\remote_jobs.disabled` exists, log and exit (kill switch).
2. Take the lock. If a live lock exists, exit. Remove a stale one the way `auto_deploy.ps1` does.
3. `git pull` the `masedet-jobs` clone.
4. For each `requests/*.json` with no matching `results/<id>.json`, oldest first:
   - Parse and validate (id format, id equals file name, repo and job exist in the catalogue,
     resolved `dir` is under `allowed_root`).
   - If `requested_at` is older than `max_request_age_minutes`, write a result with status
     `expired` and do not run it.
   - If invalid, write a result with status `refused` and the reason.
   - Otherwise run the job (below) and write a result with status `passed`, `failed` or
     `timeout`.
5. Commit and push the new `results/*.json` files (phase 2; in phase 1 skip the push).
6. Release the lock in a `finally`.

Running a job:

- Working directory: the repo's `dir`. Do not pull or check out anything there; the auto-deploy
  owns those clones. Record the clone's current commit (`git rev-parse HEAD`) in the result.
- Environment: remove `ALMA_PROD_API_KEY` from the child process environment.
- Capture stdout and stderr to `shared_output_dir\<id>\output.log`.
- Enforce `timeout_minutes`, and on timeout kill the whole process tree, not just the parent.
- Run at most one job per fire if that keeps the task short; the next fire takes the next one.

Result file:

```json
{
  "id": "20261125-141200-rs-pytest",
  "repo": "Alma-RS-lending-request-automation",
  "job": "pytest",
  "status": "passed",
  "exit_code": 0,
  "commit": "f37aaf7",
  "started_at": "2026-11-25T14:15:03+02:00",
  "duration_seconds": 41,
  "tail": ["142 passed, 1 skipped in 0.95s"],
  "full_log": "_ops_shared/jobs/20261125-141200-rs-pytest/output.log"
}
```

Lessons already paid for on this machine, in `masedet-ws-ops/docs/ssh-key-setup.md`. Apply them:

- Git under Task Scheduler must never be able to prompt: SSH with `BatchMode yes`,
  `GCM_INTERACTIVE=never`, `GIT_TERMINAL_PROMPT=0`. A prompt hangs the task forever.
- Use Git's bundled ssh, not the Windows inbox one.
- Put a timeout on every git call and kill the process tree, or one hang leaks the lock and
  blocks every later run.
- Target Windows PowerShell 5.1 unless PowerShell 7 is confirmed on masedet.

Also add `-DryRun`: validate and log what would run, write nothing, push nothing.

### 4.4 Scheduled task (registered by the owner over RDP)

- Name: `remote_jobs_devsandbox`. Every 5 minutes. Same account as `git_auto_deploy_prod`.
- Action: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <ops clone>\scripts_admin\remote_jobs.ps1`.
- Put the exact registration steps in `masedet-ws-ops/docs/remote-jobs.md`, with how to check
  it works and how to turn it off.

### 4.5 Agent command: `tau-masedet` (phase 2)

Lives in the sandbox kit next to `tau-relay` and `tau-deploy`; follow their conventions.

- `tau-masedet jobs [repo]`: list the jobs in the catalogue (read from the `masedet-ws-ops` clone).
- `tau-masedet run <repo> <job>`: refuse names not in the catalogue, write the request, commit,
  push, print the id.
- `tau-masedet wait <id>`: fetch every 30 seconds until `results/<id>.json` exists or 20 minutes
  pass; print the result; exit non-zero unless status is `passed`.

## 5. Safety rules (acceptance criteria, each needs a test)

1. A request for an unknown repo or job is refused and logged; nothing runs.
2. A request whose id contains path characters, or differs from its file name, is refused.
3. A catalogue entry whose `dir` is outside `allowed_root` never runs.
4. A request older than `max_request_age_minutes` gets `expired` and never runs.
5. A request that already has a result is never run again.
6. Two overlapping fires never run two jobs at once.
7. A job that exceeds its timeout is killed with its children and gets `timeout`.
8. The job's environment has no `ALMA_PROD_API_KEY`.
9. The kill-switch file stops everything.
10. Full output goes only to the SharePoint folder. GitHub gets the summary and at most
    `publish_tail_lines` lines.

The Alma sandbox is a copy of production, so job output can name real patrons. That is why
rule 10 exists. Never raise `publish_tail_lines` for a job that prints request or user data.

## 6. Phases

| Phase | Build | Done when |
|---|---|---|
| 0 | Owner answers the open decisions in §7 | Answers recorded in this file |
| 1 | `remote_jobs.ps1`, `remote_jobs.json` with the `pytest` job for this repo, `docs/remote-jobs.md`, tests. Results to SharePoint only, no push. One PR in `masedet-ws-ops`. Owner merges, creates `masedet-jobs`, clones it on masedet, registers the task. | A request file pushed by hand produces `_ops_shared\jobs\<id>\output.log` and a result file within 10 minutes |
| 2 | Result push to `masedet-jobs`; `tau-masedet`. | An agent runs `tau-masedet run` then `wait` and gets the result with no help |
| 3 | More jobs: `smoke`; `devsandbox-day` (count today's lines in `runs_<date>.log`, count `error` rows in the daily CSV; summary only); a Sandbox end-to-end job if decision 4 allows it. One PR per job. | Steps 6 and 8 of `docs/almaapitk-bump-protocol.md` in this repo can be done through the runner; update that protocol to say so |
| 4 | Catalogue entries for other DevSandbox clones | As needed |

Testing the script before it reaches masedet: keep validation and selection logic in functions
that take paths as parameters, and test them with Pester against temp folders (rules 1 to 9).
If Pester isn't available where you work, say so in the PR and give the owner a `-DryRun`
checklist to run on masedet.

## 7. Open decisions (the owner's; ask once, record the answers here)

1. **Where requests live.** Recommended: new private repo `masedet-jobs`. Alternative: a `jobs`
   branch in `masedet-ws-ops`.
2. **How results reach the agent.** Recommended: summary pushed to `masedet-jobs`, which needs
   masedet's SSH key to have write access to that one repo. Alternative: SharePoint only, with a
   copier on WSL that drops results into `/home/hagaybar/agent-work/` the way screenshots arrive.
3. **IT.** Tell them before the task is registered, or treat it as one more scheduled task?
4. **Jobs that write to the Alma sandbox.** Allowed (needed for the end-to-end check), or
   read-only jobs only at first?

Phase 1 depends only on decision 1. Don't block it on the others.

## 8. Unknowns to check first

- Can masedet's current GitHub SSH key push, or only pull? Is it an account key or a deploy key?
- Does the auto-deploy update the `masedet-ws-ops` clone on masedet, or is that pulled by hand?
  The executor must always run the merged catalogue; if it is pulled by hand, the script should
  pull its own repo first, or the docs must say so.
- Is `masedet-ws-ops` public? If so, check that nothing new in the catalogue or docs should be
  private, and keep staff names out.
- Does `_ops_shared` also sync to the owner's PC?
- Which Python does each DevSandbox clone use (`.venv` in the project, as the RS prod batch does)?

## 9. Working rules for whoever builds this

- All changes to `masedet-ws-ops` go through a PR. The owner merges. Never push `prod` anywhere.
- No secrets, keys, patron or staff data in any repo. Credential setup is given to the owner as
  command shapes with `<placeholder>` values.
- `scripts_admin/auto_deploy.ps1` also serves Prod. Don't edit it for this project; the runner is
  a separate script and a separate task.
- Anything done on masedet itself (clone, task registration, key access) is the owner's, over
  RDP. Give exact steps and a way to verify each one.
