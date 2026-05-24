# PII Leak Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confine patron PII to local (gitignored) file logs — keep it out of `.a5c/` agent artifacts and out of console/stdout — while preserving full local logging and `.a5c` history.

**Architecture:** Two layered barriers. (1) Git hygiene: untrack `.a5c/runs` + `.a5c/cache` so per-run capture data stops reaching the public repo. (2) Logging sink split: the file handler keeps full PII locally; a `PiiConsoleFilter` drops PII-flagged records from the console handler, and PII-bearing call sites log full detail file-only via a `_log_pii` helper plus a sanitized (masked-ID) companion for the console.

**Tech Stack:** Python 3.12, stdlib `logging`, pytest, git. No `almaapitk` changes. No live Alma API calls in tests.

**Spec:** `docs/superpowers/specs/2026-05-24-pii-leak-isolation-design.md`

---

### Task 1: `.a5c` boundary isolation (git hygiene)

Not TDD — git/config change verified by `git ls-files`.

**Files:**
- Modify: `.gitignore`
- Modify: `.a5c/processes/task-scheduler-migration.js` (scrub absolute paths)
- Untrack: `.a5c/runs/`, `.a5c/cache/`

- [ ] **Step 1: Add ignore rules.** Append to `.gitignore` under a new `# Babysitter runtime (local-only; keep run history off the public repo)` comment:

```gitignore
# Babysitter runtime (local-only; keep run history off the public repo)
.a5c/runs/
.a5c/cache/
```

- [ ] **Step 2: Untrack the already-committed runtime data (files stay on disk).**

Run: `git rm -r --cached .a5c/runs .a5c/cache`
Expected: lists removed paths; `ls .a5c/runs` still shows the files locally.

- [ ] **Step 3: Scrub hardcoded absolute paths in the committed process file.**

Run: `sed -i 's#/home/hagaybar/projects/Alma-RS-lending-request-automation#.#g' .a5c/processes/task-scheduler-migration.js`
Then collapse any leftover `cd . && ` prefixes:
Run: `sed -i 's#cd \. && ##g' .a5c/processes/task-scheduler-migration.js`

- [ ] **Step 4: Verify only the recipe layer remains tracked under `.a5c`.**

Run: `git ls-files '.a5c/**' | grep -vE '\.a5c/(processes/|package\.json|package-lock\.json)' || echo CLEAN`
Expected: `CLEAN` (nothing tracked outside `processes/` + package files).

Run: `git grep -n '/home/hagaybar' -- '.a5c/**' || echo NO-ABS-PATHS`
Expected: `NO-ABS-PATHS`.

- [ ] **Step 5: Commit.**

```bash
git add .gitignore .a5c/processes/task-scheduler-migration.js
git commit -m "Untrack .a5c run/cache data; scrub abs paths (PII isolation, issue #4)"
```

---

### Task 2: `mask_user_id` helper (TDD)

**Files:**
- Modify: `resource_sharing_forms_processor.py` (add module-level function after the exception classes, before `class ResourceSharingFormsProcessor`, ~line 80)
- Test: `tests/test_pii_logging.py` (new)

- [ ] **Step 1: Write the failing test.** Create `tests/test_pii_logging.py`:

```python
"""Tests for PII-safe console logging helpers."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resource_sharing_forms_processor import mask_user_id


def test_mask_user_id_keeps_last_four():
    assert mask_user_id("123456789") == "*****6789"


def test_mask_user_id_short_is_fully_masked():
    assert mask_user_id("1234") == "***"
    assert mask_user_id("12") == "***"


def test_mask_user_id_empty_or_none():
    assert mask_user_id("") == "***"
    assert mask_user_id(None) == "***"
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `poetry run pytest tests/test_pii_logging.py -v`
Expected: FAIL — `ImportError: cannot import name 'mask_user_id'`.

- [ ] **Step 3: Write minimal implementation.** In `resource_sharing_forms_processor.py`, after `class FileProcessingError` (line 79) and before `class ResourceSharingFormsProcessor` (line 82), add:

```python
def mask_user_id(user_id: Optional[str]) -> str:
    """Mask a patron identifier for safe console display.

    Keeps only the last 4 characters so operators can correlate a console
    warning with a record without exposing the full ID. Full IDs are written
    to the local (gitignored) file log, never the console.
    """
    if not user_id:
        return "***"
    uid = str(user_id)
    if len(uid) <= 4:
        return "***"
    return "*" * (len(uid) - 4) + uid[-4:]
```

- [ ] **Step 4: Run test to verify it passes.**

Run: `poetry run pytest tests/test_pii_logging.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit.**

```bash
git add resource_sharing_forms_processor.py tests/test_pii_logging.py
git commit -m "Add mask_user_id helper for PII-safe console output"
```

---

### Task 3: `PiiConsoleFilter` + attach to console handler (TDD)

**Files:**
- Modify: `resource_sharing_forms_processor.py` (add filter class after `mask_user_id`; attach in `setup_logging` ~line 204)
- Test: `tests/test_pii_logging.py`

- [ ] **Step 1: Write the failing test.** Append to `tests/test_pii_logging.py`:

```python
from resource_sharing_forms_processor import PiiConsoleFilter


def _record(pii: bool) -> logging.LogRecord:
    rec = logging.LogRecord("x", logging.INFO, __file__, 0, "msg", None, None)
    if pii:
        rec.pii = True
    return rec


def test_pii_filter_drops_flagged_record():
    assert PiiConsoleFilter().filter(_record(pii=True)) is False


def test_pii_filter_passes_normal_record():
    assert PiiConsoleFilter().filter(_record(pii=False)) is True
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `poetry run pytest tests/test_pii_logging.py -v`
Expected: FAIL — `ImportError: cannot import name 'PiiConsoleFilter'`.

- [ ] **Step 3: Write minimal implementation.** In `resource_sharing_forms_processor.py`, directly after `mask_user_id`, add:

```python
class PiiConsoleFilter(logging.Filter):
    """Drops log records flagged as containing PII.

    Attached to the console/stdout handler only. Records emitted with
    ``extra={'pii': True}`` are written to the file handler (local,
    gitignored) but suppressed on the console, so patron data never reaches
    stdout (terminal snapshots, agent capture, LLM exposure).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "pii", False)
```

Then in `setup_logging`, immediately after `console_handler.setFormatter(console_formatter)` (line 204), add:

```python
        console_handler.addFilter(PiiConsoleFilter())
```

- [ ] **Step 4: Run test to verify it passes.**

Run: `poetry run pytest tests/test_pii_logging.py -v`
Expected: PASS (5 tests total).

- [ ] **Step 5: Commit.**

```bash
git add resource_sharing_forms_processor.py tests/test_pii_logging.py
git commit -m "Add PiiConsoleFilter and attach to console handler"
```

---

### Task 4: Split PII call sites via `_log_pii` helper (TDD)

**Files:**
- Modify: `resource_sharing_forms_processor.py` (add `_log_pii` method; edit call sites at ~366, 384, 398, 400, 403, 500, 657)
- Test: `tests/test_pii_logging.py`

- [ ] **Step 1: Write the failing integration test.** Append to `tests/test_pii_logging.py`:

```python
from resource_sharing_forms_processor import ResourceSharingFormsProcessor


def test_note_pii_in_file_not_on_console(tmp_path, capsys):
    config = {
        "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
        "file_processing": {
            "input_folder": str(tmp_path / "input"),
            "processed_folder": str(tmp_path / "processed"),
            "output_dir": str(tmp_path / "output"),
        },
    }
    proc = ResourceSharingFormsProcessor(config, dry_run=True)
    form_data = {
        "partner_code": "ANC",
        "identifier": "12345678",  # 8-digit PMID
        "user_name": "Jane Patron",
        "user_id": "0273601",
        "is_faculty": "Yes",
        "notes": "",
        "order_number": "",
    }
    proc.create_lending_request_from_form(form_data)

    for h in proc.logger.handlers:
        h.flush()
    log_text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (tmp_path / "output" / "logs").glob("*.log")
    )
    out = capsys.readouterr().out

    # Full PII present in the local file log...
    assert "Jane Patron" in log_text
    # ...but never on the console/stdout.
    assert "Jane Patron" not in out
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `poetry run pytest tests/test_pii_logging.py::test_note_pii_in_file_not_on_console -v`
Expected: FAIL — `assert "Jane Patron" not in out` (the Note line at 657 currently prints to console).

- [ ] **Step 3: Add the `_log_pii` helper.** In `resource_sharing_forms_processor.py`, add this method to `ResourceSharingFormsProcessor` (place it just after `setup_logging` returns, e.g. after line 211):

```python
    def _log_pii(self, level: int, full_msg: str, safe_msg: Optional[str] = None) -> None:
        """Log PII-bearing detail to the file sink only, plus an optional
        sanitized companion that may reach the console.

        ``full_msg`` is flagged ``pii=True`` so PiiConsoleFilter suppresses it
        on the console while the file handler still records it. ``safe_msg``,
        when given, is logged normally and may appear on the console.
        """
        self.logger.log(level, full_msg, extra={"pii": True})
        if safe_msg is not None:
            self.logger.log(level, safe_msg)
```

- [ ] **Step 4: Edit call site — line 366 (user lookup debug).** Replace:

```python
            self.logger.debug(f"Looking up user in Alma: {user_id}")
```
with:
```python
            self._log_pii(logging.DEBUG, f"Looking up user in Alma: {user_id}")
```

- [ ] **Step 5: Edit call site — lines 384-387 (lookup success info).** Replace:

```python
            self.logger.info(
                f"User lookup successful: {user_id} -> {full_name} "
                f"(group: {user_group_desc}, is_academic_staff: {is_academic_staff})"
            )
```
with:
```python
            self._log_pii(
                logging.INFO,
                f"User lookup successful: {user_id} -> {full_name} "
                f"(group: {user_group_desc}, is_academic_staff: {is_academic_staff})",
                f"User {mask_user_id(user_id)}: lookup OK "
                f"(is_academic_staff: {is_academic_staff})",
            )
```

- [ ] **Step 6: Edit call sites — lines 398, 400, 403 (lookup warnings).** Replace:

```python
            if e.status_code == 404:
                self.logger.warning(f"User not found in Alma: {user_id}")
            else:
                self.logger.warning(f"Alma API error looking up user {user_id}: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"Unexpected error looking up user {user_id}: {e}")
            return None
```
with:
```python
            if e.status_code == 404:
                self._log_pii(
                    logging.WARNING,
                    f"User not found in Alma: {user_id}",
                    f"User not found in Alma: {mask_user_id(user_id)}",
                )
            else:
                self._log_pii(
                    logging.WARNING,
                    f"Alma API error looking up user {user_id}: {e}",
                    f"Alma API error looking up user {mask_user_id(user_id)}: {e}",
                )
            return None
        except Exception as e:
            self._log_pii(
                logging.WARNING,
                f"Unexpected error looking up user {user_id}: {e}",
                f"Unexpected error looking up user {mask_user_id(user_id)}: {e}",
            )
            return None
```

- [ ] **Step 7: Edit call site — line 500 (requester debug).** Replace:

```python
            self.logger.debug(f"  Requester: {form_data['user_name']} ({form_data['user_id']})")
```
with:
```python
            self._log_pii(
                logging.DEBUG,
                f"  Requester: {form_data['user_name']} ({form_data['user_id']})",
            )
```

- [ ] **Step 8: Edit call site — line 657 (note).** Replace:

```python
        self.logger.info(f"  Note: {params['note'][:100]}..." if params.get('note') else "  Note: (empty)")
```
with:
```python
        if params.get('note'):
            self._log_pii(
                logging.INFO,
                f"  Note: {params['note'][:100]}...",
                "  Note: (recorded — see file log)",
            )
        else:
            self.logger.info("  Note: (empty)")
```

- [ ] **Step 9: Run the integration test to verify it passes.**

Run: `poetry run pytest tests/test_pii_logging.py::test_note_pii_in_file_not_on_console -v`
Expected: PASS.

- [ ] **Step 10: Commit.**

```bash
git add resource_sharing_forms_processor.py tests/test_pii_logging.py
git commit -m "Route patron PII to file-only log sink; mask IDs on console"
```

---

### Task 5: `test_user_retrieval.py` — mask contacts, gate raw dump (TDD)

**Files:**
- Modify: `test_user_retrieval.py` (extract `format_user_report`; add `--show-raw`; mask helpers)
- Test: `tests/test_user_retrieval_masking.py` (new)

- [ ] **Step 1: Write the failing test.** Create `tests/test_user_retrieval_masking.py`:

```python
"""Tests for PII masking in the test_user_retrieval diagnostic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_user_retrieval import format_user_report

SAMPLE = {
    "primary_id": "0273601",
    "first_name": "Jane",
    "last_name": "Patron",
    "contact_info": {
        "email": [{"email_address": "jane.patron@example.com", "preferred": True,
                   "email_type": [{"desc": "Personal"}]}],
        "phone": [{"phone_number": "0521234567", "preferred": True}],
        "address": [{"city": "Tel Aviv", "country": {"desc": "Israel"}, "preferred": True}],
    },
}


def test_contacts_masked_by_default():
    report = format_user_report(SAMPLE, show_raw=False)
    assert "jane.patron@example.com" not in report
    assert "0521234567" not in report
    assert "Tel Aviv" not in report
    # Domain may remain as a non-identifying hint; full address must not.
    assert "example.com" in report


def test_show_raw_includes_full_record():
    report = format_user_report(SAMPLE, show_raw=True)
    assert "jane.patron@example.com" in report
    assert "0521234567" in report
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `poetry run pytest tests/test_user_retrieval_masking.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_user_report'`.

- [ ] **Step 3: Refactor `test_user_retrieval.py`.** Replace the entire file contents with:

```python
#!/usr/bin/env python3
"""
Simple diagnostic to retrieve user information from Alma API.

By default, contact fields (email, phone, address) are masked and the raw
JSON is suppressed, so running this does not spill patron PII to the terminal.
Pass --show-raw to print the full unmasked record (explicit opt-in).

Usage:
    python test_user_retrieval.py
    python test_user_retrieval.py --user-id 027393602
    python test_user_retrieval.py --environment PRODUCTION --show-raw
"""

import argparse
import json
import sys

from almaapitk import AlmaAPIClient, Users


def _mask_email(addr: str) -> str:
    if not addr or "@" not in addr:
        return "***"
    return "***@" + addr.split("@", 1)[1]


def _mask_phone(num: str) -> str:
    if not num:
        return "***"
    digits = str(num)
    return "***" + digits[-2:] if len(digits) > 2 else "***"


def format_user_report(user_data: dict, show_raw: bool = False) -> str:
    """Build the human-readable user report.

    Identity fields (name, group, status) are shown; contact fields are
    masked unless show_raw is True. The full JSON is included only when
    show_raw is True.
    """
    lines = []
    lines.append(f"Primary ID:    {user_data.get('primary_id', 'N/A')}")
    lines.append(f"First Name:    {user_data.get('first_name', 'N/A')}")
    lines.append(f"Last Name:     {user_data.get('last_name', 'N/A')}")
    lines.append(f"Full Name:     {user_data.get('full_name', 'N/A')}")
    lines.append(f"User Group:    {user_data.get('user_group', {}).get('desc', 'N/A')}")
    lines.append(f"Status:        {user_data.get('status', {}).get('desc', 'N/A')}")
    lines.append(f"Account Type:  {user_data.get('account_type', {}).get('desc', 'N/A')}")
    lines.append(f"Expiry Date:   {user_data.get('expiry_date', 'N/A')}")

    contact_info = user_data.get("contact_info", {})

    lines.append("")
    lines.append("Email Addresses:")
    emails = contact_info.get("email", [])
    if emails:
        for email in emails:
            preferred = " (preferred)" if email.get("preferred") else ""
            raw = email.get("email_address", "N/A")
            shown = raw if show_raw else _mask_email(raw)
            lines.append(f"  - {shown}{preferred}")
    else:
        lines.append("  (no emails found)")

    lines.append("")
    lines.append("Phone Numbers:")
    phones = contact_info.get("phone", [])
    if phones:
        for phone in phones:
            preferred = " (preferred)" if phone.get("preferred") else ""
            raw = phone.get("phone_number", "N/A")
            shown = raw if show_raw else _mask_phone(raw)
            lines.append(f"  - {shown}{preferred}")
    else:
        lines.append("  (no phones found)")

    lines.append("")
    lines.append("Addresses:")
    addresses = contact_info.get("address", [])
    if addresses:
        for addr in addresses:
            preferred = " (preferred)" if addr.get("preferred") else ""
            country = addr.get("country", {}).get("desc", "")
            if show_raw:
                city = addr.get("city", "")
                lines.append(f"  - {city}, {country}{preferred}")
            else:
                lines.append(f"  - (masked), {country}{preferred}")
    else:
        lines.append("  (no addresses found)")

    if show_raw:
        lines.append("")
        lines.append("-" * 60)
        lines.append("Full JSON Response:")
        lines.append("-" * 60)
        lines.append(json.dumps(user_data, indent=2, ensure_ascii=False))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Retrieve user information from Alma API")
    parser.add_argument("--user-id", default="027393602", help="User ID to retrieve")
    parser.add_argument("--environment", "-e", choices=["SANDBOX", "PRODUCTION"],
                        default="SANDBOX", help="Alma environment")
    parser.add_argument("--show-raw", action="store_true",
                        help="Print full unmasked record incl. raw JSON (PII!)")
    args = parser.parse_args()

    print("=" * 60)
    print("USER RETRIEVAL TEST")
    print("=" * 60)
    print(f"Environment: {args.environment}")
    print(f"User ID: {args.user_id}")
    print("=" * 60)

    client = AlmaAPIClient(args.environment)
    users = Users(client)

    print("\nRetrieving user data...")
    try:
        response = users.get_user(args.user_id)
        user_data = response.data
        print("\n" + "=" * 60)
        print("USER DATA RETRIEVED SUCCESSFULLY")
        print("=" * 60 + "\n")
        print(format_user_report(user_data, show_raw=args.show_raw))
        if not args.show_raw:
            print("\n(contact fields masked; pass --show-raw to print the full record)")
    except Exception as e:
        print(f"\nERROR: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes.**

Run: `poetry run pytest tests/test_user_retrieval_masking.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit.**

```bash
git add test_user_retrieval.py tests/test_user_retrieval_masking.py
git commit -m "Mask contact PII in test_user_retrieval; gate raw dump behind --show-raw"
```

---

### Task 6: Full verification

- [ ] **Step 1: Run the whole suite.**

Run: `ALMA_SB_API_KEY=dummy ALMA_PROD_API_KEY=dummy poetry run pytest tests/ -v -p no:cacheprovider`
Expected: the new PII tests PASS; previously-passing tests still PASS; the only errors are the 4 pre-existing `fixture not found` collection errors (`test_pubmed_fetch`, `test_crossref_fetch`, `test_validation_errors`, `test_lending_requests`) — unrelated and out of scope.

- [ ] **Step 2: Verify success criteria.**

Run: `git ls-files '.a5c/**' | grep -vE '\.a5c/(processes/|package\.json|package-lock\.json)' || echo CLEAN`
Expected: `CLEAN`.

Run: `poetry run python scripts/smoke_project.py`
Expected: `All imports OK!`.

- [ ] **Step 3: Final commit (if any uncommitted docs/cleanup remain).**

```bash
git status
# commit anything outstanding, then:
git push origin main
```

---

## Self-review notes

- **Spec coverage:** Section 1 → Task 1; Section 2 → Tasks 2–4; Section 3 → Task 5; Section 4 (testing) → embedded in Tasks 2–5 + Task 6. Success criteria 1–4 → Task 6.
- **Type/name consistency:** `mask_user_id`, `PiiConsoleFilter`, `_log_pii(level, full_msg, safe_msg)`, `format_user_report(user_data, show_raw)` used consistently across tasks.
- **No placeholders:** all steps contain concrete code/commands and expected output.
