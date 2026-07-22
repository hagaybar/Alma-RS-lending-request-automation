# Borrowing Request Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend this processor to create Alma **borrowing** (user resource-sharing) requests from a second input folder, without disturbing the production lending path.

**Architecture:** The Power Automate flow already forks on a holdings check, writing lending files to `input/` and borrowing files to `input_borrowing/`. Everything up to request creation — file watching, identifier detection, metadata enrichment, moving to `processed/`, logging, reporting — is shared and stays in `resource_sharing_forms_processor.py`. Only the terminal step differs, so the two request-building/submitting behaviours move behind a small `RequestBuilder` interface in a new `rs_requests/` package. Lending is extracted first as a pure refactor guarded by a characterization test; borrowing is then added as a second implementation of the same interface.

**Tech Stack:** Python 3.12, Poetry, pytest, `almaapitk` (Alma REST client), PubMed E-utilities / Crossref for citation metadata.

**Reference:** `docs/BORROWING_REQUESTS.md` is the authority for every field value (§9 records the 2026-07-22 upstream live evidence). `docs/BORROWING_SB_TEST_MATRIX.md` lists the SANDBOX tests that close its open questions.

> **Revised 2026-07-22:** scope narrowed to DIGITAL+CR articles; body building
> moved to `almaapitk.build_user_rs_request` (merged upstream in PR #206,
> gated on the 0.5.0 release); `401604` policy decided. Guidebook §9 has the
> upstream evidence behind every change.

## Global Constraints

- Python `^3.12`, dependencies via Poetry. `package-mode = false` — the repo runs from its root, so `rs_requests/` is imported as a plain top-level package.
- **Scope — articles only: `citation_type=CR` + `format=DIGITAL` (DECISION 2026-07-22).** The book path (`BK`) is out of scope: `PHYSICAL`+`BOOK` creates reproducibly 500 in SANDBOX (AlmaAPITK #207, culprit undetermined), the census shows zero `E_CR`/`E_BK`, and the 2026-07-22 A/B probe showed `E_CR` discards metadata at persist (guidebook §9). `DIGITAL`+`CR` is the live-proven shape.
- **Build the body with `almaapitk.build_user_rs_request(...)` — REQUIRES almaapitk >= 0.5.0.** Merged to AlmaAPITK `main` 2026-07-22 (PR #206) and live-proven in SANDBOX, but **unreleased at plan-revision time** (PyPI latest: 0.4.6). Task 0 raises the floor and is BLOCKED until the release ships; Tasks 1–4 do not touch the new surface. The builder is exported at package root and encodes the plain-vs-`{"value": ...}` wrapping rules exactly once, upstream.
- The submit call is `Users.create_user_rs_request(user_id, request_data, user_id_type=None, override_blocks=None, *, validate=False) -> AlmaResponse`. It forwards `request_data` to Alma **verbatim**; pass **`validate=True`** so a wrong code-table value fails locally, before any HTTP, with an `AlmaValidationError` naming the field.
- `owner` is a **plain string**; `pickup_location`, `format`, `citation_type` are **wrapped** as `{"value": ...}`. The builder hides this asymmetry; it stays documented because fields passed through its `extra` dict must still respect it (the builder wraps known code-table fields in `extra` and passes everything else through untouched).
- Mandatory for a `DIGITAL` article: `title`, `journal_title`, `year` (plus `author` per the 401930 message) — confirmed live 2026-07-22. Validate locally so a bad file fails before any network call.
- **`401604` policy (DECISION 2026-07-22): never pass `override_blocks`.** When Alma answers `401604` ("institutional inventory has services for the requested title"), the create fails as a normal error row for manual handling. Power Automate's holdings fork makes this rare; auto-overriding could create borrowing requests for items we hold.
- **Dry-run by default.** `--live` must be passed explicitly for any API call.
- **SANDBOX only** for all testing. `AlmaAPIClient("SANDBOX")` reads `ALMA_SB_API_KEY` from the environment. Never place a key on a command line, never print one.
- **Duplicate safety is Alma-side — DECISION 2026-07-20 (GH #35).** A timed-out
  POST may already have saved. Recovery is NOT reconcile-by-external_id: live
  SANDBOX probes proved Alma discards client external_ids (GH #14). Instead,
  an identical re-POST for the same patron fails with alma_code `402362`
  ("Patron has duplicate request") while the original is active — verified
  live — and `submit()` treats that as already-created (status `duplicate`,
  file moves to `processed/`). This depends on the customer parameter
  `check_patron_duplicate_borrowing_requests` being `true` (it is **false by
  default**; TAU has it enabled). **Go-live precondition: confirm it is true
  in PRODUCTION config.** Accepted residual risk (user decision): a retry
  whose rebuilt body differs (metadata drift between runs) could escape the
  check — judged low-probability.
- `agree_to_copyright_terms` and `lcc_number` content are **OPEN questions** (guidebook §4.6, §4.5). Both must be config-driven with a documented default, never hardcoded, so the answers land in config without a code change. (2026-07-22: the upstream builder defaults the copyright flag to `True` — a third voice in the T-04 contradiction. Our code always passes the config value explicitly, so the builder default never applies.)
- **PII:** `lcc_number` carries a patron's name. It must be masked on console output using the existing `PiiConsoleFilter` / `_log_pii` mechanism, exactly as `user_id` already is.
- The lending path is **live production code** running on `masedet` via Task Scheduler. `tests/test_l2_citation_golden.py` must stay green at every commit.
- Branch discipline: work on `feature/borrowing-requests`, merge to `main` only. **Never commit to `prod`.** A merge to `prod` reaches production unattended on the next scheduled deploy run.

## File Structure

| Path | Responsibility |
|---|---|
| `rs_requests/__init__.py` | Package marker; re-exports `RequestBuilder`, `BuiltRequest`, `get_builder` |
| `rs_requests/base.py` | `BuiltRequest` dataclass + `RequestBuilder` ABC + `get_builder()` dispatch |
| `rs_requests/metadata.py` | `fetch_citation_metadata()` — thin adapter over the toolkit's PubMed/Crossref helpers, normalising to one internal dict |
| `rs_requests/lending.py` | `LendingRequestBuilder` — the existing lending behaviour, moved verbatim |
| `rs_requests/borrowing.py` | `BorrowingRequestBuilder` — validation + `almaapitk.build_user_rs_request` body + submit |
| `resource_sharing_forms_processor.py` | Pipeline only; delegates the terminal step to a builder |
| `config/rs_forms_config.example.json` | Gains a `borrowing` block |
| `tests/test_borrowing_toolkit_contract.py` | Guards the almaapitk floor (>= 0.5.0: builder + `validate=` pre-flight) |
| `tests/test_lending_characterization.py` | Pins lending behaviour before the refactor |
| `tests/test_builder_dispatch.py` | Folder → builder routing |
| `tests/test_borrowing_tsv.py` | Borrowing TSV parsing |
| `tests/test_borrowing_builder.py` | Borrowing payload construction and validation |
| `scripts/sb_borrowing_tests.py` | Opt-in SANDBOX harness for the test matrix (never runs by default) |

---

### Task 0: Raise the almaapitk floor to the builder release

The repo pins `almaapitk = ">=0.4.6"`. The borrowing body is built by
`almaapitk.build_user_rs_request`, which was merged upstream on 2026-07-22
(PR #206) but is **absent from every PyPI release through 0.4.6**. This task
raises the floor to the first release that ships it (expected **0.5.0** —
the operator is preparing that release and will announce it).

> **⛔ BLOCKED until that release is on PyPI.** Tasks 1–4 do not touch the
> new surface and can run first; Tasks 5+ depend on this task. Do not pin a
> git ref as a workaround — masedet installs from PyPI (see
> `docs/almaapitk-audit.md` for the bump gate used for 0.4.5→0.4.6).

**Files:**
- Test: `tests/test_borrowing_toolkit_contract.py` (create)
- Modify: `pyproject.toml`, `poetry.lock`

**Interfaces:**
- Consumes: nothing
- Produces: a proven floor for `almaapitk.build_user_rs_request` and the `validate=` pre-flight on `Users.create_user_rs_request`

- [ ] **Step 1: Write the failing test**

```python
"""Guard: the pinned almaapitk must ship the borrowing build+create surface.

The floor is the first release carrying build_user_rs_request (expected
0.5.0 — merged upstream 2026-07-22, PR #206; absent through 0.4.6).
"""
import inspect

# Import from the top-level surface — the package declares it "the ONLY
# supported public API"; internal module paths may move without notice (GH #34).
from almaapitk import Users, build_user_rs_request


def test_build_user_rs_request_is_exported():
    sig = inspect.signature(build_user_rs_request)
    # The three positional identity fields of a borrowing body.
    assert list(sig.parameters)[:3] == ["owner", "format", "citation_type"]
    assert "agree_to_copyright_terms" in sig.parameters
    assert "extra" in sig.parameters


def test_create_user_rs_request_has_the_validate_preflight():
    sig = inspect.signature(Users.create_user_rs_request)
    assert list(sig.parameters) == [
        "self", "user_id", "request_data", "user_id_type", "override_blocks",
        "validate",
    ]
    assert sig.parameters["validate"].kind is inspect.Parameter.KEYWORD_ONLY


def test_get_user_rs_request_exists_for_the_matrix_diff():
    """The SANDBOX harness GETs the created request to diff settability
    (matrix T-02). NOT used for reconcile — that is impossible (GH #14)."""
    assert hasattr(Users, "get_user_rs_request")
```

- [ ] **Step 2: Run it to verify it fails against the old floor**

Run: `poetry run pytest tests/test_borrowing_toolkit_contract.py -v`
Expected against 0.4.6: FAIL at collection —
`ImportError: cannot import name 'build_user_rs_request' from 'almaapitk'`.
That failure is the proof the floor must move.

- [ ] **Step 3: Raise the floor**

First confirm the release is actually live (this is the task's blocking gate):

```bash
poetry run pip index versions almaapitk
```

If the newest version listed is still 0.4.6, **stop here** — the task is
blocked, not failed. Otherwise, in `pyproject.toml`, replace the
`almaapitk = ">=0.4.6"` line, keeping the existing comment block above it and
appending:

```toml
# Raised to >=0.5.0: build_user_rs_request and the validate= pre-flight on
# Users.create_user_rs_request are absent below this (merged upstream
# 2026-07-22, PR #206). Borrowing support cannot function on an older floor.
almaapitk = ">=0.5.0"
```

Then `poetry lock && poetry install`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/test_borrowing_toolkit_contract.py -v`
Expected: PASS (3 tests). Also run the full suite (`poetry run pytest -q`) —
the bump must not disturb the lending path's golden test.

- [ ] **Step 5: Commit**

```bash
git add tests/test_borrowing_toolkit_contract.py pyproject.toml poetry.lock
git commit -m "test: raise almaapitk floor to 0.5.0 for the borrowing build surface"
```

---

### Task 1: Pin the lending path before touching it

A characterization test that records exactly what the lending path builds today. Task 2 refactors that path; this is the net.

**Files:**
- Test: `tests/test_lending_characterization.py` (create)
- Create: `tests/borrowing_fixtures.py` (shared fixtures for the whole feature branch — GH #22)
- Read: `resource_sharing_forms_processor.py:619-786` (`create_lending_request_from_form`)

**Interfaces:**
- Consumes: `ResourceSharingFormsProcessor.create_lending_request_from_form(form_data) -> dict`
- Produces: a frozen record of the lending `params` dict, reused unchanged in Task 2

- [ ] **Step 1: Write the failing test**

First create `tests/borrowing_fixtures.py` — the shared fixture module every
test file in this feature imports from, so no test closes over another test
module's globals (GH #22, GH #12):

```python
"""Shared fixtures for the borrowing-requests feature branch (GH #22).

file_processing paths here are placeholders — every consumer MUST override
them with tmp_path-based paths before constructing a processor (tests must
never write into the repo's live input/, processed/ or output/ folders).
"""

CONFIG = {
    "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
    "file_processing": {"input_folder": "./input", "processed_folder": "./processed",
                        "output_dir": "./output"},
    "watch_mode": {"poll_interval": 60},
    "processing_options": {"skip_invalid_identifiers": True,
                           "continue_on_metadata_failure": True,
                           "continue_on_api_error": True},
}
```

Then `tests/test_lending_characterization.py`:

```python
"""Characterization: freeze what the lending path builds today.

Runs in dry-run, so no API call is made. Asserts on the dry-run result dict
returned by create_lending_request_from_form.
"""
from pathlib import Path

from resource_sharing_forms_processor import ResourceSharingFormsProcessor
from tests.borrowing_fixtures import CONFIG

FORM = {
    "filename": "sample", "filepath": Path("sample.tsv"),
    "partner_code": "SHEB", "user_name": "Levi, David", "user_id": "",
    "is_faculty": "yes", "identifier": "33219451",
    "notes": "urgent", "order_number": "Order_Num_24586",
}


def test_lending_params_are_unchanged(tmp_path):
    cfg = dict(CONFIG)
    cfg["file_processing"] = {
        "input_folder": str(tmp_path / "input"),
        "processed_folder": str(tmp_path / "processed"),
        "output_dir": str(tmp_path / "output"),
    }
    proc = ResourceSharingFormsProcessor(cfg, dry_run=True)
    result = proc.create_lending_request_from_form(dict(FORM))

    assert result["status"] == "dry_run_success"
    assert result["detected_type"] == "pmid"
    # Pins the CSV Title column through the refactor (GH #26) — the dry-run
    # placeholder must survive the move into rs_requests/ byte for byte.
    assert result["title"] == "[DRY-RUN - Not fetched]"
    # external_id embeds a timestamp; assert its shape, not its value
    assert result["external_id"].startswith("FORMS-SHEB-")
    assert result["external_id"].endswith("-Order_Num_24586")
    assert len(result["external_id"].split("-")) == 4
```

- [ ] **Step 2: Run it to confirm it passes against current code**

Run: `poetry run pytest tests/test_lending_characterization.py -v`
Expected: PASS. If it fails, **stop** — the assumption about current behaviour is wrong and Task 2 is unsafe.

- [ ] **Step 3: Commit**

```bash
git add tests/test_lending_characterization.py tests/borrowing_fixtures.py
git commit -m "test: characterize lending request building before refactor"
```

---

### Task 2: Introduce the builder interface and move lending behind it

Pure refactor. No behaviour change. Both `tests/test_l2_citation_golden.py` and Task 1's test must stay green.

**Files:**
- Create: `rs_requests/__init__.py`, `rs_requests/base.py`, `rs_requests/lending.py`
- Modify: `resource_sharing_forms_processor.py` (`create_lending_request_from_form` becomes a delegation)
- Test: `tests/test_builder_dispatch.py` (create)

**Interfaces:**
- Consumes: Task 1's characterization test
- Produces:
  - `BuiltRequest(kind: str, external_id: str, payload: dict, summary: dict)`
  - `RequestBuilder` ABC with `kind: str`, `needs_metadata: bool`, `build(form_data, metadata=None) -> BuiltRequest`, `submit(built) -> dict`
  - `get_builder(kind: str, *, processor) -> RequestBuilder`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from rs_requests import get_builder
from rs_requests.base import BuiltRequest, RequestBuilder


def test_get_builder_returns_lending():
    b = get_builder("lending", processor=None)
    assert isinstance(b, RequestBuilder)
    assert b.kind == "lending"
    assert b.needs_metadata is False


def test_get_builder_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown request kind"):
        get_builder("interlibrary-telepathy", processor=None)


def test_built_request_is_immutable():
    built = BuiltRequest(kind="lending", external_id="X", payload={}, summary={})
    with pytest.raises(Exception):
        built.kind = "borrowing"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `poetry run pytest tests/test_builder_dispatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rs_requests'`

- [ ] **Step 3: Create the interface**

`rs_requests/base.py`:

```python
"""Request-building interface shared by the lending and borrowing paths.

The processor owns the pipeline (watch, parse, enrich, move, report). A
builder owns only the last two steps: turning parsed form data into an Alma
request body, and submitting it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BuiltRequest:
    """A request that has been assembled but not necessarily sent."""

    kind: str
    external_id: str
    payload: Dict[str, Any]
    summary: Dict[str, str] = field(default_factory=dict)


class RequestBuilder(ABC):
    """Turns parsed form data into an Alma request, and submits it."""

    #: "lending" or "borrowing" — also the config key and report label.
    kind: str = ""

    #: When True the processor fetches citation metadata and passes it to
    #: build(). Lending is False because the toolkit enriches internally.
    needs_metadata: bool = False

    def __init__(self, processor: Any) -> None:
        self.processor = processor

    @abstractmethod
    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        """Assemble the request. Must not perform network I/O."""

    @abstractmethod
    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        """Send the request to Alma. Only called when not in dry-run."""
```

`rs_requests/__init__.py`:

```python
"""Request builders for the resource-sharing forms processor."""
from typing import Any

from rs_requests.base import BuiltRequest, RequestBuilder

__all__ = ["BuiltRequest", "RequestBuilder", "get_builder"]


def get_builder(kind: str, *, processor: Any) -> RequestBuilder:
    """Return the builder for a request kind.

    Imported lazily so that a broken borrowing module can never prevent the
    production lending path from starting.
    """
    if kind == "lending":
        from rs_requests.lending import LendingRequestBuilder
        return LendingRequestBuilder(processor)
    if kind == "borrowing":
        from rs_requests.borrowing import BorrowingRequestBuilder
        return BorrowingRequestBuilder(processor)
    raise ValueError(f"unknown request kind: {kind!r}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/test_builder_dispatch.py -v`
Expected: only `test_get_builder_returns_lending` still FAILS (its lazy
import of `rs_requests.lending` is unresolved); the other two PASS —
`get_builder` raises `ValueError` for an unknown kind before any import, and
the dataclass test needs no builder at all (GH #24).

- [ ] **Step 5: Move lending into the builder**

Create `rs_requests/lending.py`. The move is **behaviour-preserving, not
literal** — the original function's body straddles the new `build`/`submit`
boundary, so three build-scope locals must be reached through the
`BuiltRequest` in `submit()`. The exact mapping (GH issue #11):

| build-scope local | in `submit()` becomes |
|---|---|
| `params` | `built.payload` |
| `external_id` | `built.external_id` |
| `detected_type` | `built.summary['detected_type']` |

**`build()`** gets the body of `create_lending_request_from_form`
(`resource_sharing_forms_processor.py:634-750`) — everything from
`# Extract fields` down to the note logging, i.e. everything **before** the
`# Create request (or dry-run)` comment — changing only `self.` →
`self.processor.` for processor attributes (`logger`, `dry_run`, `owner`,
`format_type`, `rs`, `detect_identifier_type`, `validate_identifier`,
`_lookup_and_verify_user`, `_log_pii`), then ends with the `return
BuiltRequest(...)` shown below.

**`submit()`** gets only the live branch (proc:753-773). The `if not
self.dry_run:` guard is dropped — `create_request_from_form` already gates
`submit()` on dry-run. The original dry-run return (proc:774-785) is **not**
moved anywhere: the generic dry-run branch reproduces its result dict exactly
via `**built.summary` (which is why `summary` below carries `title`). Its two
extra log lines (`Type:`/`Identifier:`) are the only casualty — no test or CSV
field reads them.

```python
"""Lending request builder — behaviour moved unchanged from the processor."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from almaapitk import AlmaAPIError
from almaapitk.utils.citation_metadata import CitationMetadataError

# Cycle-safe: the processor never imports rs_requests at module level (every
# get_builder import is deferred into a method body), so importing its
# exception types here cannot create a circular import.
from resource_sharing_forms_processor import (
    IdentifierDetectionError,
    LendingRequestError,
    MetadataFetchError,
)

from rs_requests.base import BuiltRequest, RequestBuilder


class LendingRequestBuilder(RequestBuilder):
    kind = "lending"
    needs_metadata = False   # the toolkit enriches inside its own call

    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        # <<< proc:634-750 moved here with the self. → self.processor.
        # renames listed above. Do not alter any logic. Then: >>>
        return BuiltRequest(
            kind=self.kind,
            external_id=external_id,
            payload=params,
            summary={
                'detected_type': detected_type,
                # Preserves the pre-refactor dry-run result dict (and the
                # CSV Title column) byte for byte; the live path overrides
                # this with the real title in submit()'s return.
                'title': '[DRY-RUN - Not fetched]',
            },
        )

    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        # proc:753-773 with exactly the renames from the mapping table.
        params = built.payload
        try:
            request = self.processor.rs.create_lending_request_from_citation(**params)

            self.processor.logger.info(f"✓ Lending request created successfully")
            self.processor.logger.info(f"  Request ID: {request['request_id']}")
            self.processor.logger.info(f"  Title: {request.get('title', 'N/A')[:60]}")

            return {
                'status': 'success',
                'request_id': request['request_id'],
                'external_id': built.external_id,
                'detected_type': built.summary['detected_type'],
                'title': request.get('title', '')
            }
        except CitationMetadataError as e:
            raise MetadataFetchError(f"Metadata fetch failed: {e}")
        except AlmaAPIError as e:
            raise LendingRequestError(f"API error: {e}")
        except Exception as e:
            raise LendingRequestError(f"Unexpected error: {e}")
```

Then replace `create_lending_request_from_form` in the processor with:

```python
    def create_lending_request_from_form(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Kept as a thin shim so existing callers and tests are unaffected."""
        return self.create_request_from_form(form_data, kind="lending")
```

and add the generic entry point:

```python
    def create_request_from_form(self, form_data: Dict[str, Any],
                                 kind: str = "lending") -> Dict[str, Any]:
        from rs_requests import get_builder

        builder = get_builder(kind, processor=self)
        metadata = None
        if builder.needs_metadata:
            # Stamped onto form_data so summaries/reports can show the
            # detected type (GH #28).
            form_data["identifier_type"] = self.detect_identifier_type(
                form_data["identifier"])
            if self.dry_run:
                # Dry-run makes NO network calls — the project invariant the
                # lending path already honours (GH #20). Build against
                # placeholder metadata; the payload structure stays
                # inspectable for matrix T-10.
                from rs_requests.metadata import DRY_RUN_METADATA
                metadata = dict(DRY_RUN_METADATA)
            else:
                from rs_requests.metadata import fetch_citation_metadata
                metadata = fetch_citation_metadata(
                    form_data["identifier"], form_data["identifier_type"])
        built = builder.build(form_data, metadata)
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create {kind} request")
            self.logger.info(f"  External ID: {built.external_id}")
            # Full body to the file log only: lcc_number may carry a patron
            # name (GH #20 — this is also what matrix T-10 inspects).
            self._log_pii(logging.DEBUG,
                          f"  Payload: {built.payload}",
                          "  Payload: (recorded — see file log)")
            return {"status": "dry_run_success", "external_id": built.external_id,
                    **built.summary}
        return builder.submit(built)
```

- [ ] **Step 6: Run the full offline suite**

Run: `poetry run pytest -q`
Expected: all pass, **including** `test_l2_citation_golden.py` and
`test_lending_characterization.py`. If the golden test fails, the move was not
verbatim — revert and redo it.

- [ ] **Step 7: Commit**

```bash
git add rs_requests/ resource_sharing_forms_processor.py tests/test_builder_dispatch.py
git commit -m "refactor: extract request building behind a RequestBuilder interface"
```

---

### Task 3: Route a second input folder to the borrowing builder

**Files:**
- Modify: `resource_sharing_forms_processor.py` (`__init__`, `find_pending_tsv_files`, `process_single_run`, `process_watch_mode`)
- Modify: `config/rs_forms_config.example.json`
- Test: `tests/test_builder_dispatch.py` (extend)

**Interfaces:**
- Consumes: `get_builder(kind, processor=...)` from Task 2
- Produces: `find_pending_files() -> List[Tuple[Path, str]]` — each path paired with its request kind

- [ ] **Step 1: Write the failing test**

```python
from resource_sharing_forms_processor import ResourceSharingFormsProcessor
from tests.borrowing_fixtures import CONFIG


def _folders_cfg(tmp_path, lend, borrow=None, enabled=True):
    cfg = dict(CONFIG)
    cfg["file_processing"] = {
        "input_folder": str(lend),
        "processed_folder": str(tmp_path / "processed"),
        "output_dir": str(tmp_path / "output"),
    }
    if borrow is not None:
        cfg["file_processing"]["borrowing_input_folder"] = str(borrow)
    cfg["borrowing"] = {**cfg.get("borrowing", {}), "enabled": enabled}
    return cfg


def test_find_pending_files_tags_each_folder(tmp_path):
    lend = tmp_path / "input"; lend.mkdir()
    borrow = tmp_path / "input_borrowing"; borrow.mkdir()
    (lend / "a.tsv").write_text("x")
    (borrow / "b.tsv").write_text("y")

    proc = ResourceSharingFormsProcessor(
        _folders_cfg(tmp_path, lend, borrow), dry_run=True)

    found = dict((p.name, kind) for p, kind in proc.find_pending_files())
    assert found == {"a.tsv": "lending", "b.tsv": "borrowing"}


def test_disabled_borrowing_folder_is_not_scanned(tmp_path):
    """GH #29: parked files in a disabled folder must not generate a warning
    plus a report row every minute — they are excluded at scan time."""
    lend = tmp_path / "input"; lend.mkdir()
    borrow = tmp_path / "input_borrowing"; borrow.mkdir()
    (borrow / "b.tsv").write_text("y")
    proc = ResourceSharingFormsProcessor(
        _folders_cfg(tmp_path, lend, borrow, enabled=False), dry_run=True)
    assert [k for _, k in proc.find_pending_files()] == []


def test_borrowing_folder_is_optional(tmp_path):
    """A config without a borrowing folder must behave exactly as today."""
    lend = tmp_path / "input"; lend.mkdir()
    (lend / "a.tsv").write_text("x")
    proc = ResourceSharingFormsProcessor(
        _folders_cfg(tmp_path, lend), dry_run=True)
    assert [k for _, k in proc.find_pending_files()] == ["lending"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/test_builder_dispatch.py -v`
Expected: FAIL — `AttributeError: 'ResourceSharingFormsProcessor' object has no attribute 'find_pending_files'`

- [ ] **Step 3: Implement**

In `__init__`, after the existing `self.input_folder` assignment:

```python
        borrowing_folder = config['file_processing'].get('borrowing_input_folder')
        self.borrowing_input_folder = Path(borrowing_folder) if borrowing_folder else None
```

Add alongside `find_pending_tsv_files` (keep that method — it is still used by the lending-only path and by existing tests):

```python
    def find_pending_files(self) -> List[Tuple[Path, str]]:
        """Return (path, kind) for every pending TSV across both folders.

        The borrowing folder is optional: a config without it behaves exactly
        as the lending-only processor always has.
        """
        pending: List[Tuple[Path, str]] = [
            (p, 'lending') for p in self.find_pending_tsv_files()
        ]
        # Disabled borrowing (the shipped default) is excluded at scan time:
        # parked files must not churn a warning + log + report row per minute
        # (GH #29). The per-file guard in process_tsv_file remains as
        # second-line defence for files already routed when config flips.
        if self.borrowing_input_folder and self.borrowing_config.get('enabled', False):
            if not self.borrowing_input_folder.exists():
                self.logger.warning(
                    f"Borrowing input folder does not exist: {self.borrowing_input_folder}"
                )
            else:
                borrowing = sorted(self.borrowing_input_folder.glob('*.tsv'))
                if borrowing:
                    self.logger.debug(
                        f"Found {len(borrowing)} TSV files in {self.borrowing_input_folder}"
                    )
                else:
                    self.heartbeat_logger.debug(
                        f"Folder check: 0 TSV files in {self.borrowing_input_folder}"
                    )
                pending += [(p, 'borrowing') for p in borrowing]
        return pending
```

Add `Tuple` to the `typing` import line. Also add the `kind` parameter to
`process_tsv_file` **now**, as accepted-but-ignored
(`def process_tsv_file(self, file_path: Path, kind: str = 'lending') -> Dict[str, Any]:`
with no other change until Task 6) — otherwise the loops below would call it
with an argument that does not exist yet, leaving Tasks 3-5's commits
runtime-broken (GH #21).

Then change `process_single_run` to iterate the tagged scan:

```python
        for file_path, kind in self.find_pending_files():
            self.process_tsv_file(file_path, kind)
```

In `process_watch_mode`, the in-memory dedup set keys on bare `f.name` today;
a lending file and a borrowing file may legitimately share a filename (both
come from Power Automate), so key it on the kind as well (GH #30):

```python
            for file_path, kind in self.find_pending_files():
                token = f"{kind}:{file_path.name}"
                if token in self.processed_files:
                    continue
                self.process_tsv_file(file_path, kind)
                self.processed_files.add(token)
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest tests/test_builder_dispatch.py -q`
Expected: PASS

- [ ] **Step 5: Add the config block**

In `config/rs_forms_config.example.json`, add to `file_processing`:

```json
    "borrowing_input_folder": "./input_borrowing",
```

and a `borrowing` settings block at the top level:

```json
  "borrowing": {
    "enabled": false,
    "owner": "AM1",
    "pickup_location": "AM1",
    "pickup_location_type": "LIBRARY",
    "default_format": "DIGITAL",
    "default_citation_type": "CR",
    "requested_media": "7",
    "agree_to_copyright_terms": false,
    "lcc_number_template": "",
    "allowed_hospitals": ["ASAF", "BEIL", "IC", "LE", "ME", "SHEB", "SHH", "WOLF"]
  },
```

Append to the `notes` array:

```json
    "borrowing.enabled: master switch; false means borrowing files are ignored entirely",
    "borrowing scope (DECISION 2026-07-22): articles only — CR + DIGITAL. A material_type other than CR is rejected before any API call",
    "borrowing.agree_to_copyright_terms: OPEN — 98/100 real requests store false; confirm with SB test T-04 before changing",
    "borrowing.lcc_number_template: OPEN — pending the librarians. Placeholders: {hospital} {order_number} {patron_name}. Empty means omit the field",
    "borrowing.allowed_hospitals: proxy user codes; a file naming any other requestor is rejected before any API call"
```

Create the watched folder so a fresh clone works:

```bash
mkdir -p input_borrowing && touch input_borrowing/.gitkeep
# User data must never be committable (GH #23) — mirror the input/ rule:
echo 'input_borrowing/*.tsv' >> .gitignore
```

- [ ] **Step 6: Commit**

```bash
git add resource_sharing_forms_processor.py config/rs_forms_config.example.json \
        tests/test_builder_dispatch.py input_borrowing/.gitkeep .gitignore
git commit -m "feat: route a second input folder to the borrowing builder"
```

---

### Task 4: Parse the borrowing TSV

Only two columns are settled: **requestor** (hospital proxy user code) and
**identifier** (PMID or DOI). Others are TBD, so the parser is driven by a
column map in config — adding a column later is a config edit, not a code
change.

**Files:**
- Modify: `resource_sharing_forms_processor.py` (add `read_borrowing_tsv_file`)
- Modify: `config/rs_forms_config.example.json`
- Test: `tests/test_borrowing_tsv.py` (create)

**Interfaces:**
- Consumes: `self.borrowing_config` (Task 3)
- Produces: `read_borrowing_tsv_file(path) -> dict` with keys `filename`, `filepath`, `requestor`, `identifier`, `notes`, `material_type`, `order_number`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from resource_sharing_forms_processor import (
    ResourceSharingFormsProcessor, FileProcessingError,
)


from tests.borrowing_fixtures import CONFIG


def _proc(tmp_path, columns=None):
    cfg = dict(CONFIG)
    cfg["file_processing"] = {
        "input_folder": str(tmp_path / "input"),
        "borrowing_input_folder": str(tmp_path / "input_borrowing"),
        "processed_folder": str(tmp_path / "processed"),
        "output_dir": str(tmp_path / "output"),
    }
    cfg["borrowing"] = {
        "enabled": True,
        "allowed_hospitals": ["SHEB", "BEIL"],
        "columns": columns or {"requestor": 0, "identifier": 1,
                               "notes": 2, "material_type": 3, "order_number": 4},
    }
    (tmp_path / "input").mkdir(exist_ok=True)
    (tmp_path / "input_borrowing").mkdir(exist_ok=True)
    return ResourceSharingFormsProcessor(cfg, dry_run=True)


def test_parses_the_two_settled_columns(tmp_path):
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("SHEB\t33219451\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["requestor"] == "SHEB"
    assert data["identifier"] == "33219451"
    assert data["notes"] == ""
    assert data["material_type"] == ""


def test_parses_optional_columns_when_present(tmp_path):
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("BEIL\t10.1038/x\turgent\tBK\tOrder_9\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["material_type"] == "BK"
    assert data["order_number"] == "Order_9"


def test_rejects_unknown_hospital(tmp_path):
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("NOTAHOSPITAL\t33219451\n", encoding="utf-8")
    with pytest.raises(FileProcessingError, match="not a configured hospital"):
        _proc(tmp_path).read_borrowing_tsv_file(f)


def test_rejects_missing_identifier(tmp_path):
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("SHEB\t\n", encoding="utf-8")
    with pytest.raises(FileProcessingError, match="identifier is empty"):
        _proc(tmp_path).read_borrowing_tsv_file(f)


def test_column_positions_are_config_driven(tmp_path):
    """A future Power Automate change must be a config edit, not a code edit."""
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("33219451\tSHEB\n", encoding="utf-8")
    proc = _proc(tmp_path, columns={"identifier": 0, "requestor": 1})
    data = proc.read_borrowing_tsv_file(f)
    assert data["requestor"] == "SHEB"
    assert data["identifier"] == "33219451"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/test_borrowing_tsv.py -v`
Expected: FAIL — no attribute `read_borrowing_tsv_file`

- [ ] **Step 3: Implement**

In `__init__`:

```python
        self.borrowing_config = config.get('borrowing', {}) or {}
```

Add the method next to `read_tsv_file`:

```python
    #: Only `requestor` and `identifier` are settled with the Power Automate
    #: side. Everything else is optional and defaults to empty.
    #: 'patron_name' is deliberately absent (GH #17): once the librarians
    #: answer the lcc_number question (guidebook §4.5), adding
    #: {"patron_name": <idx>} to config['borrowing']['columns'] activates it
    #: end-to-end — a config edit, not a code change.
    DEFAULT_BORROWING_COLUMNS = {
        'requestor': 0, 'identifier': 1, 'notes': 2,
        'material_type': 3, 'order_number': 4,
    }

    def read_borrowing_tsv_file(self, file_path: Path) -> Dict[str, Any]:
        """Read and parse a borrowing TSV file.

        Column positions come from config so that a change on the Power
        Automate side is a config edit rather than a code change.
        """
        columns = {**self.DEFAULT_BORROWING_COLUMNS,
                   **(self.borrowing_config.get('columns') or {})}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                rows = [r for r in csv.reader(f, delimiter='\t')
                        if r and any(c.strip() for c in r)]
        except Exception as e:
            raise FileProcessingError(f"Error reading TSV file {file_path.name}: {e}")

        if not rows:
            raise FileProcessingError(f"TSV file is empty: {file_path.name}")
        row = rows[0]

        def cell(name: str) -> str:
            idx = columns.get(name)
            if idx is None or idx >= len(row):
                return ''
            return row[idx].strip()

        data = {
            'filename': file_path.stem,
            'filepath': file_path,
            # Stable across retries (GH #13): derived from the file's mtime,
            # not wall-clock. Error files stay in place untouched, so every
            # retry of the same file sees the same token.
            'file_token': datetime.fromtimestamp(
                file_path.stat().st_mtime).strftime('%d%m%Y%H%M%S'),
            'requestor': cell('requestor'),
            'identifier': cell('identifier'),
            'notes': cell('notes'),
            'material_type': cell('material_type').upper(),
            'order_number': cell('order_number'),
            # Unmapped by default (no index in DEFAULT_BORROWING_COLUMNS), so
            # this is '' until config maps it — see the columns note (GH #17).
            'patron_name': cell('patron_name'),
        }

        allowed = self.borrowing_config.get('allowed_hospitals') or []
        if not data['requestor']:
            raise FileProcessingError(f"requestor is empty in {file_path.name}")
        if allowed and data['requestor'] not in allowed:
            raise FileProcessingError(
                f"'{data['requestor']}' is not a configured hospital "
                f"in {file_path.name}. Allowed: {', '.join(allowed)}"
            )
        if not data['identifier']:
            raise FileProcessingError(f"identifier is empty in {file_path.name}")

        self.logger.debug(f"Parsed borrowing TSV: {file_path.name}")
        self.logger.debug(f"  Requestor: {data['requestor']}")
        self.logger.debug(f"  Identifier: {data['identifier']}")
        self.logger.debug(f"  Material type: {data['material_type'] or '(default)'}")
        return data
```

Add to the example config's `borrowing` block:

```json
    "columns": {"requestor": 0, "identifier": 1, "notes": 2, "material_type": 3, "order_number": 4},
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest tests/test_borrowing_tsv.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add resource_sharing_forms_processor.py config/rs_forms_config.example.json \
        tests/test_borrowing_tsv.py
git commit -m "feat: parse borrowing TSV with config-driven column positions"
```

---

### Task 5: Build the borrowing payload

The core of the work. Every value traces to `docs/BORROWING_REQUESTS.md` §4
and §9. The body itself is assembled by `almaapitk.build_user_rs_request`
(Task 0's floor) — this builder owns *what* to send; the toolkit owns *how*
to shape it.

**Files:**
- Create: `rs_requests/metadata.py`, `rs_requests/borrowing.py`
- Test: `tests/test_borrowing_builder.py` (create)

**Interfaces:**
- Consumes: `BuiltRequest`, `RequestBuilder` (Task 2); `read_borrowing_tsv_file` output (Task 4); `almaapitk.build_user_rs_request` (Task 0, >= 0.5.0)
- Produces:
  - `fetch_citation_metadata(identifier: str, id_type: str) -> Dict[str, str]` with keys `title, author, journal, year, volume, issue, pages, start_page, end_page, issn, isbn, doi, pmid, publisher`
  - `BorrowingRequestBuilder.build(form_data, metadata) -> BuiltRequest`

- [ ] **Step 1: Write the failing test**

First extend `tests/borrowing_fixtures.py` (created in Task 1 — GH #22) with
the canonical borrowing metadata; defining it once prevents the cross-file
`NameError` of GH issue #12. Append:

```python
# --- canonical borrowing metadata (GH #12) ---------------------------------

META = {
    "title": "A distinctive article title", "author": "Testerson, A.",
    "journal": "Journal of Diagnostics", "year": "2024", "volume": "12",
    "issue": "3", "pages": "101-115", "start_page": "101", "end_page": "115",
    "issn": "0000-0000", "isbn": "", "doi": "10.9999/x", "pmid": "33219451",
    "publisher": "Sandbox Press",
}

FORM = {"requestor": "SHEB", "identifier": "33219451", "notes": "",
        "material_type": "", "order_number": "Order_9", "filename": "r",
        "file_token": "20072026143205"}
```

Then `tests/test_borrowing_builder.py`:

```python
import pytest
import requests

from almaapitk import AlmaAPIError

from rs_requests.borrowing import BorrowingRequestBuilder, BorrowingValidationError
from tests.borrowing_fixtures import FORM, META


class FakeProcessor:
    dry_run = True
    users = None          # set by _builder_with() for the submit() tests
    borrowing_config = {
        "owner": "AM1", "pickup_location": "AM1",
        "pickup_location_type": "LIBRARY", "default_format": "DIGITAL",
        "default_citation_type": "CR", "requested_media": "7",
        "agree_to_copyright_terms": False, "lcc_number_template": "",
    }
    class logger:
        @staticmethod
        def info(*a, **k): pass
        @staticmethod
        def debug(*a, **k): pass
        @staticmethod
        def warning(*a, **k): pass
    def _log_pii(self, *a, **k): pass


def _build(form=None, meta=None, config=None):
    proc = FakeProcessor()
    if config:
        proc.borrowing_config = {**FakeProcessor.borrowing_config, **config}
    return BorrowingRequestBuilder(proc).build({**FORM, **(form or {})},
                                               {**META, **(meta or {})})


def _builder_with(users):
    """A builder whose processor exposes the given (fake) Users client."""
    proc = FakeProcessor()
    proc.users = users
    return BorrowingRequestBuilder(proc)


def test_constants_match_the_verified_template():
    p = _build().payload
    assert p["owner"] == "AM1"                       # plain string
    assert p["pickup_location"] == {"value": "AM1"}  # wrapped
    assert p["pickup_location_type"] == "LIBRARY"
    assert p["requested_media"] == "7"
    assert p["allow_other_formats"] is False
    assert p["willing_to_pay"] is False


def test_defaults_to_digital_article():
    p = _build().payload
    assert p["format"] == {"value": "DIGITAL"}
    assert p["citation_type"] == {"value": "CR"}


def test_material_type_bk_is_rejected():
    """DECISION 2026-07-22: articles only. BK is out of scope until the
    PHYSICAL+BOOK SANDBOX 500 (AlmaAPITK #207) is decomposed and a book
    recipe is proven live."""
    with pytest.raises(BorrowingValidationError, match="out of scope"):
        _build(form={"material_type": "BK"})


def test_rejects_electronic_citation_codes():
    """E_CR is accepted at create but DISCARDS journal_title/issue/doi/pmid
    at persist (A/B probe 2026-07-22, guidebook §9) — and appears in 0 of
    1912 real requests."""
    with pytest.raises(BorrowingValidationError, match="E_CR"):
        _build(form={"material_type": "E_CR"})


def test_article_requires_journal_author_year():
    with pytest.raises(BorrowingValidationError, match="journal_title"):
        _build(meta={"journal": ""})


def test_omits_partner_mms_id_and_oclc_number():
    p = _build().payload
    for absent in ("partner", "mms_id", "oclc_number",
                   "level_of_service", "copyright_status"):
        assert absent not in p


def test_external_id_is_stable_and_identifies_the_source():
    """Same file → same id on every retry (GH #13); no wall-clock component."""
    a = _build().external_id
    b = _build().external_id
    assert a == b == "FORMS-BR-SHEB-20072026143205-r-Order_9"


def test_lcc_number_omitted_when_template_empty():
    assert "lcc_number" not in _build().payload


def test_lcc_number_rendered_from_template():
    p = _build(config={"lcc_number_template": "{hospital}-TAU-{order_number}"}).payload
    assert p["lcc_number"] == "SHEB-TAU-Order_9"


def test_copyright_flag_is_config_driven():
    assert _build().payload["agree_to_copyright_terms"] is False
    assert _build(config={"agree_to_copyright_terms": True}
                  ).payload["agree_to_copyright_terms"] is True


def test_empty_metadata_fields_are_omitted_not_sent_blank():
    p = _build(meta={"isbn": "", "publisher": ""}).payload
    assert "isbn" not in p
    assert "publisher" not in p


# --- submit(): a failed create must never be blind-retried -------------------

class _FakeUsers:
    """Users stand-in whose create always raises exc (failure-path tests)."""

    def __init__(self, exc=None):
        self.creates = 0
        self.exc = exc if exc is not None else AlmaAPIError("HTTP 500")

    def create_user_rs_request(self, user_id, request_data, **kw):
        self.creates += 1
        self.last_kwargs = kw
        raise self.exc


def _alma_error(message, code=""):
    e = AlmaAPIError(message)
    e.alma_code = code
    return e


def test_duplicate_rejection_means_already_created():
    """402362 = an identical active request exists — most importantly when a
    previous run's create timed out AFTER saving. DECISION 2026-07-20
    (GH #35): report done, never blind-retry."""
    users = _FakeUsers(exc=_alma_error(
        "Failed to save the request: Patron has duplicate request", "402362"))
    result = _builder_with(users).submit(_build())
    assert result["status"] == "duplicate"
    assert result["request_id"] == ""
    assert users.creates == 1


def test_duplicate_rejection_matches_by_message_when_code_missing():
    users = _FakeUsers(exc=_alma_error(
        "Failed to save the request: Patron has duplicate request"))
    assert _builder_with(users).submit(_build())["status"] == "duplicate"


def test_other_api_errors_reraise():
    users = _FakeUsers(exc=_alma_error(
        "Patron is not affiliated with a resource sharing library", "401768"))
    with pytest.raises(AlmaAPIError):
        _builder_with(users).submit(_build())
    assert users.creates == 1        # never internally retried
    # The opt-in pre-flight (almaapitk >= 0.5.0) must be on for every create.
    assert users.last_kwargs.get("validate") is True


def test_transport_timeout_reraises_for_the_next_scheduled_run():
    """almaapitk does not wrap transport errors (GH #9; re-verified on the
    2026-07-22 main); a socket timeout must propagate. The file then stays
    in input, the next run
    re-POSTs, and if this create actually saved Alma rejects it 402362 —
    which the duplicate branch converts to done."""
    users = _FakeUsers(exc=requests.exceptions.ReadTimeout("read timed out"))
    with pytest.raises(requests.exceptions.ReadTimeout):
        _builder_with(users).submit(_build())
    assert users.creates == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/test_borrowing_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rs_requests.borrowing'`

- [ ] **Step 3: Write the metadata adapter**

`rs_requests/metadata.py`. **First** confirm the toolkit's actual signatures:

```bash
poetry run python -c "import inspect, almaapitk.utils.citation_metadata as m; print([n for n in dir(m) if not n.startswith('_')]); print(inspect.signature(m.get_pubmed_metadata)); print(inspect.signature(m.get_crossref_metadata))"
```

Then adapt the two calls below to match what it prints. Everything downstream
depends only on this module's normalised output, so a signature difference is
contained here.

**Known key drift — do not assume `FIELDS` is satisfied.** The toolkit emits
`pages` and has no `start_page`/`end_page`; the split is derived below. More
importantly, `issn` / `isbn` / `publisher` / `pmid` are *not* confirmed to be
emitted by either helper, and the `raw.get(k, "")` below fails silently — a
missing key is indistinguishable from an empty value. Before writing this
module, print an actual result from each source:

```bash
poetry run python -c "import almaapitk.utils.citation_metadata as m; print(sorted(m.get_pubmed_metadata('33301246'))); print(sorted(m.get_crossref_metadata('10.1038/nature12373')))"
```

Any name in `FIELDS` absent from *both* outputs must either be dropped from
`FIELDS` or mapped from the key the toolkit actually uses. Do not leave a field
in `FIELDS` that can only ever be empty — the borrowing payload would then omit
it without anything reporting why.

```python
"""Citation metadata, normalised to one internal shape.

The toolkit's PubMed and Crossref helpers return slightly different keys.
Everything downstream consumes this module's output, so any upstream change
is absorbed in one place.
"""
from __future__ import annotations

from typing import Any, Dict

from almaapitk.utils.citation_metadata import (
    CitationMetadataError, get_crossref_metadata, get_pubmed_metadata,
)

# isbn is NOT in FIELDS: neither toolkit helper extracts it (verified against
# 0.4.6 — GH #18); a name that can only ever be empty must not pretend to be
# part of the normalised shape.
FIELDS = ("title", "author", "journal", "year", "volume", "issue", "pages",
          "start_page", "end_page", "issn", "doi", "pmid", "publisher")

#: Placeholder metadata used when building in dry-run: no network calls
#: happen (GH #20), but the payload keeps a valid, inspectable structure.
#: Mirrors the lending path's '[DRY-RUN - Not fetched]' convention.
DRY_RUN_METADATA = {
    "title": "[DRY-RUN - Not fetched]",
    "author": "[DRY-RUN]",
    "journal": "[DRY-RUN]",
    "year": "[DRY-RUN]",
}


def fetch_citation_metadata(identifier: str, id_type: str) -> Dict[str, str]:
    """Fetch and normalise citation metadata for a PMID or DOI."""
    if id_type == "pmid":
        raw: Dict[str, Any] = get_pubmed_metadata(identifier)
    elif id_type == "doi":
        raw = get_crossref_metadata(identifier)
    else:
        raise CitationMetadataError(f"unsupported identifier type: {id_type!r}")

    out = {k: str(raw.get(k, "") or "").strip() for k in FIELDS}
    # Alma stores page range both whole and split; derive the split when the
    # source only gives the range.
    if out["pages"] and not out["start_page"]:
        parts = out["pages"].replace("--", "-").split("-", 1)
        out["start_page"] = parts[0].strip()
        out["end_page"] = parts[1].strip() if len(parts) > 1 else ""
    return out
```

- [ ] **Step 4: Write the borrowing builder**

`rs_requests/borrowing.py`:

```python
"""Borrowing (user resource-sharing) request builder.

Field values trace to docs/BORROWING_REQUESTS.md §4 (1912 real SANDBOX
requests, 100 read in full) and §9 (live upstream evidence, 2026-07-22). Do
not change a value without updating that document and the evidence behind it.

The wire shape is assembled by almaapitk.build_user_rs_request (>= 0.5.0),
which encodes Alma's plain-vs-{"value": ...} wrapping rules once, upstream.
This module owns WHAT to send; the toolkit owns HOW to shape it.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from almaapitk import AlmaAPIError, build_user_rs_request

from rs_requests.base import BuiltRequest, RequestBuilder


class BorrowingValidationError(Exception):
    """Raised before any API call when the request cannot be valid."""


#: DECISION 2026-07-22 — articles only. CR is the librarians' UI value and
#: the live-proven shape (DIGITAL+CR, guidebook §9). BK is out of scope
#: (PHYSICAL+BOOK reproducibly 500s in SANDBOX — AlmaAPITK #207); E_CR is
#: accepted at create but DISCARDS journal_title/issue/doi/pmid at persist
#: (A/B probe 2026-07-22) and appears in 0 of 1912 real requests.
ALLOWED_CITATION_TYPES = ("CR",)


class BorrowingRequestBuilder(RequestBuilder):
    kind = "borrowing"
    needs_metadata = True     # the processor enriches before calling build()

    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        cfg = self.processor.borrowing_config
        meta = metadata or {}

        citation_type = (form_data.get("material_type")
                         or cfg.get("default_citation_type", "CR")).upper()
        if citation_type not in ALLOWED_CITATION_TYPES:
            raise BorrowingValidationError(
                f"citation_type {citation_type!r} is out of scope: this "
                f"pipeline creates DIGITAL article requests only "
                f"(DECISION 2026-07-22). Allowed: "
                f"{', '.join(ALLOWED_CITATION_TYPES)}."
            )

        title = meta.get("title", "").strip()
        if not title:
            raise BorrowingValidationError("citation metadata has no title")

        # Every request is an article — the trio is unconditionally
        # mandatory (Alma 401930, confirmed live 2026-07-22).
        missing = [name for name, key in
                   (("journal_title", "journal"), ("author", "author"), ("year", "year"))
                   if not meta.get(key, "").strip()]
        if missing:
            raise BorrowingValidationError(
                f"an article request requires {', '.join(missing)} "
                f"(Alma returns alma_code 401930 without them)"
            )

        hospital = form_data["requestor"]
        order_number = (form_data.get("order_number") or "").strip()
        # Stable across retries (GH #13): the token is the input file's mtime
        # (stamped by the reader), and the sanitized stem is unique among
        # concurrently pending files (a directory cannot hold two files with
        # one name). Same file → same id in every log line and report row, so
        # a retry is traceable to its earlier attempts. Alma does NOT store
        # this id (GH #14) — duplicate safety is Alma's 402362 rejection, see
        # submit().
        token = (form_data.get("file_token") or "").strip()
        if not token:
            raise BorrowingValidationError(
                "file_token missing from form data — reader must stamp it"
            )
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", form_data.get("filename") or "")[:40]
        external_id = f"FORMS-BR-{hospital}-{token}-{stem}"
        if order_number:
            external_id = f"{external_id}-{order_number}"

        # --- extra: everything build_user_rs_request has no kwarg for ----
        # Constants: 100/100 in the verified sample (guidebook §4.1). The
        # builder applies its wrapping rules to `extra` too, so plain values
        # here stay correct even if a field is reclassified upstream.
        extra: Dict[str, Any] = {
            "requested_media": cfg.get("requested_media", "7"),
            "allow_other_formats": False,
            "willing_to_pay": False,
        }

        # Bibliographic fields: included only when non-empty ("" must be
        # omitted, not sent blank). isbn is not mapped: neither toolkit
        # metadata helper can produce it (GH #18); reinstate only after
        # almaapitk grows ISBN extraction.
        for key, source in (("volume", "volume"), ("issue", "issue"),
                            ("pages", "pages"), ("start_page", "start_page"),
                            ("end_page", "end_page"), ("issn", "issn"),
                            ("doi", "doi"), ("pmid", "pmid"),
                            ("publisher", "publisher")):
            value = (meta.get(source) or "").strip()
            if value:
                extra[key] = value

        note = (form_data.get("notes") or "").strip()
        if note:
            extra["note"] = note

        template = (cfg.get("lcc_number_template") or "").strip()
        if template:
            extra["lcc_number"] = template.format(
                hospital=hospital,
                order_number=order_number,
                patron_name=(form_data.get("patron_name") or "").strip(),
            ).strip()

        # Deliberately NOT sent — see docs/BORROWING_REQUESTS.md:
        #   external_id   Alma discards the client value and substitutes a
        #                 broker id (972TAU…) — GH #14, re-confirmed upstream
        #                 2026-07-22. The local FORMS-BR-… id above exists
        #                 only for logs, reports and file correlation.
        #   partner       assigned by the rota after creation
        #   mms_id        Alma generates a placeholder bib from this metadata
        #   oclc_number   written by the supplier, not the requester
        #   level_of_service / copyright_status  empty in 100/100

        # The toolkit builder owns the wire shape: owner plain,
        # format/citation_type/pickup_location wrapped {"value": ...},
        # pickup_location_type plain (the §4.1 asymmetry, encoded once
        # upstream — AlmaAPITK PR #206, live-proven 2026-07-22). The trio
        # below was validated non-empty above, so the builder's
        # _require_rs_text guards cannot fire here.
        payload = build_user_rs_request(
            owner=cfg.get("owner", "AM1"),
            format=cfg.get("default_format", "DIGITAL"),
            citation_type=citation_type,
            title=title,
            journal_title=meta.get("journal", "").strip(),
            author=meta.get("author", "").strip(),
            year=meta.get("year", "").strip(),
            pickup_location=cfg.get("pickup_location", "AM1"),
            pickup_location_type=cfg.get("pickup_location_type", "LIBRARY"),
            agree_to_copyright_terms=bool(cfg.get("agree_to_copyright_terms", False)),
            extra=extra,
        )

        return BuiltRequest(
            kind=self.kind,
            external_id=external_id,
            payload=payload,
            summary={"detected_type": form_data.get("identifier_type", ""),
                     "title": title, "requestor": hospital,
                     "citation_type": citation_type},
        )

    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        # The processor already wires a Users client (see the processor's
        # __init__); reuse it rather than constructing a second one.
        users = self.processor.users
        hospital = built.summary["requestor"]
        try:
            # validate=True (almaapitk >= 0.5.0): a wrong code-table value
            # raises AlmaValidationError naming the field BEFORE any HTTP.
            response = users.create_user_rs_request(
                hospital, built.payload, validate=True)
        except AlmaAPIError as e:
            if self._is_duplicate_rejection(e):
                # DECISION 2026-07-20 (GH #35): Alma's duplicate check IS the
                # safety mechanism. This fires when an identical request is
                # already active for this patron — most importantly when a
                # previous run's create timed out AFTER saving. Treat as
                # already created: report it and let the file move out of
                # input, ending the retry loop.
                self.processor.logger.warning(
                    f"  Alma rejected as duplicate (402362): an identical "
                    f"active request already exists for {hospital} — "
                    f"treating as already created."
                )
                return {"status": "duplicate",
                        "request_id": "",   # unknowable — Alma doesn't say which
                        "external_id": built.external_id, **built.summary}
            raise
        # requests.RequestException (socket timeout, connection reset) is
        # deliberately NOT caught: almaapitk does not wrap transport errors
        # (GH #9; re-verified on the 2026-07-22 main), and re-raising is
        # correct here — the file stays in
        # input, the next scheduled run re-POSTs, and if this create actually
        # saved, Alma answers 402362 and the branch above finishes the job.
        data = response.data or {}
        self.processor.logger.info("✓ Borrowing request created")
        self.processor.logger.info(f"  Request ID: {data.get('request_id')}")
        return {"status": "success", "request_id": data.get("request_id"),
                "external_id": built.external_id, **built.summary}

    @staticmethod
    def _is_duplicate_rejection(e: AlmaAPIError) -> bool:
        """True when Alma refused the create because an identical request is
        already active for this patron (verified live 2026-07-20, GH #35).

        alma_code is the structural match; the message fallback covers error
        bodies the toolkit could not parse into a code. The substring match
        is unaffected by the ``[almaapitk hint: ...]`` suffix that >= 0.5.0
        appends to some unrenderable Alma 400s.
        """
        if getattr(e, "alma_code", "") == "402362":
            return True
        return "patron has duplicate request" in str(e).lower()
```

**Decision record — 2026-07-20 (GH #35).** Reconcile-by-external_id was
removed after two live SANDBOX probes replaced assumptions with facts:

1. **`external_id` sent on POST is discarded.** Alma substitutes a broker id
   (`972TAU…`) in the create response itself; a
   `request_id_type="external"` lookup for our value returns
   *"No result found for given parameters"* — indistinguishable from
   never-created (GH #14; probe request `39940249320004146`, cancelled).
   Re-confirmed independently 2026-07-22 (upstream hospital-format demo:
   sent `"99990001"`, came back empty on GET — guidebook §9). The upstream
   builder's docstring pitching `external_id` as an idempotency key is
   wrong for this surface; we never pass it.
2. **An identical re-POST while the original is active fails with alma_code
   `402362`** *"Patron has duplicate request"* (probe request
   `39940250330004146`, cancelled). This is the duplicate-safety mechanism.

Scope and dependencies (Ex Libris FAQ + probes):

- Duplicate = same user + citation fields ("Title, ISBN, Volume…" — not
  exhaustively documented; an identical rebuilt body is the verified case).
- **Active requests only** — completed/cancelled requests do not block, so
  legitimate re-requests keep working.
- Controlled by customer parameter
  `check_patron_duplicate_borrowing_requests` — **false by default**; TAU has
  it enabled, which is why the sandbox rejects.

**Go-live preconditions:** (1) RS librarians confirm the parameter is `true`
in PRODUCTION config; (2) accepted residual risk (user decision, 2026-07-20):
a retry whose rebuilt body differs — e.g. upstream metadata drift between
runs — could escape the check. Judged low-probability and acceptable.

- [ ] **Step 5: Run to verify it passes**

Run: `poetry run pytest tests/test_borrowing_builder.py -v`
Expected: PASS (15 tests)

- [ ] **Step 6: Run the whole offline suite**

Run: `poetry run pytest -q`
Expected: everything green, lending golden included.

- [ ] **Step 7: Commit**

```bash
git add rs_requests/metadata.py rs_requests/borrowing.py tests/test_borrowing_builder.py tests/borrowing_fixtures.py
git commit -m "feat: build borrowing request payloads from the verified field template"
```

---

### Task 6: Wire borrowing into the pipeline, dry-run only

**Files:**
- Modify: `resource_sharing_forms_processor.py` (`process_tsv_file`, `generate_csv_report`, `_write_file_processing_log`, `_append_daily_report`)
- Test: `tests/test_borrowing_tsv.py` (extend)

**Interfaces:**
- Consumes: everything from Tasks 3–5
- Produces: `process_tsv_file(file_path, kind='lending') -> dict` including a `kind` key in every result

- [ ] **Step 1: Write the failing test**

```python
def test_end_to_end_dry_run_builds_a_payload(tmp_path):
    """A borrowing file produces a dry-run result with NO network call —
    dry-run builds against placeholder metadata (GH #20), so nothing needs
    monkeypatching."""
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("SHEB\t33219451\n", encoding="utf-8")

    proc = _proc(tmp_path)
    result = proc.process_tsv_file(f, kind="borrowing")
    assert result["status"] == "dry_run_success"
    assert result["kind"] == "borrowing"
    assert result["requestor"] == "SHEB"
    assert result["detected_type"] == "pmid"     # stamped in the pipeline (GH #28)


def test_disabled_borrowing_skips_the_file(tmp_path):
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("SHEB\t33219451\n", encoding="utf-8")
    proc = _proc(tmp_path)
    proc.borrowing_config = {**proc.borrowing_config, "enabled": False}
    result = proc.process_tsv_file(f, kind="borrowing")
    assert result["status"] == "skipped"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/test_borrowing_tsv.py -v`
Expected: FAIL — `kind` is accepted but ignored (a no-op since Task 3,
GH #21), so the borrowing file is parsed by the *lending* reader: the result
is `status='error'` with no `kind` key and the first assertion fails.

- [ ] **Step 3: Implement**

The signature already accepts `kind` (a no-op since Task 3 — GH #21); now
honour it. At the top of the body — **before the `try`** (this check cannot
raise, so it is safe outside error isolation):

```python
        if kind == 'borrowing' and not self.borrowing_config.get('enabled', False):
            self.logger.warning(
                f"Borrowing is disabled in config; skipping {file_path.name}"
            )
            return {'status': 'skipped', 'kind': kind,
                    'filename': file_path.name,
                    'error_message': 'borrowing disabled in config'}
```

Then, **inside the `try`**, replace the existing read + `result.update` block.
The current block direct-indexes `form_data['partner_code']`, `user_name`,
`user_id`, `is_faculty` — keys that do not exist in borrowing form data, so
leaving it unbranched raises `KeyError` on every borrowing file, swallowed by
the generic `except Exception` into a misleading `status='error'` (GH issue #10):

```python
            if kind == 'borrowing':
                form_data = self.read_borrowing_tsv_file(file_path)
                result.update({
                    # No partner at create time — the rota assigns one later.
                    'partner_code': '',
                    'user_name': '',
                    # The hospital proxy code IS the requesting user of a
                    # borrowing request; surfacing it as user_id lands it in
                    # the reports' existing Requestor_ID column.
                    'user_id': form_data['requestor'],
                    'is_faculty': '',
                    'requestor': form_data['requestor'],
                    'identifier': form_data['identifier'],
                    'order_number': form_data['order_number']
                })
            else:
                form_data = self.read_tsv_file(file_path)
                result.update({
                    'partner_code': form_data['partner_code'],
                    'user_name': form_data['user_name'],
                    'user_id': form_data['user_id'],
                    'is_faculty': form_data['is_faculty'],
                    'identifier': form_data['identifier'],
                    'order_number': form_data['order_number']
                })
```

Route the terminal call through `self.create_request_from_form(form_data, kind=kind)`
and add `'kind': kind` to every returned result dict.

Extend the except ladder with the two exception types only the borrowing path
raises, inserted **before** the generic `except Exception`, keeping lending's
semantics (validation problems are permanent → `skipped`; fetch problems →
`error`):

```python
        except BorrowingValidationError as e:
            self.logger.error(f"✗ Borrowing validation error: {e}")
            result['status'] = 'skipped'
            result['error_message'] = str(e)

        except CitationMetadataError as e:
            self.logger.error(f"✗ Metadata fetch error: {e}")
            result['status'] = 'error'
            result['error_message'] = str(e)
```

`CitationMetadataError` is already imported at the top of the processor (the
lending path never lets it escape — it wraps it in `MetadataFetchError` — so
this clause only ever fires for borrowing). Import `BorrowingValidationError`
from `rs_requests.borrowing` alongside the processor's other imports.

Add a `Kind` column to the CSV report header in `generate_csv_report` and
`_append_daily_report`, populated from `result.get('kind', 'lending')`. Both
writers already use `result.get(...)` with defaults, so the empty
lending-specific fields of borrowing rows need no further handling.

Extend the move-to-processed condition with the `duplicate` status (the
DECISION 2026-07-20 outcome — Alma confirmed the request already exists, so
the file is done and must leave the input folder or it retries forever):

```python
            if result['status'] in ['success', 'dry_run_success', 'duplicate']:
                self.move_to_processed(file_path)
```

`duplicate` rows appear in the CSV with an empty `Request_ID` — Alma's 402362
rejection does not say which existing request matched.

`401604` ("institutional inventory has services for the requested title")
needs **no dedicated branch**: it arrives as a generic `AlmaAPIError`, is not
a duplicate, so it re-raises out of `submit()` into the existing generic
handler → `status='error'` row. That is the decided policy (2026-07-22:
never pass `override_blocks`); the file stays in `input_borrowing/` for
manual handling, like any other errored file.

Finally, give the shared client the generous timeout the matrix mandates
(GH #19) — a borrowing create can exceed the 60s default **and still save**,
which is exactly the scenario the 402362 recovery exists for. At the client
construction (`resource_sharing_forms_processor.py:163`):

```python
            self.client = AlmaAPIClient(
                self.environment,
                timeout=int(config.get('api_timeout_seconds', 180)),
            )
```

and add `"api_timeout_seconds": 180` at the top level of
`config/rs_forms_config.example.json`. The lending path shares this client;
a longer ceiling is strictly safer for its creates too.

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add resource_sharing_forms_processor.py tests/test_borrowing_tsv.py
git commit -m "feat: process borrowing files end to end in dry-run"
```

---

### Task 7: Mask the patron name in `lcc_number`

`lcc_number` may carry a patron's name. The repo already masks `user_id` on
console output; this extends the same guarantee.

**Files:**
- Modify: `resource_sharing_forms_processor.py` (`PiiConsoleFilter`)
- Test: `tests/test_pii_logging.py` (extend)

**Interfaces:**
- Consumes: existing `mask_user_id`, `PiiConsoleFilter`, `_log_pii`
- Produces: `mask_lcc_number(value: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
from resource_sharing_forms_processor import mask_lcc_number


def test_mask_keeps_structure_drops_the_name():
    assert mask_lcc_number("SHEBA-TAU-1680 Some Patron") == "SHEBA-TAU-1680 ***"


def test_mask_handles_this_repos_order_number_shapes():
    """GH #16: order numbers here are 'Order_…', not digits — the mask must
    still catch the name that follows them."""
    assert mask_lcc_number("SHEB-TAU-Order_9 David Levi") == "SHEB-TAU-Order_9 ***"
    assert (mask_lcc_number("SHEB-TAU-Order_Num_24586 Some Patron")
            == "SHEB-TAU-Order_Num_24586 ***")


def test_mask_leaves_nameless_conventions_intact():
    assert mask_lcc_number("BEIL248; 20233913") == "BEIL248; 20233913"
    assert mask_lcc_number("IC2055") == "IC2055"


def test_mask_handles_empty():
    assert mask_lcc_number("") == ""
    assert mask_lcc_number(None) == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/test_pii_logging.py -v`
Expected: FAIL — cannot import `mask_lcc_number`

- [ ] **Step 3: Implement**

Next to `mask_user_id`:

```python
def mask_lcc_number(value: Optional[str]) -> str:
    """Mask the patron-name tail of an lcc_number, keeping its structure.

    The observed conventions are '<HOSP>-TAU-<n> <patron name>',
    '<HOSP><n>; <n>' and '<HOSP><n>'. Only the first carries a name, as the
    segment following the first space after a digit run.
    """
    if not value:
        return ""
    # The prefix segment is NOT digits-only: this repo's order numbers look
    # like 'Order_Num_24586' (GH #16), so the rendered template can be
    # 'SHEB-TAU-Order_9 <patron name>'. Match any word-ish final segment.
    match = re.match(r"^([A-Za-z]+-[A-Za-z]+-[A-Za-z0-9_]+)\s+\S.*$",
                     value.strip())
    if match:
        return f"{match.group(1)} ***"
    return value.strip()
```

Then in `BorrowingRequestBuilder.build`, immediately after the `lcc_number`
template is rendered into the payload, **add** this logging (there is no
existing debug line to replace — GH #27):

```python
            self.processor._log_pii(
                logging.DEBUG,
                f"  lcc_number: {payload['lcc_number']}",
                f"  lcc_number: {mask_lcc_number(payload['lcc_number'])}",
            )
```

importing `mask_lcc_number` from the processor module.

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest tests/test_pii_logging.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add resource_sharing_forms_processor.py tests/test_pii_logging.py
git commit -m "feat: mask the patron name in lcc_number on console output"
```

---

### Task 8: SANDBOX test harness and documentation

The harness makes the test matrix runnable but **never runs by default** —
it requires an explicit environment flag, mirroring `tests/test_live_smoke.py`.

**Files:**
- Create: `scripts/sb_borrowing_tests.py`
- Modify: `CLAUDE.md`, `README.md`
- Modify: `docs/BORROWING_SB_TEST_MATRIX.md` (cleanup log)

**Interfaces:**
- Consumes: `BorrowingRequestBuilder`, `Users.create_user_rs_request`
- Produces: a CLI that runs one named test from the matrix and records the result

- [ ] **Step 1: Write the harness**

`scripts/sb_borrowing_tests.py`:

```python
#!/usr/bin/env python3
"""Run one SANDBOX test from docs/BORROWING_SB_TEST_MATRIX.md.

Refuses to run without RUN_SB_BORROWING_TESTS=1. SANDBOX only. Prints a
create/GET diff so field settability can be recorded.

    RUN_SB_BORROWING_TESTS=1 poetry run python scripts/sb_borrowing_tests.py --test T-01
    RUN_SB_BORROWING_TESTS=1 poetry run python scripts/sb_borrowing_tests.py --cancel <request_id> --user SHEB
"""
import argparse
import json
import os
import sys

from almaapitk import AlmaAPIClient, AlmaAPIError, Users, build_user_rs_request

if os.environ.get("RUN_SB_BORROWING_TESTS") != "1":
    sys.exit("Refusing to run: set RUN_SB_BORROWING_TESTS=1 to enable SANDBOX writes.")

# Constants the builder has no kwarg for (guidebook §4.1); the builder wraps
# what needs wrapping and passes these through.
EXTRA = {
    "requested_media": "7",
    "allow_other_formats": False,
    "willing_to_pay": False,
}

TESTS = {
    # Bodies come from build_user_rs_request — the same call path production
    # uses — so a harness pass vouches for the real payload shape.
    # agree_to_copyright_terms=False matches the config default pending T-04.
    "T-01": ("SHEB", build_user_rs_request(
        owner="AM1",
        format="DIGITAL",
        citation_type="CR",
        title="Interlibrary loan latency under synthetic load: a sandbox baseline",
        journal_title="Journal of Resource Sharing Diagnostics",
        author="Testerson, A.",
        year="2024",
        pickup_location="AM1",
        pickup_location_type="LIBRARY",
        agree_to_copyright_terms=False,
        extra=EXTRA,
    )),
    # Add T-02 … T-09 from the matrix as they are run.
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", choices=sorted(TESTS))
    ap.add_argument("--cancel")
    ap.add_argument("--user")
    args = ap.parse_args()

    client = AlmaAPIClient("SANDBOX", timeout=180)
    users = Users(client)

    if args.cancel:
        if not args.user:
            return print("--cancel requires --user") or 2
        users.cancel_user_rs_request(args.user, args.cancel)
        print(f"cancelled {args.cancel} for {args.user}")
        return 0

    if not args.test:
        return print("nothing to do: pass --test or --cancel") or 2

    user_id, payload = TESTS[args.test]
    print(f"[{args.test}] POST for user {user_id}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    try:
        response = users.create_user_rs_request(user_id, payload, validate=True)
    except AlmaAPIError as e:
        print(f"FAILED alma_code={getattr(e, 'alma_code', '?')}: {e}")
        return 1

    created = response.data or {}
    request_id = created.get("request_id")
    print(f"created request_id={request_id}")

    fetched = users.get_user_rs_request(user_id, request_id)
    print("\n--- settability diff (sent -> stored) ---")
    for key, sent in sorted(payload.items()):
        stored = fetched.get(key, "<ABSENT>")
        verdict = "ok" if stored == sent else "DIFFERS"
        print(f"  {key:<28} {verdict:<8} sent={sent!r} stored={stored!r}")
    print(f"\nRecord request_id {request_id} in the matrix cleanup log, then cancel it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify it refuses to run without the flag**

Run: `poetry run python scripts/sb_borrowing_tests.py --test T-01`
Expected: exits with "Refusing to run: set RUN_SB_BORROWING_TESTS=1 …" and makes **no** API call.

- [ ] **Step 3: Update the project docs**

In `CLAUDE.md`, under **Architecture**, add:

```markdown
- `rs_requests/` — request builders: `base.py` (interface), `lending.py`, `borrowing.py`, `metadata.py`
- `input_borrowing/` — watched folder for borrowing files from Power Automate (the not-held fork)
```

Under **Key Patterns**, add:

```markdown
- **Two request kinds, one pipeline**: Power Automate forks on a holdings check — held → `input/` → lending; not held → `input_borrowing/` → borrowing. Only the terminal build/submit step differs.
- **`SHEB` is ambiguous**: a *partner code* on the lending path, a *proxy user code* on the borrowing path. Never move one between paths.
- **Borrowing field values are evidence-backed**: `docs/BORROWING_REQUESTS.md` derives them from 1912 real requests. Change a value there, with evidence, before changing it in code.
```

Under **Gotchas**, add:

```markdown
- Borrowing `owner` is a plain string but `pickup_location` is wrapped `{"value": ...}` — the most common cause of a borrowing `BAD_REQUEST`
- `agree_to_copyright_terms` and `lcc_number_template` are unresolved (see the guidebook); both are config-driven so the answer needs no code change
- A borrowing create can time out and still save — recovery is Alma's own `402362`
  duplicate rejection on the next run's re-POST (see the Decision record in Task 5),
  which depends on `check_patron_duplicate_borrowing_requests=true` in config
```

In `README.md`, add a **Borrowing Requests** section describing the second
input folder, the `borrowing.enabled` switch, and linking to both new docs.

- [ ] **Step 4: Run the full suite one last time**

Run: `poetry run pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/sb_borrowing_tests.py CLAUDE.md README.md docs/
git commit -m "feat: add SANDBOX borrowing test harness and document the flow"
```

---

## Self-Review

**Spec coverage.** Guidebook §4.1 constants → Task 5 Step 4 (builder kwargs +
`extra`) + test. §4.2 near-constants → config defaults, Task 3 Step 5. §4.3
articles-only scope and the `E_CR`/`BK` rejection → Task 5 tests. §4.4
bibliographic fields → Task 5 loop. §4.5 `lcc_number` template → Tasks 3, 5, 7.
§4.6 copyright → config flag, Task 5. §5 gotchas → Task 5 `submit` comment and
Task 8 docs. §9 upstream evidence → Global Constraints, Tasks 0 and 5. Test
matrix → Task 8 harness.

**Deliberate gaps, to be closed by evidence rather than guesswork:**

1. **Task 0 is blocked on the almaapitk 0.5.0 release** (PyPI latest is 0.4.6
   at plan-revision time; the operator is preparing the release). Tasks 1–4
   are executable now; Tasks 5+ wait for the floor.
2. **Field settability is unproven.** Task 5 sends `requested_media`,
   `agree_to_copyright_terms` and possibly `lcc_number` on the strength of GET
   observations. **T-02 must run before any production use**, and its diff may
   remove fields from the payload.
3. **`lcc_number_template` ships empty**, so the field is omitted until the
   librarians answer. That is a knowing divergence from 98% of existing
   requests, not an oversight.
4. **`need_patron_info`, `specific_edition`, `maximum_fee` are not sent.** They
   vary or are suspected output-only. T-02 decides whether to add them.
5. **Book (`BK`) support is deliberately out of scope** (DECISION 2026-07-22).
   Revisit only after AlmaAPITK #207 decomposes the PHYSICAL+BOOK 500 and a
   book recipe is proven live in SANDBOX.
6. **Task 2 moves ~170 lines of production lending code.** The golden test plus
   Task 1's characterization test are the only guards. If either fails after the
   move, revert rather than adjust the test.

**Type consistency.** `BuiltRequest(kind, external_id, payload, summary)` is
constructed identically in Tasks 2 and 5. `get_builder(kind, *, processor)` is
called the same way in Tasks 2 and 6. `fetch_citation_metadata(identifier,
id_type)` is defined in Task 5 and called in Task 2's `create_request_from_form`
— note that Task 2 writes the call site before Task 5 creates the module, so
Task 2's import is inside the `if builder.needs_metadata:` branch and never
executes for lending.
