# almaapitk bump protocol (binding)

Every change to this repo's `almaapitk` pin follows this document, step by step. It is binding:
a bump that skips a step is not done. `CLAUDE.md` points here.

**Why it exists.** This repo is a production consumer of `almaapitk`. It runs on a production workstation,
and `main` and `prod` auto-deploy on a schedule with no second checkpoint. A bad bump on a
scheduled repo can fail silently in production. A bump is therefore a small, audited change
made inside this repo, never a one-line pin edit pushed from somewhere else.

## Ground rules

- **One repo at a time, from this repo.** The bump is done by a session working in this repo,
  using this repo's tests. Never as part of a batch across consumer repos, and never driven
  from the AlmaAPITK repo. An AlmaAPITK release ends by opening this repo's bump issue.
- **Trigger:** the issue "Bump almaapitk to `<version>` (pin → validate → main → prod)" in this
  repo. Bump to the current release directly; skip intermediate versions.
- **Agents never merge to `prod` or push to it.** The owner merges the PR into `main` and
  promotes `main` → `prod`.
- **No production writes during validation.** Live checks against PRODUCTION are read-only.
  Anything that writes to Alma, sends email or uploads files runs only against the SANDBOX,
  with `ALMA_PROD_API_KEY` unset, or not at all.
- **No real identifiers** (user IDs, MMS IDs, report paths with names, emails) in commits, PRs,
  issues or the audit. Use placeholders.

## Steps

### 1. Branch

`git checkout main && git pull && git checkout -b chore/almaapitk-<version>`.

### 2. Audit first: `docs/almaapitk-<version>-audit.md`

Write it before changing the pin. Earlier audits in `docs/` are the model. Sections:

- **(a) Usage surface.** Every `almaapitk` import and call in this repo, with `file:line`:
  classes, methods and arguments, exceptions caught, environment variables relied on.
- **(b) Upstream changes** from the version in `poetry.lock` to `<version>`: the AlmaAPITK
  `CHANGELOG.md` sections in between, plus anything the bump issue calls out. When the
  CHANGELOG is unclear, diff the wheels (`pip download almaapitk==<v> --no-deps` for both,
  then `diff -ru`).
- **(c) Per-symbol classification** of the usage surface: unchanged / changed but compatible
  / breaking. Every breaking entry names its fix.
- **(d) Repo-specific risks** listed under "This repo" below.
- **(e) Verdict:** SAFE, SAFE WITH CHANGES (list them), or BLOCKED (stop and report upstream).

### 3. Pin and lock

- Set `almaapitk = ">=<version>"`, keeping the pin's style and its comment.
- Run `poetry update almaapitk`, never a bare `poetry lock` that refreshes everything. Then run
  `poetry check --lock` and confirm `poetry.lock` resolves `almaapitk <version>`.
- No other package may move. If one must, list it in the audit with the reason.
- In the TAU sandbox, prefix Poetry commands with `POETRY_VIRTUALENVS_IN_PROJECT=false`. A
  `.venv` in the folder belongs to the WSL host.

### 4. Code changes (only if the audit requires them)

Keep them minimal, and give each one a test that fails without it. Don't add unrelated work
to the bump branch.

### 5. L2: this repo's tests

Run the commands under "This repo". All green, with no new skips.

### 6. L3: live check

Run the commands under "This repo" and record what ran and the result in the audit. If a
required L3 step can't run where you are (for example missing config), the PR says so and the
owner runs it before merging.

### 7. Pull request into `main`

- Commit the audit, pin, lock and any code changes:
  `chore(deps): bump almaapitk to >=<version> (#<issue>)`.
- The PR body links the audit and gives the L2 result and the L3 result (or what is left for
  the owner). It says `Refs #<issue>`, not `Closes`.
- Tick the issue's boxes that are actually done.
- The owner merges.

### 8. DevSandbox (production workstation)

After the next auto-deploy of `main`, run the repo's DevSandbox check on the production workstation (see "This
repo"). If L3 in step 6 already ran there, on the deployed `main`, it counts. Note the result in
the issue.

### 9. Prod

The owner merges `main` → `prod`; the next auto-deploy pulls the new version into Prod. After
the next Prod run, check its logs and output, then close the issue.

### Rollback

Pin `almaapitk==<previous>` on `prod`, run `poetry update almaapitk`, and push. The next
auto-deploy restores the previous version. Report the regression in AlmaAPITK with a failing
test (AlmaAPITK rule R10).

## This repo: Alma-RS-lending-request-automation

This is a **scheduled, unattended, writing** production job. Every 5 minutes on the production workstation it
creates lending requests and user (borrowing) requests in Alma. Treat every bump as
high-risk.

- **Usage surface:**
  - `resource_sharing_forms_processor.py`: `AlmaAPIClient(env, timeout=)`, `ResourceSharing`,
    `Users.get_user`, `CitationMetadataError`, `AlmaAPIError.status_code`.
  - `rs_requests/lending.py`: `create_lending_request_from_citation`.
  - `rs_requests/borrowing.py`: `build_user_rs_request`,
    `Users.create_user_rs_request(validate=True, override_blocks=)`, `AlmaTimeoutError`,
    `AlmaValidationError`, and the `alma_code` matches `401604` and `402362`.
  - `rs_requests/metadata.py`: citation metadata helpers.

  Check it with
  `grep -rn "from almaapitk\|alma_code\|status_code" rs_requests resource_sharing_forms_processor.py`.
- **Repo-specific risks for (d):**
  - Anything that could create a request twice: retries of POST, timeouts after Alma saved the
    request, and the duplicate check (`402362`).
  - Error classification: which exception class and `alma_code` the borrowing and lending
    paths see for 400/401/429/5xx.
  - The client timeout (`api_timeout_seconds`, default 180).
  - Patron data in logs.
- **L2:** `poetry run pytest -q` and `poetry run python scripts/smoke_project.py`.
  `tests/test_borrowing_toolkit_contract.py` pins the toolkit signatures this repo relies on.
- **L3 (SANDBOX only, `ALMA_PROD_API_KEY` unset):** one lending form and one borrowing form end
  to end, with `config/tests-config.json --live`. This is what
  `batch/rs_forms_scheduled_dev_sb.bat` runs. Never run `--live` against PRODUCTION during a
  bump.
- **DevSandbox check (production workstation):** the SANDBOX task, `RS SB Lending-Borrowing (on demand)`, has
  no schedule since 2026-11-25, so there is no "clean day" to wait for. Instead, on the workstation:
  1. In the DevSandbox clone: confirm
     `config\tests-config.json` says `"environment": "SANDBOX"` and note its `input_folder`,
     `borrowing_input_folder` and `output_dir`; `git log -1` shows the merged `main`;
     `poetry run python -c "import almaapitk; print(almaapitk.__version__)"` shows the new version.
  2. Write one lending and one borrowing test TSV (test codes, one PMID, a note saying it is a
     test, no patron data) into those two input folders, UTF-8 **without** a BOM.
  3. `Start-ScheduledTask -TaskName "RS SB Lending-Borrowing (on demand)"` and wait for it to end
     (`LastTaskResult` 0).
  4. Both files are in `processed`, today's `<output_dir>\reports\processed_<date>.csv` has two
     `success` rows with request IDs, and both requests read back from the Alma sandbox.
  The 0.7.0 run (issue #55, 2026-11-25) is the worked example.
- **More:** prod operations (folders, post-deploy checks, rollback) are in the owner's private documentation.
