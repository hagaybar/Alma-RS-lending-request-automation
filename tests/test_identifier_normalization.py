"""Tests for identifier normalization.

Root cause (2026-07-06): Microsoft Forms submissions began arriving with a
literal ``PMID: `` prefix in the identifier column (e.g. ``PMID: 15320862``).
The auto-detection strips DOI-style prefixes (``doi:``, ``https://doi.org/``)
but had no equivalent for a PMID prefix, so ``detect_identifier_type`` returned
``None`` and every such file errored out with:

    Could not detect identifier type: 'PMID: 15320862'.

The fix normalizes a leading PMID prefix once, at the source of the data flow,
so the cleaned value reaches detection, validation, and the downstream lookup.
"""

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


def test_pmid_prefix_is_stripped(tmp_path):
    proc = _make_proc(tmp_path)
    cases = [
        ("PMID: 15320862", "15320862"),   # the real failing case (colon + space)
        ("PMID:19583564", "19583564"),    # no space after colon
        ("pmid: 19583564", "19583564"),   # lowercase
        ("  PMID  15320862 ", "15320862"),  # spaced, surrounding whitespace
        ("15320862", "15320862"),         # bare PMID unchanged
        ("10.1000/abc", "10.1000/abc"),   # DOI untouched (no pmid prefix)
        ("", ""),                          # empty stays empty
    ]
    for raw, expected in cases:
        assert proc._normalize_identifier(raw) == expected, f"failed on {raw!r}"


def test_pmid_prefixed_value_detects_and_validates(tmp_path):
    """The full path that was broken: normalize -> detect -> validate."""
    proc = _make_proc(tmp_path)
    ident = proc._normalize_identifier("PMID: 15320862")
    assert proc.detect_identifier_type(ident) == "pmid"
    assert proc.validate_identifier(ident, "pmid") is True


def test_doi_normalization_is_unaffected(tmp_path):
    """A DOI must still detect correctly and keep its value (no PMID stripping)."""
    proc = _make_proc(tmp_path)
    ident = proc._normalize_identifier("10.1136/bmj.39489.470347.AD")
    assert ident == "10.1136/bmj.39489.470347.AD"
    assert proc.detect_identifier_type(ident) == "doi"
