# Design: Confine private data to local logs (PII leak isolation)

**Date:** 2026-05-24
**Status:** Approved (pending spec review)
**Related:** GitHub issue #4 (security audit), findings F1/F2/F3/F4

## Problem

The repository is a **public** GitHub repo (`hagaybar/Alma-RS-lending-request-automation`).
Two paths can carry private data (patron PII; secrets) off the local machine:

1. **`.a5c/` agent-run artifacts are tracked and pushed.** Babysitter records task
   outputs, journals, and a context-compression cache under `.a5c/runs/` and
   `.a5c/cache/`. These are committed to the public repo. They are PII-free *today*,
   but any future run that operates on real TSV data — or a shell task that captures
   the processor's stdout — would pull patron PII into `.a5c/` and publish it.
2. **The processor prints patron PII to stdout/console.** Patron name + ID and the
   free-text note are logged at INFO to the console handler, where terminal snapshots
   and AI coding agents capture them.

## Goal & constraints

- **Keep full operational logging locally** — users, actions, errors must still be
  logged in detail to the local (gitignored) log/report files.
- **No private data reaches `.a5c/` files** (the public-repo vector).
- **Preserve relevant `.a5c/` history** — local run history stays; process definitions
  stay in git. The repo remains public.
- **First priority is safety.** Prefer deterministic barriers over best-effort scrubbing
  of free text (a patron name cannot be reliably regex-matched).

## Chosen approach: Approach B — boundary isolation + console sanitization

Two independent, layered barriers:

- **Layer 1 (Section 1):** stop tracking `.a5c/` per-run capture data → PII can never
  reach the public repo via `.a5c`.
- **Layer 2 (Sections 2–3):** confine PII to local *file* sinks; the console/stdout is
  PII-free → protects terminal snapshots, agent stdout capture, and general LLM exposure.

Rejected alternatives:
- **Approach A (isolation only):** leaves PII in console output. Insufficient for the
  stated LLM-exposure concern.
- **Approach C (keep `.a5c` public + pre-commit scrubber):** safety depends on a regex
  catching free-text patron names in journals — unreliable, conflicts with "safety first."

---

## Section 1 — `.a5c` boundary isolation (git hygiene)

**Gitignore + untrack the per-run capture vectors:**
- Add to `.gitignore`: `.a5c/runs/` and `.a5c/cache/`.
- `git rm -r --cached .a5c/runs .a5c/cache` — removes from tracking; files remain on disk.
  Babysitter reads/writes these locally regardless of git, so local run history is fully
  preserved and the SDK keeps working.

**Keep committed** (reusable "recipe" layer, low PII risk):
- `.a5c/processes/*.js`, `.a5c/processes/*-inputs.json`, `.a5c/package.json`,
  `.a5c/package-lock.json`.
- Scrub hardcoded absolute paths in `.a5c/processes/task-scheduler-migration.js`
  (`/home/hagaybar/projects/Alma-RS-lending-request-automation` and any
  `/home/hagaybar/.claude/...`) to relative paths (`.`). The other absolute path lived in
  `.a5c/cache/compression/*.json`, which becomes untracked by this change.

**Git history:** already-committed `.a5c/runs`/`.a5c/cache` remain in *past* history
(public). They are PII-free today, so history is left as-is (rewrite is out of scope per
issue #4). Net effect: no `.a5c` runtime data is pushed from this change forward.

---

## Section 2 — Console sanitization (logging sink split)

Principle: **file handler = full PII (local, unchanged); console handler = PII-free.**
PII is marked at the source — deterministic, no message-text regex.

**Mechanism:**
- `class PiiConsoleFilter(logging.Filter)`: `filter()` returns `False` for any record
  with attribute `pii == True`. Attached to the **console handler only**. The file handler
  has no such filter and receives every record (full PII).
- Each PII-bearing log call uses `extra={'pii': True}` for the full-detail line (→ file
  only) and, where operationally useful, emits a sanitized companion line for the console.
- `mask_user_id(uid) -> str` helper: returns `'*' * max(0, len(uid) - 4) + uid[-4:]`
  for `len(uid) > 4`; `'***'` for shorter/empty. Used on warning lines that should still
  surface on the console.

**Call-site changes** (`resource_sharing_forms_processor.py`):

| Line (approx) | Today | After |
|---|---|---|
| 657 — Note (name + id + group + comments) | full note on console | file-only (`pii=True`); no console line |
| 384 — user-lookup success (id, name, group) | full on console | file-only (`pii=True`); console: `User <***1234>: verified Academic staff` |
| 500 — Requester name + id (DEBUG) | leaks at verbose | file-only (`pii=True`) |
| 366 — user_id (DEBUG) | leaks at verbose | file-only (`pii=True`) |
| 398 / 400 / 403 — warnings with user_id | full id | masked: e.g. `User not found: ***1234` |

**Console still shows (no PII):** file name, partner code, identifier (PMID/DOI),
detected type, status, request_id, title, counts, masked-id warnings.

**Unchanged (local file sinks keep full PII):** `output/reports/*.csv` (F2),
`output/file_logs/*.log`, `output/logs/processor.log`. These are gitignored local files.

---

## Section 3 — `test_user_retrieval.py` (finding F3)

This diagnostic prints a full Alma user record (name, emails, phones, addresses) to
stdout. Bound it:
- Mask contact fields (emails, phones, addresses) by default.
- Gate the raw `json.dumps(user_data)` dump behind an explicit `--show-raw` flag
  (default off).

Keeps the tool useful while preventing the largest PII-to-terminal surface from firing
accidentally.

---

## Section 4 — Testing

Mocked only; **no live Alma API calls.**

- `PiiConsoleFilter`: a record with `extra={'pii': True}` is dropped by the console
  handler but written by the file handler (capture both streams/handlers).
- `mask_user_id`: correct masking for normal, short (<=4 char), and empty IDs.
- Processed-request smoke check (mocked client): assert patron name and note text appear
  in the file-log output but **not** in captured stdout.
- `test_user_retrieval`: `--show-raw` absent → contact fields masked; `--show-raw`
  present → full dump emitted.

## Success criteria

1. `git ls-files '.a5c/**'` lists only `processes/` + package files — no `runs/`/`cache/`.
2. Running the processor against mocked patron data prints **no** patron name, full ID, or
   note text to stdout, while the file log contains all of it.
3. `test_user_retrieval.py` without `--show-raw` shows masked contact fields.
4. Existing test suite still passes (the 4 pre-existing fixture-not-found errors are
   unrelated and out of scope).

## Out of scope

- Rewriting git history to purge already-committed (PII-free) `.a5c` data.
- Broad logging-architecture refactor; only the specific PII sinks are changed.
- Changes to `almaapitk` (toolkit-side redaction already handled via issue #3).
