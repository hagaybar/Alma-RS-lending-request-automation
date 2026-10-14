"""Guard: the pinned almaapitk must ship the borrowing build+create surface.

The floor is the first release carrying build_user_rs_request (expected
0.5.0 — merged upstream 2026-07-22, PR #206; absent through 0.4.6).
"""
import inspect

# Import from the top-level surface — the package declares it "the ONLY
# supported public API"; internal module paths may move without notice (GH #34).
from almaapitk import Users, build_user_rs_request


def test_build_user_rs_request_is_exported():
    sig = inspect.signature(build_user_rs_request)
    # The three positional identity fields of a borrowing body.
    assert list(sig.parameters)[:3] == ["owner", "format", "citation_type"]
    assert "agree_to_copyright_terms" in sig.parameters
    assert "extra" in sig.parameters


def test_create_user_rs_request_has_the_validate_preflight():
    sig = inspect.signature(Users.create_user_rs_request)
    assert list(sig.parameters) == [
        "self", "user_id", "request_data", "user_id_type", "override_blocks",
        "validate", "timeout", "reconcile", "reconcile_marker",
    ]
    for name in ("validate", "timeout", "reconcile", "reconcile_marker"):
        assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_create_user_rs_request_can_reconcile_by_note_marker():
    """submit() passes reconcile=True + the order marker (AlmaAPITK #196,
    almaapitk >= 0.6.0). The marker is how a timed-out create is found."""
    sig = inspect.signature(Users.create_user_rs_request)
    assert sig.parameters["reconcile"].default is False
    assert sig.parameters["reconcile_marker"].default is None
    assert hasattr(Users, "find_user_rs_request_by_marker")


def test_get_user_rs_request_exists_for_the_matrix_diff():
    """The SANDBOX harness GETs the created request to diff settability
    (matrix T-02). Not for reconcile by external_id: Alma replaces it
    (GH #14); reconcile goes by note marker instead (AlmaAPITK #196)."""
    assert hasattr(Users, "get_user_rs_request")
