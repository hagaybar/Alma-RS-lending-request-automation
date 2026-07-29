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
    # material_type must be CR (or blank) — anything else is out of scope
    # and now rejected at read time (see test_material_type_bk_is_rejected_
    # before_any_metadata_fetch below).
    f.write_text("BEIL\t10.1038/x\turgent\tCR\tOrder_9\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["material_type"] == "CR"
    assert data["order_number"] == "Order_9"


@pytest.mark.parametrize("raw, expected", [
    ("PMID: 15320862", "15320862"),
    ("pmid 33219451", "33219451"),
    ("DOI: 10.1038/x", "10.1038/x"),
])
def test_strips_human_typed_label_from_identifier(tmp_path, raw, expected):
    """Issue #7 applies to the borrowing folder too — same free-text column.

    Borrowing has its own parse site, so the lending fix does not cover it.
    """
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text(f"SHEB\t{raw}\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["identifier"] == expected


def test_leaves_url_doi_identifier_unchanged(tmp_path):
    """URL-form DOIs are out of scope for cleaning — they must survive intact."""
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("SHEB\thttps://doi.org/10.1038/x\n", encoding="utf-8")
    data = _proc(tmp_path).read_borrowing_tsv_file(f)
    assert data["identifier"] == "https://doi.org/10.1038/x"


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


def test_material_type_bk_is_rejected_before_any_metadata_fetch(tmp_path):
    """Live mode currently fetches PubMed/Crossref every minute forever for a
    parked BK file before build() rejects it. Reject at read time instead so
    a wrong material_type never reaches the metadata-fetch step."""
    (tmp_path / "input_borrowing").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.write_text("SHEB\t33219451\turgent\tBK\tOrder_9\n", encoding="utf-8")
    with pytest.raises(FileProcessingError, match="out of scope"):
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


def test_undetectable_identifier_is_skipped_even_in_dry_run(tmp_path):
    """Dry-run must reject an undetectable identifier too — otherwise it
    returns a false-positive dry_run_success and moves the file (GH final
    review)."""
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("SHEB\tnot-an-id\n", encoding="utf-8")

    proc = _proc(tmp_path)
    result = proc.process_tsv_file(f, kind="borrowing")
    assert result["status"] == "skipped"
    assert result["kind"] == "borrowing"


def test_disabled_borrowing_skips_the_file(tmp_path):
    f = tmp_path / "input_borrowing" / "r.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("SHEB\t33219451\n", encoding="utf-8")
    proc = _proc(tmp_path)
    proc.borrowing_config = {**proc.borrowing_config, "enabled": False}
    result = proc.process_tsv_file(f, kind="borrowing")
    assert result["status"] == "skipped"
