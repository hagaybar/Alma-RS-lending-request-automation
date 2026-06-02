"""L3 live smoke (opt-in) — creates ONE real lending request in SANDBOX.

This is the only check with real-Alma certainty; the L2 golden test
(``test_l2_citation_golden.py``) mocks the almaapitk boundary. It is the
consumer-side replacement for hand-running the old demo scripts, and it is the
acceptance gate for the ``almaapitk`` bump on this *mutating* repo.

OPT-IN. It never runs during a normal ``pytest`` (which would otherwise hit
Alma). Enable it deliberately:

    export ALMA_SB_API_KEY=<your real SANDBOX key>      # SANDBOX key ONLY
    cp tests/live_smoke_data.example.json tests/live_smoke_data.json
    # edit tests/live_smoke_data.json with a real SANDBOX partner code + identifier
    RUN_LIVE_SMOKE=1 poetry run pytest tests/test_live_smoke.py -v -s

SANDBOX-ONLY, ALWAYS (operator decision, see docs/almaapitk-audit.md §F):
  * The environment is hard-pinned to ``SANDBOX`` here and asserted; the test
    never reads ``ALMA_PROD_API_KEY`` and refuses to run against PRODUCTION.
  * It does a real WRITE (creates a lending request). There is **no teardown** —
    SANDBOX is disposable, that is what it is for.
  * It does **not** retry the create on a transient 5xx/429: almaapitk 0.4.6 no
    longer auto-retries POST (issue #166), and a manual retry on a write could
    create a duplicate. A transient failure is therefore *skipped* (a flaky API
    is not a code regression), never retried.

PII discipline: prints only the Alma ``request_id`` and the almaapitk version —
never the partner code, user id, identifier, owner, or any name.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA = Path(__file__).parent / "live_smoke_data.json"

# Transient Alma hiccups — skip rather than fail, and never retry a write.
_TRANSIENT = ("500", "502", "503", "504", "429", "timeout", "Max retries", "too many", "temporarily")

live_only = pytest.mark.skipif(
    os.getenv("RUN_LIVE_SMOKE") != "1",
    reason="opt-in live smoke — set RUN_LIVE_SMOKE=1 and a real ALMA_SB_API_KEY",
)


def _load_smoke_data() -> dict:
    if not DATA.exists():
        pytest.skip(
            f"no {DATA.name} — copy tests/live_smoke_data.example.json to "
            f"{DATA.name} and fill real SANDBOX values"
        )
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for required in ("partner_code", "owner", "identifier"):
        val = str(data.get(required, "")).strip()
        if not val or val.startswith("<"):
            pytest.skip(f"{DATA.name}: {required!r} is unset or still a placeholder")
    return data


def _is_transient(exc: Exception) -> bool:
    return any(tok in str(exc) for tok in _TRANSIENT)


@live_only
def test_live_sandbox_lending_request_create():
    """Create one real lending request in SANDBOX and confirm it succeeded."""
    import almaapitk
    from resource_sharing_forms_processor import (
        ResourceSharingFormsProcessor,
        LendingRequestError,
        MetadataFetchError,
    )

    data = _load_smoke_data()

    # --- HARD PRODUCTION refusal -------------------------------------------
    # Environment is pinned to SANDBOX here, not taken from the data file, so a
    # mistyped config can never point this write at PRODUCTION.
    environment = "SANDBOX"
    assert environment == "SANDBOX", "live smoke is SANDBOX-only"

    key = os.getenv("ALMA_SB_API_KEY", "")
    if not key:
        pytest.skip("ALMA_SB_API_KEY is unset — export your REAL SANDBOX key first")
    # Defensive: this test must never depend on the production key.
    assert "ALMA_PROD_API_KEY" not in os.environ or environment == "SANDBOX"

    import tempfile

    out_dir = tempfile.mkdtemp(prefix="rs_smoke_")
    config = {
        "alma_settings": {
            "environment": environment,
            "owner": data["owner"],
            "format_type": data.get("format_type", "DIGITAL"),
        },
        "file_processing": {
            "input_folder": str(Path(out_dir) / "input"),
            "processed_folder": str(Path(out_dir) / "processed"),
            "output_dir": str(Path(out_dir) / "output"),
        },
    }

    try:
        proc = ResourceSharingFormsProcessor(config, dry_run=False)
    except Exception as exc:  # connection/auth set-up failure
        if _is_transient(exc):
            pytest.skip(f"SANDBOX transient failure during client set-up (not a code break): {exc}")
        raise
    # Belt-and-braces: the constructed client really is SANDBOX.
    assert proc.environment == "SANDBOX"

    form_data = {
        "partner_code": data["partner_code"],
        "identifier": data["identifier"],
        "user_name": data.get("user_name", ""),
        "user_id": data.get("user_id", ""),
        "is_faculty": data.get("is_faculty", ""),
        "notes": data.get("notes", "L3 live smoke"),
        "order_number": data.get("order_number", ""),
    }

    try:
        result = proc.create_lending_request_from_form(form_data)
    except MetadataFetchError as exc:
        # Citation enrichment (PubMed/Crossref) is an external dependency; a
        # transient there is not an almaapitk-bump regression.
        if _is_transient(exc):
            pytest.skip(f"citation-metadata transient failure (not a code break): {exc}")
        raise
    except LendingRequestError as exc:
        if _is_transient(exc):
            # Deliberately NOT retried — a write retry risks a duplicate request.
            pytest.skip(f"Alma transient failure on create (not a code break): {exc}")
        raise

    assert result["status"] == "success", f"unexpected status: {result.get('status')}"
    assert result.get("request_id"), "create reported success but returned no request_id"

    # PII-safe: request_id is an Alma request handle, not patron data.
    print(
        f"\nLive SANDBOX smoke OK — created lending request_id={result['request_id']} "
        f"on almaapitk {getattr(almaapitk, '__version__', '?')}. "
        f"No teardown (SANDBOX is disposable)."
    )
