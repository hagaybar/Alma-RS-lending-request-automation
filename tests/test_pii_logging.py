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


def test_mask_handles_empty_order_number_segment():
    """order_number is optional — an empty segment must still mask (review 2026-07-22)."""
    assert mask_lcc_number("SHEB-TAU- Some Patron") == "SHEB-TAU- ***"


from rs_requests.borrowing import BorrowingRequestBuilder
from tests.borrowing_fixtures import FORM, META


def test_borrowing_lcc_number_pii_split_console_vs_file(tmp_path, capsys):
    """End-to-end for the lcc_number _log_pii call site in
    BorrowingRequestBuilder.build (review 2026-07-22, Finding 2).

    Uses Finding 1's exact leak shape (empty order_number) so this fails
    without the pii.py regex fix: with the old regex, mask_lcc_number would
    return the RAW value for the safe_msg, and the patron name would show up
    on the console below.

    verbose=True raises the console threshold to DEBUG so the PiiConsoleFilter
    — not the level gate — is what's actually under test.
    """
    config = {
        "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
        "file_processing": {
            "input_folder": str(tmp_path / "input"),
            "processed_folder": str(tmp_path / "processed"),
            "output_dir": str(tmp_path / "output"),
        },
        "verbose": True,
        "borrowing": {
            "owner": "AM1", "pickup_location": "AM1",
            "pickup_location_type": "LIBRARY", "default_format": "DIGITAL",
            "default_citation_type": "CR", "requested_media": "7",
            "agree_to_copyright_terms": False,
            "lcc_number_template": "{hospital}-TAU-{order_number} {patron_name}",
        },
    }
    proc = ResourceSharingFormsProcessor(config, dry_run=True)
    builder = BorrowingRequestBuilder(proc)
    form_data = {**FORM, "patron_name": "Some Patron", "order_number": ""}

    builder.build(form_data, META)

    for h in proc.logger.handlers:
        h.flush()
    log_text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (tmp_path / "output" / "logs").glob("*.log")
    )
    out = capsys.readouterr().out

    # Full PII present in the local file log...
    assert "Some Patron" in log_text
    # ...but never on the console/stdout...
    assert "Some Patron" not in out
    # ...where the masked variant is shown instead.
    assert "SHEB-TAU- ***" in out
