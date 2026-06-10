"""Tests for ResourceSharingFormsProcessor.move_to_processed.

Behavior contract (see issue #5): a completed file is moved to the processed
folder under its *original input filename* (no timestamp prefix), so Power
Automate can verify processing by searching for the same name in a different
folder. On a (rare) name collision the incoming file is saved under a numeric
suffix, the original is preserved, and an error is logged.
"""

import logging

from resource_sharing_forms_processor import ResourceSharingFormsProcessor


def _make_proc(tmp_path):
    config = {
        "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
        "file_processing": {
            "input_folder": str(tmp_path / "input"),
            "processed_folder": str(tmp_path / "processed"),
            "output_dir": str(tmp_path / "output"),
        },
    }
    return ResourceSharingFormsProcessor(config, dry_run=True)


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _capture_logs(proc):
    handler = _ListHandler()
    handler.setLevel(logging.DEBUG)
    proc.logger.addHandler(handler)
    return handler.records


def test_move_to_processed_keeps_original_name(tmp_path):
    proc = _make_proc(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    original_name = "SZ6_10_2026 9_32_51 AM.tsv"
    src = input_dir / original_name
    src.write_text("col1\tcol2\n", encoding="utf-8")

    proc.move_to_processed(src)

    processed_dir = tmp_path / "processed"
    moved = processed_dir / original_name

    # File lands under the exact original name, with no timestamp prefix.
    assert moved.exists()
    assert [p.name for p in processed_dir.iterdir()] == [original_name]
    # Source is gone from input/.
    assert not src.exists()


def test_move_to_processed_suffixes_on_collision_and_logs_error(tmp_path):
    proc = _make_proc(tmp_path)
    records = _capture_logs(proc)

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    name = "report.tsv"
    existing = processed_dir / name
    existing.write_text("old\n", encoding="utf-8")

    src = input_dir / name
    src.write_text("new\n", encoding="utf-8")

    proc.move_to_processed(src)

    # The pre-existing processed file is preserved untouched.
    assert existing.read_text(encoding="utf-8") == "old\n"
    # The incoming file is saved under a numeric suffix.
    suffixed = processed_dir / "report (1).tsv"
    assert suffixed.exists()
    assert suffixed.read_text(encoding="utf-8") == "new\n"
    # Source is gone from input/.
    assert not src.exists()
    # The collision is surfaced as an error.
    assert any(r.levelno == logging.ERROR for r in records)
