"""Characterization: freeze what the lending path builds today.

Runs in dry-run, so no API call is made. Asserts on the params dict handed
to the toolkit, captured by monkeypatching the domain object.
"""
import json
from pathlib import Path

import pytest

from resource_sharing_forms_processor import ResourceSharingFormsProcessor
from tests.borrowing_fixtures import CONFIG

FORM = {
    "filename": "sample", "filepath": Path("sample.tsv"),
    "partner_code": "SHEB", "user_name": "Levi, David", "user_id": "",
    "is_faculty": "yes", "identifier": "33219451",
    "notes": "urgent", "order_number": "Order_Num_24586",
}


def test_lending_params_are_unchanged(tmp_path):
    proc = ResourceSharingFormsProcessor(CONFIG, dry_run=True)
    result = proc.create_lending_request_from_form(dict(FORM))

    assert result["status"] == "dry_run_success"
    assert result["detected_type"] == "pmid"
    # Pins the CSV Title column through the refactor (GH #26) — the dry-run
    # placeholder must survive the move into rs_requests/ byte for byte.
    assert result["title"] == "[DRY-RUN - Not fetched]"
    # external_id embeds a timestamp; assert its shape, not its value
    assert result["external_id"].startswith("FORMS-SHEB-")
    assert result["external_id"].endswith("-Order_Num_24586")
    assert len(result["external_id"].split("-")) == 4
