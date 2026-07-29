"""Tests for identifier normalization (issue #7).

The identifier column is free text, so requesters type label prefixes into it —
`PMID: 15320862`, `DOI: 10.1136/bmj.abc`. Auto-detection rejected those and the
file errored out on the production machine.

Two independent defects are covered here:

1. No PMID label handling existed at all — a `PMID:` prefix always failed.
2. `detect_identifier_type`/`validate_identifier` stripped a DOI prefix without
   re-trimming, so *any* prefix followed by a space stopped matching `^10\\.`.
   `DOI: 10.x/y` failed; `DOI:10.x/y` passed only by luck.

The cleaned value has to reach detection, validation, AND the downstream
PubMed/Alma lookup, so normalization happens once at the parse site
(`read_tsv_file`) rather than inside any single consumer.

Scope (issue #7 option B): recognized `PMID`/`DOI` labels are stripped. URL-form
DOIs are detected as before and passed through unchanged — canonicalizing those
is a separate behavior change, deliberately not bundled here.
"""

import pytest

from resource_sharing_forms_processor import (
    ResourceSharingFormsProcessor,
    normalize_identifier,
)


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


def _write_tsv(tmp_path, identifier):
    """Write a single-submission TSV whose identifier column holds `identifier`."""
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    path = input_dir / "BEIL7_6_2026 9_16_56 AM.tsv"
    row = ["BEIL", "Test Requester", "test@example.com", "no", identifier, "", "BEIL-TAU-2277"]
    path.write_text("\t".join(row) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# normalize_identifier: labelled values are cleaned
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("PMID: 15320862", "15320862"),      # the value that broke production
    ("PMID:19583564", "19583564"),
    ("pmid 19583564", "19583564"),
    ("PMID 19583564", "19583564"),
    ("  PMID:   19583564  ", "19583564"),
    ("DOI: 10.1136/bmj.abc", "10.1136/bmj.abc"),
    ("DOI:10.1136/bmj.abc", "10.1136/bmj.abc"),
    ("doi: 10.1136/bmj.abc", "10.1136/bmj.abc"),
])
def test_normalize_strips_recognized_label(raw, expected):
    assert normalize_identifier(raw) == expected


# --------------------------------------------------------------------------
# normalize_identifier: everything else is left exactly as it was
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "19583564",
    "10.1136/bmj.abc",
    "https://doi.org/10.1136/bmj.abc",
    "http://dx.doi.org/10.1136/bmj.abc",
    "garbage",
    "12345",
])
def test_normalize_leaves_unlabelled_values_untouched(raw):
    assert normalize_identifier(raw) == raw


def test_normalize_does_not_mangle_bare_doi_org_host():
    """The label must be followed by a real separator (`:` or whitespace).

    A looser pattern eats the `doi` out of `doi.org/...` and leaves `org/...`,
    turning a recognizable value into nonsense.
    """
    assert normalize_identifier("doi.org/10.1136/bmj.abc") == "doi.org/10.1136/bmj.abc"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_normalize_handles_empty_input(raw):
    assert normalize_identifier(raw) == ""


# --------------------------------------------------------------------------
# Detection: labelled values now detect, junk still does not
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected_type", [
    ("PMID: 15320862", "pmid"),
    ("PMID:19583564", "pmid"),
    ("pmid 19583564", "pmid"),
    ("19583564", "pmid"),
    ("DOI: 10.1136/bmj.abc", "doi"),
    ("doi: 10.1136/bmj.abc", "doi"),
    ("10.1136/bmj.abc", "doi"),
    ("https://doi.org/10.1136/bmj.abc", "doi"),
])
def test_detects_type_after_normalization(tmp_path, raw, expected_type):
    proc = _make_proc(tmp_path)
    assert proc.detect_identifier_type(normalize_identifier(raw)) == expected_type


@pytest.mark.parametrize("raw", [
    "garbage",
    "12345",              # too few digits for a PMID
    "1234567890",         # too many digits for a PMID
    "PMID: 19583564.",    # trailing junk is not "repaired"
    "19583564 (PubMed)",
    "doi.org/10.1136/bmj.abc",
    "",
])
def test_undetectable_values_stay_undetectable(tmp_path, raw):
    proc = _make_proc(tmp_path)
    assert proc.detect_identifier_type(normalize_identifier(raw)) is None


# --------------------------------------------------------------------------
# The missing re-trim, exercised directly on the two methods that had it
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "https://doi.org/ 10.1136/bmj.abc",
    "http://dx.doi.org/ 10.1136/bmj.abc",
])
def test_detects_doi_when_url_prefix_is_followed_by_space(tmp_path, raw):
    proc = _make_proc(tmp_path)
    assert proc.detect_identifier_type(raw) == "doi"


def test_validate_accepts_doi_when_url_prefix_is_followed_by_space(tmp_path):
    proc = _make_proc(tmp_path)
    assert proc.validate_identifier("https://doi.org/ 10.1136/bmj.abc", "doi") is True


def test_validate_accepts_labelled_pmid_after_normalization(tmp_path):
    proc = _make_proc(tmp_path)
    assert proc.validate_identifier(normalize_identifier("PMID: 15320862"), "pmid") is True


# --------------------------------------------------------------------------
# Source-level wiring: the clean value is what leaves the parser, so it is the
# value that reaches detection, validation and the PubMed/Alma lookup.
# --------------------------------------------------------------------------

def test_parsed_identifier_is_normalized(tmp_path):
    proc = _make_proc(tmp_path)
    path = _write_tsv(tmp_path, "PMID: 15320862")

    form_data = proc.read_tsv_file(path)

    assert form_data["identifier"] == "15320862"


def test_parsed_identifier_keeps_url_doi_unchanged(tmp_path):
    """URL-form DOIs are out of scope for cleaning — they must survive intact."""
    proc = _make_proc(tmp_path)
    path = _write_tsv(tmp_path, "https://doi.org/10.1136/bmj.abc")

    form_data = proc.read_tsv_file(path)

    assert form_data["identifier"] == "https://doi.org/10.1136/bmj.abc"
