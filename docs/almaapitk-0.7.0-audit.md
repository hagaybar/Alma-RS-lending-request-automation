# almaapitk 0.5.1 → 0.7.0 compatibility audit

**Date:** 2026-11-11 · **Issue:** #55 · **Protocol:** `docs/almaapitk-bump-protocol.md`
**Method:** AlmaAPITK `CHANGELOG.md` sections 0.6.0 and 0.7.0, read against this repo's usage
surface, plus the toolkit source for signatures. The L1 contract tests for ResourceSharing in
AlmaAPITK pass on 0.7.0.

**Verdict: SAFE.** No code change. One test was relaxed because 0.6.0 added keyword-only
arguments.

## (a) Usage surface

| Symbol | Where |
|---|---|
| `AlmaAPIClient(env, timeout=int(api_timeout_seconds or 180))` | `resource_sharing_forms_processor.py` l.190 |
| `ResourceSharing(client).create_lending_request_from_citation(**params)` | `rs_requests/lending.py` l.163 |
| `Users(client).get_user(user_id)`; `except AlmaAPIError` + `e.status_code == 404` | processor l.454, l.486–487 |
| `build_user_rs_request(...)` | `rs_requests/borrowing.py` l.176 |
| `Users.create_user_rs_request(user, payload, validate=True[, override_blocks=True])` | borrowing l.216 |
| `except (AlmaTimeoutError, RequestException)` → unconfirmed, re-raised | borrowing l.219 |
| `except AlmaValidationError` → `BorrowingValidationError` (permanent skip) | borrowing l.225 |
| `except AlmaAPIError`; `alma_code` `402362` duplicate, `401604` self-ownership | borrowing l.234, l.325–346 |
| `CitationMetadataError`, citation metadata helpers | `rs_requests/lending.py`, `rs_requests/metadata.py` |

## (b) Upstream changes that touch this surface

- **0.6.0, #196.** `AlmaTimeoutError` is an `AlmaAPIError` and still a
  `requests.exceptions.Timeout`. `create_user_rs_request` gains keyword-only `timeout=`,
  `reconcile=False` and `reconcile_marker=None`. The defaults keep the old behaviour, so no
  note marker is added unless `reconcile=True` is passed.
- **0.6.0, #208.** A 5xx that survives the retries raises `AlmaServerError` (an
  `AlmaAPIError`), not `requests` `RetryError`. POST was already not retried (0.4.6).
- **0.6.0.** `Retry-After` waits are capped at 120 s.
- **0.7.0, #205.** 401, 429 and 5xx outrank a mapped Alma error code, so they raise
  `AlmaAuthenticationError`, `AlmaRateLimitError` and `AlmaServerError`. All are
  `AlmaAPIError`s, and `alma_code` is still set on them.
- 0.7.0 Configuration lists, `iter_paged`, `raw_request` and the Lab are not used here.

## (c) Classification

| Symbol | Status |
|---|---|
| `AlmaAPIClient(env, timeout=)` | unchanged |
| `create_lending_request_from_citation` | unchanged |
| `get_user` + 404 check | unchanged; `status_code` is still on every `AlmaAPIError` |
| `build_user_rs_request` | unchanged |
| `create_user_rs_request(validate=True, override_blocks=)` | compatible; new keyword-only arguments with neutral defaults |
| `AlmaTimeoutError` clause placed before `AlmaAPIError` | correct for 0.6.0+ (the code already notes this) |
| `alma_code` matches `402362` / `401604` | unchanged; both arrive with HTTP 400, which #205 does not affect |

## (d) Repo-specific risks

- **Duplicate creates:** none added. POST isn't retried. A read timeout is still reported as
  unconfirmed, and Alma's `402362` duplicate check stays the safety net.
- **Classification:** a 429 or 5xx now always arrives as `AlmaRateLimitError` or
  `AlmaServerError`. Both reach the `AlmaAPIError` clause and fall through
  `_is_duplicate_rejection`, as before.
- **Timeout:** 180 s from config, unchanged.
- **PII:** no logging change in 0.6.0 or 0.7.0.

## (e) Result

- **Test change:** `tests/test_borrowing_toolkit_contract.py` now checks the first six
  parameters of `create_user_rs_request`, not the exact list (0.6.0 added keyword-only
  arguments).
- **Lock:** `poetry update almaapitk` moved almaapitk 0.5.1 → 0.7.0 only.
- **L2:** 142 passed, 1 skipped. `scripts/smoke_project.py` OK.
- **L3:** not run in the TAU sandbox (no SANDBOX config for the forms). The owner runs one
  lending and one borrowing form on SANDBOX before merging.
