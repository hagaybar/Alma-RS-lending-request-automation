# almaapitk 0.4.5 → 0.4.6 Compatibility Audit

**Date:** 2026-06-01
**Scope:** Does bumping `almaapitk` from 0.4.5 (currently pinned `>=0.4.5`, installed in `.venv`) to 0.4.6 (latest PyPI release) break this repo — a **scheduled, unattended, _mutating_ production job** that creates Alma lending requests?
**Method:** Read-only. 0.4.6 obtained via `pip download almaapitk==0.4.6 --no-deps` and unzipped to `/tmp/almaapitk_046_audit/src046`; compared against the 0.4.5 source in this project's `.venv` via `diff -u`, per-surface-file. Installed `almaapitk` symbols introspected with the project interpreter. No project files modified by the audit; nothing upgraded into `.venv`. Mirrors `Fetch_Alma_Analytics_Reports/docs/almaapitk-0.4.6-audit.md`.

> **PyPI release status (checked 2026-06-01):** `pip index versions almaapitk` → `0.4.6, 0.4.5, 0.4.3, 0.3.1`. **0.4.7 is NOT yet published.** The "PROD-write safety lock" the rollout brief attributes to 0.4.7 is a **test-harness** feature (see §F) and does not affect this repo's runtime; the latest installable is 0.4.6.

**Verdict: SAFE.** No breaking change touches this repo's surface. `domains/resource_sharing.py` and `utils/citation_metadata.py` — which carry the entire write path (`create_lending_request_from_citation`) — are **byte-identical** across 0.4.5 → 0.4.6. The two behavior changes that touch this repo are both improvements: (1) **POST is no longer auto-retried** (issue #166) — strictly *safer* for a job that creates records, as it removes the duplicate-create-on-5xx-retry risk; (2) **request/response body logging is off by default** (issue #142) — reduces patron-PII exposure. One pre-existing, bump-independent PII note is documented in §E.

---

## (a) Processor usage surface — the entire almaapitk contract this repo depends on at runtime

`resource_sharing_forms_processor.py` is the production entry point. Its complete almaapitk surface:

| Surface element | Location | Detail |
|---|---|---|
| Import | line 54 | `from almaapitk import AlmaAPIClient, AlmaAPIError, ResourceSharing, Users, CitationMetadataError` |
| Client constructor | line 163 | `AlmaAPIClient(self.environment)` — single positional arg (`"SANDBOX"` or `"PRODUCTION"`, from config). Relies on the env-var key fallback. |
| Env var (read indirectly) | — | `AlmaAPIClient` reads **`ALMA_SB_API_KEY`** (SANDBOX) / **`ALMA_PROD_API_KEY`** (PRODUCTION) from the environment when no `api_key=` is passed. The processor never reads the value itself. |
| Domain construction | lines 164–165 | `ResourceSharing(self.client)`; `Users(self.client)` |
| Connection check | line 169 | `self.client.test_connection()` (GET `conf/libraries`) |
| User lookup | line 408 | `self.users.get_user(user_id)` → reads `response.data` (dict). **Called with the default `expand='none'`.** |
| Error introspection | line 441 | `except AlmaAPIError as e: if e.status_code == 404:` — relies on `AlmaAPIError.status_code` |
| **Lending request create (WRITE)** | line 728 | `self.rs.create_lending_request_from_citation(**params)` where `params = {partner_code, external_id, owner, format_type, source_type, pmid|doi, note}` |
| Result read | lines 731–739 | `request['request_id']`, `request.get('title', '')` |
| Exceptions caught | lines 741, 743 | `except CitationMetadataError` → `MetadataFetchError`; `except AlmaAPIError` → `LendingRequestError`; bare `except Exception` → `LendingRequestError` |

**Notes on the surface:**
- The write path (`create_lending_request_from_citation`) internally calls `enrich_citation_metadata(pmid=, doi=, source_type=)` from `almaapitk.utils.citation_metadata` (which may raise `CitationMetadataError`), then `create_lending_request(...)`, returning a dict containing `request_id` and `title`. The processor's reads match this contract.
- The processor imports `CitationMetadataError` from the **top-level** `almaapitk`. It does **not** import `enrich_citation_metadata` directly (it is invoked transitively inside the toolkit).
- The L1 contract methods named in the rollout brief — `create_lending_request`, `get_lending_request`, `get_request_summary` — are **not** called by the production processor. They are exercised only by the repo's standalone live demo scripts (`tests/test_resource_sharing_lending.py`, `tests/test_citation_metadata.py`, root `test_user_retrieval.py`), which construct `AlmaAPIClient('SANDBOX')` and hit real APIs. Those scripts are not part of the offline `pytest` suite.

---

## (b) Full 0.4.5 → 0.4.6 diff, restricted to files this repo touches

Per-file `diff -u`, installed 0.4.5 vs downloaded 0.4.6:

| File | Status | Relevance to this repo |
|---|---|---|
| `domains/resource_sharing.py` | **byte-identical** | The entire write path. `create_lending_request_from_citation`, `create_lending_request`, `get_lending_request`, `get_request_summary` — all unchanged. |
| `utils/citation_metadata.py` | **byte-identical** | `enrich_citation_metadata`, `CitationMetadataError` — unchanged. |
| `domains/users.py` | changed (see below) | `get_user` gains `expand` validation + structured logging. **No effect** on this repo's `get_user(user_id)` default-`expand` call. |
| `client/AlmaAPIClient.py` | changed (see below) | Retry policy, key resolution, logging. Two changes touch this repo — both improvements. |
| `__init__.py` | additive | Adds `CredentialError` to the public exports. Nothing removed. |

**`client/AlmaAPIClient.py` changes:**
1. **Retry: POST removed from `DEFAULT_RETRY_ALLOWED_METHODS`** (issue #166) — now `{"GET","PUT","DELETE"}` (was `{"GET","POST","PUT","DELETE"}`). Status forcelist unchanged `(429,500,502,503,504)`, total retries unchanged `3`. See §D — this is the one change with real semantics for a write job.
2. **New `CredentialError(AlmaValidationError)`** (issue #143). On a missing key, the client now raises `CredentialError` (with a clearer message) instead of a bare `ValueError`. `CredentialError` subclasses `AlmaValidationError` → `ValueError`, so any prior `except ValueError` still catches it.
3. **`AlmaAPIClient.__init__` gains keyword-only `api_key: Optional[str] = None`** after the existing `*`. First positional is still `environment: str = 'SANDBOX'`, so `AlmaAPIClient(self.environment)` is unchanged. Key resolution moved to a `DEFAULT_API_KEY_ENV_VAR` table (`SANDBOX→ALMA_SB_API_KEY`, `PRODUCTION→ALMA_PROD_API_KEY`); explicit `api_key=` wins, else the env var.
4. **Logging/PII hardening** (issues #142/#154): request/response **body** logging is now opt-in (`log_bodies`, default `False`); `test_connection` no longer interpolates `response.text` / `{e}` into log message strings (they bypassed the redactor); body-trace helpers (`log_request_body`/`log_response_body`/`should_log_bodies`) added.

**`domains/users.py` changes:**
- `get_user` validates `expand` against `{"loans","requests","fees"}` and raises `AlmaValidationError` for unknown tokens **before** any HTTP call. The guard is skipped when `expand` is `"none"` (the default) — **this repo passes no `expand`, so the path is identical to 0.4.5.**
- Internal logging switched from f-strings to structured kwargs (`self.logger.info("Retrieved user", user_id=user_id)`).
- Many **additive** new methods (`create_user_rs_request`, `get_user_rs_request`, `cancel_user_rs_request`, purchase-request helpers, etc.). Unused here.
- `get_user` signature, return type (`AlmaResponse`), and `.data` shape — unchanged.

**`AlmaAPIError`** (verified by introspecting 0.4.6): `__init__(self, message, status_code=None, response=None, tracking_id=None, alma_code='')`; `e.status_code` is preserved. The processor's `e.status_code == 404` at line 441 works unchanged.

---

## (c) Breaking changes affecting this repo

**None.** Per-symbol classification of the surface in §(a):

| Symbol | 0.4.6 status |
|---|---|
| `import AlmaAPIClient, AlmaAPIError, ResourceSharing, Users, CitationMetadataError` (line 54) | **unchanged** — all five still exported from top-level `almaapitk`; same inheritance. |
| `AlmaAPIClient(self.environment)` (line 163) | **unchanged** — `environment` still first positional; new `api_key` is keyword-only with `None` default. |
| `ALMA_SB_API_KEY` / `ALMA_PROD_API_KEY` env-var contract | **unchanged** — still the SANDBOX/PRODUCTION fallbacks. Only the *exception type* on a missing key changed (now `CredentialError`, a subclass of `ValueError`); the processor does not catch it, so it propagates and fails init loudly in either version — correct for a scheduled job. |
| `ResourceSharing(client)` / `Users(client)` (lines 164–165) | **unchanged** |
| `self.client.test_connection()` (line 169) | **unchanged** signature/return; internal logging hardened only. |
| `self.users.get_user(user_id)` (line 408) → `.data` | **unchanged** for `expand='none'`. New expand-validation guard is bypassed. |
| `AlmaAPIError.status_code` (line 441) | **unchanged** — attribute preserved. |
| `self.rs.create_lending_request_from_citation(**params)` (line 728) | **unchanged** — `resource_sharing.py` is byte-identical; same signature, same `{request_id, title, ...}` return dict. |
| `request['request_id']`, `request.get('title')` (lines 731–739) | **unchanged** — return contract preserved. |
| `except CitationMetadataError` / `except AlmaAPIError` (lines 741, 743) | **unchanged** — both still raised from the same paths (`citation_metadata.py` identical; `AlmaAPIError` raised from the same client code). |

No processor line needs remediation.

---

## (d) Write-path behavior — the POST-retry change (special to this _mutating_ repo)

This is the one delta with operational meaning for a job that **creates** records.

- **0.4.5:** `create_lending_request_from_citation` issues a `POST`. POST was in `DEFAULT_RETRY_ALLOWED_METHODS`, so a `429`/`5xx` on the create was **automatically retried** up to 3× by the mounted `HTTPAdapter`. Risk: if Alma committed the create but the response was lost (5xx/timeout after commit), the retry could produce a **duplicate lending request**.
- **0.4.6 (issue #166):** POST is **removed** from the retried verbs (`{"GET","PUT","DELETE"}`), matching urllib3's own default. A `429`/`5xx` on the create now surfaces **immediately** as an `AlmaAPIError` (no automatic retry).

**Net effect for this repo — safe, arguably better:**
- The duplicate-create-on-retry risk is **eliminated**. For a non-idempotent create, not retrying is the correct default.
- A transient `5xx` on the create is now caught by `except AlmaAPIError` (line 743) → `LendingRequestError` → logged; the TSV file is **not** moved to `processed/` (the move only happens on `success`/`dry_run_success`, lines 798–799). The **file-as-state** design means the file remains in `input/` and the create is retried on the **next scheduled run** (~1 minute later). So transient failures still recover — at the file granularity, not the HTTP granularity — with no data loss and no duplicate-on-same-second risk.
- GET paths (the `test_connection` check, user lookup) remain retried as before. (Citation metadata is fetched from PubMed/Crossref by `citation_metadata.py` over its own `requests` calls — outside the Alma client's retry adapter — unchanged by this bump.)
- The external-id collision caveat in CLAUDE.md ("reprocessing within the same second could collide") is *reduced* by this change: fewer in-run POST retries means fewer same-second re-attempts.

No code change required. Optionally, the operator may later opt POST back into retries via a custom `urllib3.util.retry.Retry` passed as `AlmaAPIClient(retry=...)`, but **the new default is the recommended posture for a create job.**

---

## (e) PII / logging considerations (special to this repo)

This repo recently hardened patron-PII handling on its **own** logger (`ResourceSharingFormsProcessor`): `_log_pii`, `mask_user_id`, `PiiConsoleFilter`, file-only PII sink.

**What the bump improves:**
- 0.4.6 turns **request/response body logging off by default** (`log_bodies=False`, issue #142). A single `get_user` returns the whole patron record; in 0.4.5 that body was logged at DEBUG (`response_data=...`). 0.4.6 no longer emits it unless explicitly enabled. Strict PII improvement.
- 0.4.6 stops interpolating `response.text` / `{e}` into `test_connection` log strings (issue #154), so those now pass through the redactor as structured fields.
- File logging is off by default (`output.file=False`), so the toolkit no longer drops a `logs/api_requests/...` file under the working dir without opt-in.

**Pre-existing condition (NOT a bump regression) — flagged because this repo is PII-sensitive:**
- almaapitk's own domain logger is `logging.getLogger("almapi.<domain>")` with `propagate=False` and, when `output.console=True` (**the default**), its **own `StreamHandler(sys.stdout)`** at INFO. The `users` domain therefore logs `user_id` to **stdout** — as an f-string in 0.4.5 (`f"Retrieved user {user_id}"`) and as a structured field in 0.4.6 (`"Retrieved user", user_id=...`). The default `redact_patterns` (`apikey`, `api_key`, `password`, `token`, `secret`, `authorization`) do **not** include `user_id`, so it is not redacted in either version.
- The repo's `PiiConsoleFilter` is attached to the `ResourceSharingFormsProcessor` logger, **not** to `almapi.*` (which has `propagate=False` and its own handler). So almaapitk's console line is **outside** the repo's masking — in both versions.
- **This is bump-independent** (present in 0.4.5; 0.4.6 only narrows it by removing the body), so it is **not a blocker** for the bump. But since the bump is the moment we're verifying PII posture, recommend closing the gap: in the processor's logging setup, quiet or filter the toolkit logger, e.g.
  - `logging.getLogger("almapi").setLevel(logging.WARNING)` (the toolkit exposes a single `almapi` parent for exactly this), **or**
  - attach the repo's `PiiConsoleFilter` to the `almapi` logger / its handler, **or**
  - construct the client after disabling the toolkit's console output.
- **Verify during the live SANDBOX smoke (§F/L3):** capture stdout and confirm no raw `user_id` from the `almapi.users` logger appears unmasked.

---

## (f) PROD-write safety lock & the L1/L2/L3 test strategy

**The "PROD-write safety lock" is a _test-harness_ feature, not a runtime change.** 0.4.6 already ships an `almaapitk/testing/` package, including `testing/guards.py` with `install_readonly_guard(session)` / `ReadOnlyViolation` — a rail that wraps a `requests.Session` so any non-GET verb raises *before* I/O ("PRODUCTION-targeted workflows may only read"). The rollout brief attributes the lock to 0.4.7; whatever 0.4.7 adds (auto-wiring/enforcement) sits in this `testing/` namespace. **None of it touches the production `AlmaAPIClient` this repo runs** — so the runtime behavior of the scheduled job is identical whether this repo pins `>=0.4.6` or `>=0.4.7`.

Test layering for this repo (mirrors the analytics model; adapted because **this repo mutates**):
- **L1 (in almaapitk):** contract tests pin the `ResourceSharing` surface this repo uses. Done upstream — not re-done here.
- **L2 (offline, this repo):** mock/golden test of the repo's *own* logic — identifier auto-detection (PMID vs DOI), `external_id` assembly, the structured `note` builder, and the exact `params` handed to `create_lending_request_from_citation` — with the toolkit boundary mocked. No network. (To be added; the analytics analog is `tests/test_diff_harness.py`.)
- **L3 (opt-in live, this repo):** `tests/test_live_smoke.py` creates **one real lending request in SANDBOX**, gated behind `RUN_LIVE_SMOKE=1` so it never runs during a normal `pytest`. **No teardown** (SANDBOX is disposable). It must **hard-refuse to target PRODUCTION** — assert `environment == "SANDBOX"`, never read `ALMA_PROD_API_KEY`. This is the consumer-side mirror of the upstream PROD-write lock. (To be added.)

**Implication for the version pin (§D/§F):** runtime is identical for `>=0.4.6` vs `>=0.4.7`. Pin `>=0.4.7` once it is published, to keep the consumer aligned with the rollout gate's test guarantees; until then `>=0.4.6` is correct and unblocks deployment.

---

## (g) Verdict & recommendation

**Bumping `almaapitk` 0.4.5 → 0.4.6 is SAFE for this repo.** Every symbol the processor imports / constructs / calls / catches is preserved with compatible signatures and inheritance. The write path (`resource_sharing.py`, `citation_metadata.py`) is byte-identical. The only behavior changes that reach this repo are improvements: POST is no longer auto-retried (removes duplicate-create risk on a non-idempotent create; transient failures still recover via the per-file retry on the next scheduled run), and patron-record bodies are no longer logged by default. One bump-independent PII note (toolkit `almapi.users` console logging of `user_id`) is documented in §E with a one-line mitigation; it does not block the bump.

**Recommended next steps (consumer-rollout gate):**
1. Add the L2 offline mock/golden test (§F) and the L3 opt-in SANDBOX live smoke (§F), with the PROD-write refusal baked into L3.
2. Bump the pin in `pyproject.toml`: `>=0.4.7` if 0.4.7 is published; otherwise `>=0.4.6`.
3. `poetry update almaapitk` then `poetry run pytest` (offline). Run the L3 SANDBOX smoke manually with `RUN_LIVE_SMOKE=1`.
4. While running L3, confirm stdout shows no unmasked `user_id` from the toolkit logger (§E verification).
5. Re-verify on the masedet prod workstation per its own `poetry install` before merging `main` → `prod`.
</content>
</invoke>
