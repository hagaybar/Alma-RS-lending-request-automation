"""L2 offline mock/golden test — pins THIS repo's own request-building logic.

Mirrors ``Fetch_Alma_Analytics_Reports/tests/test_diff_harness.py`` in intent
(synthetic input → real code path → assert against committed golden), adapted
for a *mutating* repo: instead of comparing output files, we capture the exact
keyword arguments this repo hands to almaapitk's
``ResourceSharing.create_lending_request_from_citation`` and compare them to a
committed golden (``golden/l2_citation_params.json``).

What this pins (the repo's own logic, NOT almaapitk's):
  * identifier auto-detection (PMID 6-9 digits vs DOI ``10.x/...``), incl. DOI
    URL/prefix pass-through;
  * ``external_id`` assembly (``FORMS-<partner>-<DDMMYYYYHHMMSS>[-<order>]``);
  * the ``source_type`` flag and pmid/doi routing;
  * the structured ``note`` builder across every requester branch:
    verified Academic-staff, verified non-Academic-staff, user-not-found (404),
    and no-user-id (form data as-is).

Fully offline: the almaapitk boundary (``rs`` and ``users``) is mocked, so no
network and no PubMed/Crossref/Alma calls. The wall-clock timestamp inside
``external_id`` is normalised to ``<TS>`` before comparison so the golden stays
deterministic while still pinning the surrounding structure.

This test must stay green across the 0.4.5 → 0.4.6 bump: almaapitk's
``resource_sharing.py`` is byte-identical across the bump (see
``docs/almaapitk-audit.md``), and this repo's request-building logic does not
change, so the captured kwargs are unaffected.
"""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Import the single-file processor from the repo root (mirrors the existing
# offline tests, e.g. test_pii_logging.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resource_sharing_forms_processor import ResourceSharingFormsProcessor  # noqa: E402
from almaapitk import AlmaAPIError  # noqa: E402

GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "l2_citation_params.json").read_text(encoding="utf-8")
)

# A canned response object standing in for almaapitk's create_lending_request_*
# return dict. The processor reads request['request_id'] and request.get('title').
MOCK_CREATE_RESULT = {"request_id": "GOLDEN-REQ-1", "title": "Mock Title (not asserted)"}

_TS_RE = re.compile(r"(?<=-)\d{14}(?=-|$)")  # the DDMMYYYYHHMMSS stamp, exactly 14 digits


def _normalise_external_id(external_id: str) -> str:
    """Replace the 14-digit wall-clock stamp with ``<TS>`` so goldens are stable."""
    return _TS_RE.sub("<TS>", external_id)


def _make_live_processor(tmp_path) -> ResourceSharingFormsProcessor:
    """Build a processor offline, then flip it into the live (mocked) code path.

    Constructing with ``dry_run=True`` avoids any AlmaAPIClient/network setup in
    ``__init__``. We then set ``dry_run=False`` and inject mocks for the two
    almaapitk domain objects the live path touches, so
    ``create_lending_request_from_form`` exercises its real request-building
    branch without a real client.
    """
    config = {
        "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
        "file_processing": {
            "input_folder": str(tmp_path / "input"),
            "processed_folder": str(tmp_path / "processed"),
            "output_dir": str(tmp_path / "output"),
        },
    }
    proc = ResourceSharingFormsProcessor(config, dry_run=True)

    # Flip into the live branch with mocked almaapitk boundaries.
    proc.dry_run = False
    proc.rs = MagicMock()
    proc.rs.create_lending_request_from_citation.return_value = dict(MOCK_CREATE_RESULT)
    proc.users = MagicMock()  # configured per-scenario by the caller
    return proc


def _configure_user_lookup(proc, kind: str) -> None:
    """Wire proc.users.get_user to model each Alma user-lookup outcome."""
    if kind == "academic":
        proc.users.get_user.return_value = SimpleNamespace(
            data={
                "first_name": "Jane",
                "last_name": "Researcher",
                "user_group": {"value": "04", "desc": "Academic staff"},
            }
        )
    elif kind == "nonacademic":
        proc.users.get_user.return_value = SimpleNamespace(
            data={
                "first_name": "Bob",
                "last_name": "Student",
                "user_group": {"value": "02", "desc": "Undergraduate"},
            }
        )
    elif kind == "notfound":
        proc.users.get_user.side_effect = AlmaAPIError("User not found", status_code=404)
    elif kind == "none":
        # No user_id in the form → lookup is never attempted; nothing to wire.
        pass
    else:  # pragma: no cover - guards against a typo in a scenario
        raise ValueError(f"unknown user-lookup kind: {kind!r}")


# (scenario_name, form_data, user-lookup kind). scenario_name keys into GOLDEN.
SCENARIOS = [
    (
        "pmid_academic_staff",
        {
            "partner_code": "ANC",
            "identifier": "33219451",  # 8-digit PMID
            "user_name": "form name (ignored when Alma lookup succeeds)",
            "user_id": "0273601",
            "is_faculty": "yes",
            "notes": "",
            "order_number": "",
        },
        "academic",
    ),
    (
        "doi_non_academic",
        {
            "partner_code": "RELAIS",
            "identifier": "10.1038/s41591-020-1124-9",
            "user_name": "form name (ignored)",
            "user_id": "0271111",
            "is_faculty": "no",
            "notes": "",
            "order_number": "",
        },
        "nonacademic",
    ),
    (
        "pmid_user_not_found",
        {
            "partner_code": "ANC",
            "identifier": "12345678",
            "user_name": "Bob Notfound",
            "user_id": "0279999",
            "is_faculty": "yes",
            "notes": "",
            "order_number": "",
        },
        "notfound",
    ),
    (
        "doi_no_user_id",
        {
            "partner_code": "RELAIS",
            "identifier": "10.1000/xyz123",
            "user_name": "Anon Requester",
            "user_id": "",
            "is_faculty": "no",
            "notes": "",
            "order_number": "",
        },
        "none",
    ),
    (
        "pmid_order_and_notes",
        {
            "partner_code": "ANC",
            "identifier": "33219451",
            "user_name": "form name (ignored)",
            "user_id": "0273601",
            "is_faculty": "yes",
            "notes": "please rush",
            "order_number": "PO1001",
        },
        "academic",
    ),
    (
        "doi_prefixed_passthrough",
        {
            "partner_code": "ANC",
            "identifier": "https://doi.org/10.1038/s41591-020-1124-9",
            "user_name": "Anon Requester",
            "user_id": "",
            "is_faculty": "no",
            "notes": "",
            "order_number": "",
        },
        "none",
    ),
]


@pytest.mark.parametrize("name,form_data,user_kind", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_citation_params_match_golden(name, form_data, user_kind, tmp_path):
    proc = _make_live_processor(tmp_path)
    _configure_user_lookup(proc, user_kind)

    result = proc.create_lending_request_from_form(form_data)

    # The repo must hand the toolkit exactly one create call...
    proc.rs.create_lending_request_from_citation.assert_called_once()
    kwargs = dict(proc.rs.create_lending_request_from_citation.call_args.kwargs)
    kwargs["external_id"] = _normalise_external_id(kwargs["external_id"])

    assert kwargs == GOLDEN[name]

    # ...and surface the toolkit's result back through its own result dict.
    assert result["status"] == "success"
    assert result["request_id"] == MOCK_CREATE_RESULT["request_id"]
    assert result["detected_type"] == GOLDEN[name]["source_type"]


def test_unknown_identifier_never_calls_toolkit(tmp_path):
    """Identifier that is neither PMID nor DOI must raise before any write."""
    from resource_sharing_forms_processor import IdentifierDetectionError

    proc = _make_live_processor(tmp_path)
    bad_form = {
        "partner_code": "ANC",
        "identifier": "not-an-identifier",
        "user_name": "",
        "user_id": "",
        "is_faculty": "",
        "notes": "",
        "order_number": "",
    }
    with pytest.raises(IdentifierDetectionError):
        proc.create_lending_request_from_form(bad_form)
    proc.rs.create_lending_request_from_citation.assert_not_called()
