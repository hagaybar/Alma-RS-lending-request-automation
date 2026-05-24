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
