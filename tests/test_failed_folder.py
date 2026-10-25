"""Tests for the failed folder (GH #48).

Behavior contract: a file that does not finish as success/duplicate is moved
to the failed folder after its FIRST attempt, under its original filename, so
it is never retried automatically. Every retry used to write a new per-file
log and CSV row (288 a day per stuck file), and a stuck backlog fired all at
once when a later release fixed the cause (2026-10-22). To retry, a person
moves the file back into its input folder.
"""

import pytest

from resource_sharing_forms_processor import (
    ResourceSharingFormsProcessor,
    MetadataFetchError,
)


def _make_proc(tmp_path, failed_folder=None, scheduled_mode=False):
    file_processing = {
        "input_folder": str(tmp_path / "input"),
        "borrowing_input_folder": str(tmp_path / "input_borrowing"),
        "processed_folder": str(tmp_path / "processed"),
        "output_dir": str(tmp_path / "output"),
    }
    if failed_folder is not None:
        file_processing["failed_folder"] = str(failed_folder)
    config = {
        "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
        "file_processing": file_processing,
        "borrowing": {"enabled": True, "allowed_hospitals": ["SHEB"]},
    }
    return ResourceSharingFormsProcessor(config, dry_run=True,
                                         scheduled_mode=scheduled_mode)


def _write_lending_tsv(tmp_path, identifier, name="BEIL7_6_2026 9_16_56 AM.tsv"):
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    path = input_dir / name
    row = ["BEIL", "Test Requester", "test@example.com", "no", identifier, "", "BEIL-TAU-2277"]
    path.write_text("\t".join(row) + "\n", encoding="utf-8")
    return path


def test_failed_folder_defaults_next_to_processed(tmp_path):
    proc = _make_proc(tmp_path)
    assert proc.failed_folder == tmp_path / "failed_files"


def test_failed_folder_is_configurable(tmp_path):
    proc = _make_proc(tmp_path, failed_folder=tmp_path / "elsewhere")
    assert proc.failed_folder == tmp_path / "elsewhere"


def test_permanent_failure_moves_to_failed_on_first_attempt(tmp_path):
    proc = _make_proc(tmp_path)
    src = _write_lending_tsv(tmp_path, "not an identifier")

    result = proc.process_tsv_file(src)

    assert result["status"] == "skipped"
    assert not src.exists()
    assert (tmp_path / "failed_files" / src.name).exists()
    assert not (tmp_path / "processed").exists()


def test_transient_failure_also_moves_to_failed(tmp_path, monkeypatch):
    """No automatic retry for any failure: a timeout re-sent with the PROD
    duplicate check off could create the request twice (guidebook §8.3)."""
    proc = _make_proc(tmp_path)
    src = _write_lending_tsv(tmp_path, "33219451")

    def boom(*args, **kwargs):
        raise MetadataFetchError("PubMed unreachable")
    monkeypatch.setattr(proc, "create_request_from_form", boom)

    result = proc.process_tsv_file(src)

    assert result["status"] == "error"
    assert not src.exists()
    assert (tmp_path / "failed_files" / src.name).exists()


def test_borrowing_failure_moves_to_the_same_failed_folder(tmp_path):
    proc = _make_proc(tmp_path)
    borrowing_dir = tmp_path / "input_borrowing"
    borrowing_dir.mkdir(parents=True, exist_ok=True)
    src = borrowing_dir / "r.tsv"
    # A requestor not in allowed_hospitals is rejected before any API call.
    src.write_text("NOPE\t33219451\n", encoding="utf-8")

    result = proc.process_tsv_file(src, kind="borrowing")

    assert result["status"] in ("skipped", "error")
    assert not src.exists()
    assert (tmp_path / "failed_files" / "r.tsv").exists()


def test_success_still_goes_to_processed(tmp_path):
    proc = _make_proc(tmp_path)
    src = _write_lending_tsv(tmp_path, "33219451")

    result = proc.process_tsv_file(src)

    assert result["status"] == "dry_run_success"
    assert (tmp_path / "processed" / src.name).exists()
    assert not (tmp_path / "failed_files").exists()


def test_failed_name_collision_keeps_both_files(tmp_path):
    proc = _make_proc(tmp_path)
    failed_dir = tmp_path / "failed_files"
    failed_dir.mkdir()
    (failed_dir / "same.tsv").write_text("old\n", encoding="utf-8")
    src = _write_lending_tsv(tmp_path, "not an identifier", name="same.tsv")

    proc.process_tsv_file(src)

    assert (failed_dir / "same.tsv").read_text(encoding="utf-8") == "old\n"
    assert (failed_dir / "same (1).tsv").exists()


def test_disabled_borrowing_file_is_left_in_place(tmp_path):
    """The kill switch parks files; it must not push them into failed."""
    proc = _make_proc(tmp_path)
    proc.borrowing_config = {**proc.borrowing_config, "enabled": False}
    borrowing_dir = tmp_path / "input_borrowing"
    borrowing_dir.mkdir(parents=True, exist_ok=True)
    src = borrowing_dir / "parked.tsv"
    src.write_text("SHEB\t33219451\n", encoding="utf-8")

    proc.process_tsv_file(src, kind="borrowing")

    assert src.exists()
    assert not (tmp_path / "failed_files").exists()


def test_a_failed_move_is_logged_and_does_not_crash(tmp_path, monkeypatch):
    proc = _make_proc(tmp_path)
    src = _write_lending_tsv(tmp_path, "not an identifier")

    def refuse(self, target):
        raise OSError(22, "Invalid argument")
    monkeypatch.setattr(type(src), "rename", refuse)

    result = proc.process_tsv_file(src)

    assert result["status"] == "skipped"
    assert src.exists()


@pytest.mark.parametrize("status, expected", [
    ("success", "moved to processed"),
    ("skipped", "moved to failed"),
])
def test_per_file_log_names_the_destination(tmp_path, monkeypatch, status, expected):
    proc = _make_proc(tmp_path, scheduled_mode=True)
    identifier = "33219451" if status == "success" else "not an identifier"
    src = _write_lending_tsv(tmp_path, identifier)

    proc.process_tsv_file(src)

    logs = list((tmp_path / "output" / "file_logs").glob("*.log"))
    assert len(logs) == 1
    assert f"Move Result: {expected}" in logs[0].read_text(encoding="utf-8")
