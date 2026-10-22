import pytest

from resource_sharing_forms_processor import ResourceSharingFormsProcessor
from rs_requests import get_builder
from rs_requests.base import BuiltRequest, RequestBuilder
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
