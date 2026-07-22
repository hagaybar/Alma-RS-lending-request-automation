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
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("SHEB\t33219451\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["requestor"] == "SHEB"
    assert data["identifier"] == "33219451"
    assert data["notes"] == ""
    assert data["material_type"] == ""


def test_parses_optional_columns_when_present(tmp_path):
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("BEIL\t10.1038/x\turgent\tBK\tOrder_9\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["material_type"] == "BK"
    assert data["order_number"] == "Order_9"


def test_rejects_unknown_hospital(tmp_path):
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("NOTAHOSPITAL\t33219451\n", encoding="utf-8")
    with pytest.raises(FileProcessingError, match="not a configured hospital"):
        _proc(tmp_path).read_borrowing_tsv_file(f)


def test_rejects_missing_identifier(tmp_path):
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("SHEB\t\n", encoding="utf-8")
    with pytest.raises(FileProcessingError, match="identifier is empty"):
        _proc(tmp_path).read_borrowing_tsv_file(f)


def test_column_positions_are_config_driven(tmp_path):
    """A future Power Automate change must be a config edit, not a code edit."""
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("33219451\tSHEB\n", encoding="utf-8")
    proc = _proc(tmp_path, columns={"identifier": 0, "requestor": 1})
    data = proc.read_borrowing_tsv_file(f)
    assert data["requestor"] == "SHEB"
    assert data["identifier"] == "33219451"
