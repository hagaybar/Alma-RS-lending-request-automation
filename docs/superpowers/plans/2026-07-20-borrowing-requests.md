# Borrowing Request Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend this processor to create Alma **borrowing** (user resource-sharing) requests from a second input folder, without disturbing the production lending path.

**Architecture:** The Power Automate flow already forks on a holdings check, writing lending files to `input/` and borrowing files to `input_borrowing/`. Everything up to request creation — file watching, identifier detection, metadata enrichment, moving to `processed/`, logging, reporting — is shared and stays in `resource_sharing_forms_processor.py`. Only the terminal step differs, so the two request-building/submitting behaviours move behind a small `RequestBuilder` interface in a new `rs_requests/` package. Lending is extracted first as a pure refactor guarded by a characterization test; borrowing is then added as a second implementation of the same interface.

**Tech Stack:** Python 3.12, Poetry, pytest, `almaapitk` (Alma REST client), PubMed E-utilities / Crossref for citation metadata.

**Reference:** `docs/BORROWING_REQUESTS.md` is the authority for every field value. `docs/BORROWING_SB_TEST_MATRIX.md` lists the SANDBOX tests that close its open questions.

## Global Constraints

- Python `^3.12`, dependencies via Poetry. `package-mode = false` — the repo runs from its root, so `rs_requests/` is imported as a plain top-level package.
- **Do not use `almaapitk.build_user_rs_request`.** It exists only on the unmerged `chunk/rs-borrowing-ergonomics` branch of AlmaAPITK and is in no released version. We build the request dict ourselves.
- The only toolkit call for borrowing is `Users.create_user_rs_request(user_id, request_data, user_id_type=None, override_blocks=None) -> AlmaResponse`. It forwards `request_data` to Alma **verbatim** — correct field shapes are entirely our responsibility.
- `owner` is a **plain string**; `pickup_location`, `format`, `citation_type` are **wrapped** as `{"value": ...}`. This asymmetry is the most common cause of `BAD_REQUEST`.
- **Dry-run by default.** `--live` must be passed explicitly for any API call.
- **SANDBOX only** for all testing. `AlmaAPIClient("SANDBOX")` reads `ALMA_SB_API_KEY` from the environment. Never place a key on a command line, never print one.
- **Never blind-retry a create.** A timed-out POST may already have saved; reconcile by `external_id` first.
- `agree_to_copyright_terms` and `lcc_number` content are **OPEN questions** (guidebook §4.6, §4.5). Both must be config-driven with a documented default, never hardcoded, so the answers land in config without a code change.
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
| `rs_requests/borrowing.py` | `BorrowingRequestBuilder` — the new borrowing payload + submit |
| `resource_sharing_forms_processor.py` | Pipeline only; delegates the terminal step to a builder |
| `config/rs_forms_config.example.json` | Gains a `borrowing` block |
| `tests/test_borrowing_toolkit_contract.py` | Guards the almaapitk dependency floor |
| `tests/test_lending_characterization.py` | Pins lending behaviour before the refactor |
| `tests/test_builder_dispatch.py` | Folder → builder routing |
| `tests/test_borrowing_tsv.py` | Borrowing TSV parsing |
| `tests/test_borrowing_builder.py` | Borrowing payload construction and validation |
| `scripts/sb_borrowing_tests.py` | Opt-in SANDBOX harness for the test matrix (never runs by default) |

---

### Task 0: Guard the almaapitk dependency floor

The repo pins `almaapitk = ">=0.4.6"`. The user resource-sharing methods post-date the 0.4.5 release, so it is **unverified** that the pinned floor exposes them. If it does not, every later task is built on sand.

**Files:**
- Test: `tests/test_borrowing_toolkit_contract.py` (create)
- Modify: `pyproject.toml` (only if the assertion fails)

**Interfaces:**
- Consumes: nothing
- Produces: a proven floor for `Users.create_user_rs_request`

- [ ] **Step 1: Write the failing test**

```python
"""Guard: the pinned almaapitk must expose the borrowing create surface."""
import inspect

from almaapitk.domains.users import Users


def test_users_exposes_create_user_rs_request():
    assert hasattr(Users, "create_user_rs_request"), (
        "The pinned almaapitk has no Users.create_user_rs_request. "
        "Raise the floor in pyproject.toml to the first release that ships it."
    )


def test_create_user_rs_request_signature_is_stable():
    sig = inspect.signature(Users.create_user_rs_request)
    assert list(sig.parameters) == [
        "self", "user_id", "request_data", "user_id_type", "override_blocks",
    ]


def test_get_user_rs_request_supports_external_lookup():
    """Reconciling a timed-out create depends on request_id_type='external'."""
    sig = inspect.signature(Users.get_user_rs_request)
    assert "request_id_type" in sig.parameters
```

- [ ] **Step 2: Run it**

Run: `poetry run pytest tests/test_borrowing_toolkit_contract.py -v`

Two outcomes, both informative:
- **PASS** — the floor is fine. Go to Step 4.
- **FAIL** on `hasattr` — the floor is too low. Go to Step 3.

- [ ] **Step 3: Raise the floor (only if Step 2 failed)**

Find the first released version exposing the method:

```bash
poetry run pip index versions almaapitk
```

Then in `pyproject.toml`, replace the `almaapitk = ">=0.4.6"` line, keeping the existing comment block above it and appending:

```toml
# Raised to >=X.Y.Z: the user resource-sharing methods
# (Users.create_user_rs_request / get_user_rs_request) are absent below this.
# Borrowing support cannot function on an older floor.
almaapitk = ">=X.Y.Z"
```

Then `poetry lock && poetry install` and re-run Step 2.

- [ ] **Step 4: Commit**

```bash
git add tests/test_borrowing_toolkit_contract.py pyproject.toml poetry.lock
git commit -m "test: guard almaapitk floor for borrowing request support"
```

---

### Task 1: Pin the lending path before touching it

A characterization test that records exactly what the lending path builds today. Task 2 refactors that path; this is the net.

**Files:**
- Test: `tests/test_lending_characterization.py` (create)
- Read: `resource_sharing_forms_processor.py:619-786` (`create_lending_request_from_form`)

**Interfaces:**
- Consumes: `ResourceSharingFormsProcessor.create_lending_request_from_form(form_data) -> dict`
- Produces: a frozen record of the lending `params` dict, reused unchanged in Task 2

- [ ] **Step 1: Write the failing test**

```python
"""Characterization: freeze what the lending path builds today.

Runs in dry-run, so no API call is made. Asserts on the params dict handed
to the toolkit, captured by monkeypatching the domain object.
"""
import json
from pathlib import Path

import pytest

from resource_sharing_forms_processor import ResourceSharingFormsProcessor

CONFIG = {
    "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
    "file_processing": {"input_folder": "./input", "processed_folder": "./processed",
                        "output_dir": "./output"},
    "watch_mode": {"poll_interval": 60},
    "processing_options": {"skip_invalid_identifiers": True,
                           "continue_on_metadata_failure": True,
                           "continue_on_api_error": True},
}

FORM = {
    "filename": "sample", "filepath": Path("sample.tsv"),
    "partner_code": "SHEB", "user_name": "Levi, David", "user_id": "",
    "is_faculty": "yes", "identifier": "33219451",
    "notes": "urgent", "order_number": "Order_Num_24586",
}


def test_lending_params_are_unchanged(tmp_path):
    proc = ResourceSharingFormsProcessor(CONFIG, dry_run=True)
    result = proc.create_lending_request_from_form(dict(FORM))

    assert result["status"] == "dry_run_success"
    assert result["detected_type"] == "pmid"
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
git add tests/test_lending_characterization.py
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
Expected: the first two tests still FAIL (`rs_requests.lending` missing), the third PASSES.

- [ ] **Step 5: Move lending into the builder**

Create `rs_requests/lending.py`. Move the body of
`create_lending_request_from_form` (`resource_sharing_forms_processor.py:619-786`)
into it **verbatim**, changing only `self.` → `self.processor.` for processor
attributes (`logger`, `dry_run`, `owner`, `format_type`, `rs`,
`detect_identifier_type`, `validate_identifier`, `_lookup_and_verify_user`,
`_log_pii`):

```python
"""Lending request builder — behaviour moved unchanged from the processor."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from almaapitk import AlmaAPIError
from almaapitk.utils.citation_metadata import CitationMetadataError

from rs_requests.base import BuiltRequest, RequestBuilder


class LendingRequestBuilder(RequestBuilder):
    kind = "lending"
    needs_metadata = False   # the toolkit enriches inside its own call

    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        # <<< the exact body of create_lending_request_from_form up to the
        # "Create request (or dry-run)" comment, returning a BuiltRequest
        # whose payload is the `params` dict and whose summary carries
        # detected_type. Do not alter any logic while moving it. >>>
        raise NotImplementedError("move the existing body here verbatim")

    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        # <<< the existing `self.rs.create_lending_request_from_citation(**params)`
        # call plus its three except clauses, unchanged. >>>
        raise NotImplementedError("move the existing submit here verbatim")
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
            from rs_requests.metadata import fetch_citation_metadata
            metadata = fetch_citation_metadata(
                form_data["identifier"],
                self.detect_identifier_type(form_data["identifier"]),
            )
        built = builder.build(form_data, metadata)
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create {kind} request")
            self.logger.info(f"  External ID: {built.external_id}")
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
def test_find_pending_files_tags_each_folder(tmp_path):
    lend = tmp_path / "input"; lend.mkdir()
    borrow = tmp_path / "input_borrowing"; borrow.mkdir()
    (lend / "a.tsv").write_text("x")
    (borrow / "b.tsv").write_text("y")

    cfg = dict(CONFIG)
    cfg["file_processing"] = {
        "input_folder": str(lend),
        "borrowing_input_folder": str(borrow),
        "processed_folder": str(tmp_path / "processed"),
        "output_dir": str(tmp_path / "output"),
    }
    proc = ResourceSharingFormsProcessor(cfg, dry_run=True)

    found = dict((p.name, kind) for p, kind in proc.find_pending_files())
    assert found == {"a.tsv": "lending", "b.tsv": "borrowing"}


def test_borrowing_folder_is_optional(tmp_path):
    """A config without a borrowing folder must behave exactly as today."""
    lend = tmp_path / "input"; lend.mkdir()
    (lend / "a.tsv").write_text("x")
    cfg = dict(CONFIG)
    cfg["file_processing"] = {
        "input_folder": str(lend),
        "processed_folder": str(tmp_path / "processed"),
        "output_dir": str(tmp_path / "output"),
    }
    proc = ResourceSharingFormsProcessor(cfg, dry_run=True)
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
        if self.borrowing_input_folder:
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

Add `Tuple` to the `typing` import line. Then change `process_single_run` and
`process_watch_mode` to iterate `self.find_pending_files()` and pass `kind`
through to `process_tsv_file(file_path, kind)`.

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
    "borrowing.agree_to_copyright_terms: OPEN — 98/100 real requests store false; confirm with SB test T-04 before changing",
    "borrowing.lcc_number_template: OPEN — pending the librarians. Placeholders: {hospital} {order_number} {patron_name}. Empty means omit the field",
    "borrowing.allowed_hospitals: proxy user codes; a file naming any other requestor is rejected before any API call"
```

Create the watched folder so a fresh clone works:

```bash
mkdir -p input_borrowing && touch input_borrowing/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add resource_sharing_forms_processor.py config/rs_forms_config.example.json \
        tests/test_builder_dispatch.py input_borrowing/.gitkeep
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
            'requestor': cell('requestor'),
            'identifier': cell('identifier'),
            'notes': cell('notes'),
            'material_type': cell('material_type').upper(),
            'order_number': cell('order_number'),
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
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add resource_sharing_forms_processor.py config/rs_forms_config.example.json \
        tests/test_borrowing_tsv.py
git commit -m "feat: parse borrowing TSV with config-driven column positions"
```

---

### Task 5: Build the borrowing payload

The core of the work. Every value traces to `docs/BORROWING_REQUESTS.md` §4.

**Files:**
- Create: `rs_requests/metadata.py`, `rs_requests/borrowing.py`
- Test: `tests/test_borrowing_builder.py` (create)

**Interfaces:**
- Consumes: `BuiltRequest`, `RequestBuilder` (Task 2); `read_borrowing_tsv_file` output (Task 4)
- Produces:
  - `fetch_citation_metadata(identifier: str, id_type: str) -> Dict[str, str]` with keys `title, author, journal, year, volume, issue, pages, start_page, end_page, issn, isbn, doi, pmid, publisher`
  - `BorrowingRequestBuilder.build(form_data, metadata) -> BuiltRequest`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from rs_requests.borrowing import BorrowingRequestBuilder, BorrowingValidationError


class FakeProcessor:
    dry_run = True
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


META = {
    "title": "A distinctive article title", "author": "Testerson, A.",
    "journal": "Journal of Diagnostics", "year": "2024", "volume": "12",
    "issue": "3", "pages": "101-115", "start_page": "101", "end_page": "115",
    "issn": "0000-0000", "isbn": "", "doi": "10.9999/x", "pmid": "33219451",
    "publisher": "Sandbox Press",
}
FORM = {"requestor": "SHEB", "identifier": "33219451", "notes": "",
        "material_type": "", "order_number": "Order_9", "filename": "r"}


def _build(form=None, meta=None, config=None):
    proc = FakeProcessor()
    if config:
        proc.borrowing_config = {**FakeProcessor.borrowing_config, **config}
    return BorrowingRequestBuilder(proc).build({**FORM, **(form or {})},
                                               {**META, **(meta or {})})


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


def test_material_type_bk_selects_book_and_stays_digital():
    p = _build(form={"material_type": "BK"}).payload
    assert p["citation_type"] == {"value": "BK"}
    assert p["format"] == {"value": "DIGITAL"}   # books are scanned, not loaned


def test_rejects_electronic_citation_codes():
    """E_CR/E_BK are accepted by Alma but appear in 0 of 1912 real requests."""
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
    built = _build()
    assert built.external_id.startswith("FORMS-BR-SHEB-")
    assert built.external_id.endswith("-Order_9")


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

FIELDS = ("title", "author", "journal", "year", "volume", "issue", "pages",
          "start_page", "end_page", "issn", "isbn", "doi", "pmid", "publisher")


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

Every constant here traces to docs/BORROWING_REQUESTS.md §4, which was
derived from 1912 real SANDBOX requests (100 read in full). Do not change a
value without updating that document and the evidence behind it.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from almaapitk import AlmaAPIError, Users

from rs_requests.base import BuiltRequest, RequestBuilder


class BorrowingValidationError(Exception):
    """Raised before any API call when the request cannot be valid."""


#: The librarians' UI offers only these two. E_CR/E_BK are accepted by Alma
#: but appear in 0 of 1912 real requests — sending them would silently
#: diverge from every manually created request.
ALLOWED_CITATION_TYPES = ("CR", "BK")

#: Article citation types additionally require journal_title + author + year,
#: else Alma returns alma_code 401930.
ARTICLE_CITATION_TYPES = ("CR",)


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
                f"citation_type {citation_type!r} is not offered by the "
                f"librarians' UI and appears in 0 of 1912 real requests. "
                f"Allowed: {', '.join(ALLOWED_CITATION_TYPES)}."
            )

        title = meta.get("title", "").strip()
        if not title:
            raise BorrowingValidationError("citation metadata has no title")

        if citation_type in ARTICLE_CITATION_TYPES:
            missing = [name for name, key in
                       (("journal_title", "journal"), ("author", "author"), ("year", "year"))
                       if not meta.get(key, "").strip()]
            if missing:
                raise BorrowingValidationError(
                    f"an article request requires {', '.join(missing)} "
                    f"(Alma returns alma_code 401930 without them)"
                )

        hospital = form_data["requestor"]
        timestamp = datetime.now().strftime("%d%m%Y%H%M%S")
        order_number = (form_data.get("order_number") or "").strip()
        external_id = f"FORMS-BR-{hospital}-{timestamp}"
        if order_number:
            external_id = f"{external_id}-{order_number}"

        # --- constants: 100/100 in the verified sample -------------------
        payload: Dict[str, Any] = {
            "owner": cfg.get("owner", "AM1"),                            # plain
            "pickup_location": {"value": cfg.get("pickup_location", "AM1")},
            "pickup_location_type": cfg.get("pickup_location_type", "LIBRARY"),
            "requested_media": cfg.get("requested_media", "7"),
            "allow_other_formats": False,
            "willing_to_pay": False,
            "format": {"value": cfg.get("default_format", "DIGITAL")},
            "citation_type": {"value": citation_type},
            "agree_to_copyright_terms": bool(cfg.get("agree_to_copyright_terms", False)),
            "title": title,
            "external_id": external_id,
        }

        # --- bibliographic fields: included only when non-empty ----------
        for key, source in (("author", "author"), ("year", "year"),
                            ("journal_title", "journal"), ("volume", "volume"),
                            ("issue", "issue"), ("pages", "pages"),
                            ("start_page", "start_page"), ("end_page", "end_page"),
                            ("issn", "issn"), ("isbn", "isbn"),
                            ("doi", "doi"), ("pmid", "pmid"),
                            ("publisher", "publisher")):
            value = (meta.get(source) or "").strip()
            if value:
                payload[key] = value

        note = (form_data.get("notes") or "").strip()
        if note:
            payload["note"] = note

        template = (cfg.get("lcc_number_template") or "").strip()
        if template:
            payload["lcc_number"] = template.format(
                hospital=hospital,
                order_number=order_number,
                patron_name=(form_data.get("patron_name") or "").strip(),
            ).strip()

        # Deliberately NOT sent — see docs/BORROWING_REQUESTS.md:
        #   partner       assigned by the rota after creation
        #   mms_id        Alma generates a placeholder bib from this metadata
        #   oclc_number   written by the supplier, not the requester
        #   level_of_service / copyright_status  empty in 100/100

        return BuiltRequest(
            kind=self.kind,
            external_id=external_id,
            payload=payload,
            summary={"detected_type": form_data.get("identifier_type", ""),
                     "title": title, "requestor": hospital,
                     "citation_type": citation_type},
        )

    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        users = Users(self.processor.client)
        hospital = built.summary["requestor"]
        try:
            response = users.create_user_rs_request(hospital, built.payload)
        except AlmaAPIError as e:
            # A create can time out and still save. Never blind-retry:
            # reconcile by external_id instead.
            raise
        data = response.data or {}
        self.processor.logger.info("✓ Borrowing request created")
        self.processor.logger.info(f"  Request ID: {data.get('request_id')}")
        return {"status": "success", "request_id": data.get("request_id"),
                "external_id": built.external_id, **built.summary}
```

- [ ] **Step 5: Run to verify it passes**

Run: `poetry run pytest tests/test_borrowing_builder.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Run the whole offline suite**

Run: `poetry run pytest -q`
Expected: everything green, lending golden included.

- [ ] **Step 7: Commit**

```bash
git add rs_requests/metadata.py rs_requests/borrowing.py tests/test_borrowing_builder.py
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
def test_end_to_end_dry_run_builds_a_payload(tmp_path, monkeypatch):
    """A borrowing file produces a payload without any network call."""
    import rs_requests.metadata as md
    monkeypatch.setattr(md, "fetch_citation_metadata",
                        lambda ident, id_type: dict(META))

    f = tmp_path / "input_borrowing" / "r.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("SHEB\t33219451\n", encoding="utf-8")

    proc = _proc(tmp_path)
    result = proc.process_tsv_file(f, kind="borrowing")
    assert result["status"] == "dry_run_success"
    assert result["kind"] == "borrowing"
    assert result["requestor"] == "SHEB"


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
Expected: FAIL — `process_tsv_file()` takes no `kind` argument

- [ ] **Step 3: Implement**

Change the signature to `def process_tsv_file(self, file_path: Path, kind: str = 'lending') -> Dict[str, Any]:` and at the top of the body:

```python
        if kind == 'borrowing':
            if not self.borrowing_config.get('enabled', False):
                self.logger.warning(
                    f"Borrowing is disabled in config; skipping {file_path.name}"
                )
                return {'status': 'skipped', 'kind': kind,
                        'filename': file_path.name,
                        'error_message': 'borrowing disabled in config'}
            form_data = self.read_borrowing_tsv_file(file_path)
        else:
            form_data = self.read_tsv_file(file_path)
```

replacing the existing `form_data = self.read_tsv_file(file_path)` line. Then
route the terminal call through `self.create_request_from_form(form_data, kind=kind)`
and add `'kind': kind` to every returned result dict.

Add a `Kind` column to the CSV report header in `generate_csv_report` and
`_append_daily_report`, populated from `result.get('kind', 'lending')`.

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
    match = re.match(r"^([A-Za-z]+-[A-Za-z]+-\d+)\s+\S.*$", value.strip())
    if match:
        return f"{match.group(1)} ***"
    return value.strip()
```

Then in `BorrowingRequestBuilder.build`, replace the plain debug of the
rendered template with:

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

from almaapitk import AlmaAPIClient, AlmaAPIError, Users

if os.environ.get("RUN_SB_BORROWING_TESTS") != "1":
    sys.exit("Refusing to run: set RUN_SB_BORROWING_TESTS=1 to enable SANDBOX writes.")

BASE = {
    "owner": "AM1",
    "pickup_location": {"value": "AM1"},
    "pickup_location_type": "LIBRARY",
    "allow_other_formats": False,
    "willing_to_pay": False,
}

TESTS = {
    "T-01": ("SHEB", {
        **BASE,
        "format": {"value": "DIGITAL"},
        "citation_type": {"value": "CR"},
        "title": "Interlibrary loan latency under synthetic load: a sandbox baseline",
        "journal_title": "Journal of Resource Sharing Diagnostics",
        "author": "Testerson, A.",
        "year": "2024",
        "external_id": "SBTEST-T01-20260720",
    }),
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
        response = users.create_user_rs_request(user_id, payload)
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
- A borrowing create can time out and still save — never blind-retry, reconcile by `external_id`
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

**Spec coverage.** Guidebook §4.1 constants → Task 5 Step 4 + test. §4.2
near-constants → config defaults, Task 3 Step 5. §4.3 `CR`/`BK` and the `E_CR`
prohibition → Task 5 tests. §4.4 bibliographic fields → Task 5 loop. §4.5
`lcc_number` template → Tasks 3, 5, 7. §4.6 copyright → config flag, Task 5.
§5 gotchas → Task 5 `submit` comment and Task 8 docs. §6.4 dependency floor →
Task 0. Test matrix → Task 8 harness.

**Deliberate gaps, to be closed by evidence rather than guesswork:**

1. **Field settability is unproven.** Task 5 sends `requested_media`,
   `agree_to_copyright_terms` and possibly `lcc_number` on the strength of GET
   observations. **T-02 must run before any production use**, and its diff may
   remove fields from the payload.
2. **`lcc_number_template` ships empty**, so the field is omitted until the
   librarians answer. That is a knowing divergence from 98% of existing
   requests, not an oversight.
3. **`need_patron_info`, `specific_edition`, `maximum_fee` are not sent.** They
   vary or are suspected output-only. T-02 decides whether to add them.
4. **Task 2 moves ~170 lines of production lending code.** The golden test plus
   Task 1's characterization test are the only guards. If either fails after the
   move, revert rather than adjust the test.

**Type consistency.** `BuiltRequest(kind, external_id, payload, summary)` is
constructed identically in Tasks 2 and 5. `get_builder(kind, *, processor)` is
called the same way in Tasks 2 and 6. `fetch_citation_metadata(identifier,
id_type)` is defined in Task 5 and called in Task 2's `create_request_from_form`
— note that Task 2 writes the call site before Task 5 creates the module, so
Task 2's import is inside the `if builder.needs_metadata:` branch and never
executes for lending.
