from types import SimpleNamespace

import pytest
import requests

from almaapitk import AlmaAPIError, AlmaValidationError

from rs_requests.borrowing import BorrowingRequestBuilder, BorrowingValidationError
from tests.borrowing_fixtures import FORM, META


class FakeProcessor:
    dry_run = True
    users = None          # set by _builder_with() for the submit() tests
    borrowing_config = {
        "owner": "AM1", "pickup_location": "AM1",
        "pickup_location_type": "LIBRARY", "default_format": "DIGITAL",
        "default_citation_type": "CR", "requested_media": "7",
        "agree_to_copyright_terms": True, "lcc_number_template": "",
    }
    class logger:
        @staticmethod
        def info(*a, **k): pass
        @staticmethod
        def debug(*a, **k): pass
        @staticmethod
        def warning(*a, **k): pass
    def _log_pii(self, *a, **k): pass


def _build(form=None, meta=None, config=None):
    proc = FakeProcessor()
    if config:
        proc.borrowing_config = {**FakeProcessor.borrowing_config, **config}
    return BorrowingRequestBuilder(proc).build({**FORM, **(form or {})},
                                               {**META, **(meta or {})})


def _builder_with(users):
    """A builder whose processor exposes the given (fake) Users client."""
    proc = FakeProcessor()
    proc.users = users
    return BorrowingRequestBuilder(proc)


def test_constants_match_the_verified_template():
    p = _build().payload
    assert p["owner"] == "AM1"                       # plain string
    assert p["pickup_location"] == {"value": "AM1"}  # wrapped
    assert p["pickup_location_type"] == "LIBRARY"
    assert p["requested_media"] == "7"
    assert p["allow_other_formats"] is False
    assert p["willing_to_pay"] is False


def test_defaults_to_digital_article():
    p = _build().payload
    assert p["format"] == {"value": "DIGITAL"}
    assert p["citation_type"] == {"value": "CR"}


def test_material_type_bk_is_rejected():
    """DECISION 2026-07-22: articles only. BK is out of scope until the
    PHYSICAL+BOOK SANDBOX 500 (AlmaAPITK #207) is decomposed and a book
    recipe is proven live."""
    with pytest.raises(BorrowingValidationError, match="out of scope"):
        _build(form={"material_type": "BK"})


def test_rejects_electronic_citation_codes():
    """E_CR is accepted at create but DISCARDS journal_title/issue/doi/pmid
    at persist (A/B probe 2026-07-22, guidebook §9) — and appears in 0 of
    1912 real requests."""
    with pytest.raises(BorrowingValidationError, match="E_CR"):
        _build(form={"material_type": "E_CR"})


def test_article_requires_journal_author_year():
    with pytest.raises(BorrowingValidationError, match="journal_title"):
        _build(meta={"journal": ""})


def test_omits_partner_mms_id_and_oclc_number():
    # external_id leads the tuple: Alma discards it (GH #14) and the toolkit
    # builder actively invites passing it — this line is the regression pin.
    p = _build().payload
    for absent in ("external_id", "partner", "mms_id", "oclc_number",
                   "level_of_service", "copyright_status"):
        assert absent not in p


def test_external_id_is_stable_and_identifies_the_source():
    """Same file → same id on every retry (GH #13); no wall-clock component."""
    a = _build().external_id
    b = _build().external_id
    assert a == b == "FORMS-BR-SHEB-20072026143205-r-Order_9"


def test_lcc_number_omitted_when_template_empty():
    assert "lcc_number" not in _build().payload


def test_lcc_number_rendered_from_template():
    p = _build(config={"lcc_number_template": "{hospital}-TAU-{order_number}"}).payload
    assert p["lcc_number"] == "SHEB-TAU-Order_9"


def test_lcc_number_template_with_unknown_placeholder_is_rejected():
    """A config typo in the template must be a permanent validation failure,
    not a KeyError escaping to the processor's generic (retryable) handler."""
    with pytest.raises(BorrowingValidationError, match="hopital"):
        _build(config={"lcc_number_template": "{hopital}-x {patron_name}"})


def test_copyright_flag_is_config_driven():
    assert _build().payload["agree_to_copyright_terms"] is True
    assert _build(config={"agree_to_copyright_terms": False}
                  ).payload["agree_to_copyright_terms"] is False


def test_empty_metadata_fields_are_omitted_not_sent_blank():
    p = _build(meta={"isbn": "", "publisher": ""}).payload
    assert "isbn" not in p
    assert "publisher" not in p


# --- submit(): a failed create must never be blind-retried -------------------

class _FakeUsers:
    """Users stand-in whose create always raises exc (failure-path tests)."""

    def __init__(self, exc=None):
        self.creates = 0
        self.exc = exc if exc is not None else AlmaAPIError("HTTP 500")

    def create_user_rs_request(self, user_id, request_data, **kw):
        self.creates += 1
        self.last_kwargs = kw
        raise self.exc


def _alma_error(message, code=""):
    e = AlmaAPIError(message)
    e.alma_code = code
    return e


def test_duplicate_rejection_means_already_created():
    """402362 = an identical active request exists — most importantly when a
    previous run's create timed out AFTER saving. DECISION 2026-07-20
    (GH #35): report done, never blind-retry."""
    users = _FakeUsers(exc=_alma_error(
        "Failed to save the request: Patron has duplicate request", "402362"))
    result = _builder_with(users).submit(_build())
    assert result["status"] == "duplicate"
    assert result["request_id"] == ""
    assert users.creates == 1


def test_duplicate_rejection_matches_by_message_when_code_missing():
    users = _FakeUsers(exc=_alma_error(
        "Failed to save the request: Patron has duplicate request"))
    assert _builder_with(users).submit(_build())["status"] == "duplicate"


def test_other_api_errors_reraise():
    users = _FakeUsers(exc=_alma_error(
        "Patron is not affiliated with a resource sharing library", "401768"))
    with pytest.raises(AlmaAPIError):
        _builder_with(users).submit(_build())
    assert users.creates == 1        # never internally retried
    # The opt-in pre-flight (almaapitk >= 0.5.0) must be on for every create.
    assert users.last_kwargs.get("validate") is True


def test_validation_error_becomes_permanent_borrowing_validation_error():
    """AlmaValidationError subclasses ValueError, NOT AlmaAPIError — without
    an explicit catch it would escape to the processor's generic handler as
    a retryable 'error', retried every minute for a permanent config typo
    (e.g. an undocumented code-table value)."""
    users = _FakeUsers(exc=AlmaValidationError(
        "format=BOGUS is not a documented code-table value"))
    with pytest.raises(BorrowingValidationError, match="not a documented"):
        _builder_with(users).submit(_build())
    assert users.creates == 1


def test_transport_timeout_reraises_for_the_next_scheduled_run():
    """almaapitk does not wrap transport errors (GH #9; re-verified on the
    2026-07-22 main); a socket timeout must propagate. The file then stays
    in input, the next run
    re-POSTs, and if this create actually saved Alma rejects it 402362 —
    which the duplicate branch converts to done."""
    users = _FakeUsers(exc=requests.exceptions.ReadTimeout("read timed out"))
    with pytest.raises(requests.exceptions.ReadTimeout):
        _builder_with(users).submit(_build())
    assert users.creates == 1


# --- submit(): Alma's self-ownership block (401604) --------------------------
#
# Alma's Self Ownership check is title-level and coverage-blind
# (docs/BORROWING_REQUESTS.md §10). Power Automate's LibKey check, which put
# the file on this path at all, is article-level. So a 401604 here means "we
# hold the journal, for other years" — not "we can supply this article".
# RS team approved clearing it automatically, 2026-09-03 (§10.8).

class _FakeUsersSeq:
    """Users stand-in that plays a scripted sequence of outcomes.

    Each entry is either an exception to raise or a dict to return as
    ``response.data``. Records the kwargs and body of every call.
    """

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []          # list of (request_data, kwargs)

    def create_user_rs_request(self, user_id, request_data, **kw):
        self.calls.append((request_data, kw))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(data=outcome)

    @property
    def creates(self):
        return len(self.calls)


def _self_ownership_error(code="401604"):
    return _alma_error(
        "Warning - The institutional inventory has services for the "
        "requested title.", code)


def test_self_ownership_block_is_retried_with_the_override():
    """401604 must not fail the file: retry once with override_blocks=True."""
    users = _FakeUsersSeq(_self_ownership_error(),
                          {"request_id": "43256811230004146"})
    result = _builder_with(users).submit(_build())

    assert users.creates == 2
    assert result["status"] == "success"
    assert result["request_id"] == "43256811230004146"


def test_the_first_attempt_never_carries_the_override():
    """Refinement agreed 2026-09-03: override only on retry, so an ordinary
    create cannot silently clear a genuine patron block (fines, expired
    account, loan limit)."""
    users = _FakeUsersSeq({"request_id": "1"})
    _builder_with(users).submit(_build())

    assert users.creates == 1
    assert users.calls[0][1].get("override_blocks") is None


def test_only_the_retry_carries_the_override():
    users = _FakeUsersSeq(_self_ownership_error(), {"request_id": "1"})
    _builder_with(users).submit(_build())

    assert users.calls[0][1].get("override_blocks") is None
    assert users.calls[1][1]["override_blocks"] is True
    # The pre-flight stays on for the retry too.
    assert users.calls[1][1].get("validate") is True


def test_the_retry_is_stamped_so_it_can_be_found_later():
    """These requests go straight out (§10.7), so the only way to audit one
    afterwards is a marker on the request itself."""
    users = _FakeUsersSeq(_self_ownership_error(), {"request_id": "1"})
    built = _build(form={"notes": "urgent please"})
    _builder_with(users).submit(built)

    note = users.calls[1][0]["note"]
    assert "urgent please" in note          # the requester's note survives
    assert "401604" in note


def test_the_stamp_does_not_leak_into_the_first_attempt():
    users = _FakeUsersSeq(_self_ownership_error(), {"request_id": "1"})
    _builder_with(users).submit(_build(form={"notes": "urgent please"}))

    assert users.calls[0][0].get("note") == "urgent please"


def test_the_result_records_that_the_override_was_used():
    users = _FakeUsersSeq(_self_ownership_error(), {"request_id": "1"})
    result = _builder_with(users).submit(_build())
    assert result["self_ownership_override"] is True

    users = _FakeUsersSeq({"request_id": "1"})
    assert _builder_with(users).submit(_build())["self_ownership_override"] is False


def test_self_ownership_matches_by_message_when_the_code_is_missing():
    users = _FakeUsersSeq(_self_ownership_error(code=""),
                          {"request_id": "1"})
    assert _builder_with(users).submit(_build())["status"] == "success"
    assert users.creates == 2


def test_the_override_can_be_switched_off_in_config():
    """Kill switch, matching borrowing.enabled: pause the behaviour without
    a code change. Off means 401604 propagates as before."""
    users = _FakeUsersSeq(_self_ownership_error())
    builder = _builder_with(users)
    builder.processor.borrowing_config = {
        **FakeProcessor.borrowing_config, "override_self_ownership": False}

    with pytest.raises(AlmaAPIError):
        builder.submit(_build())
    assert users.creates == 1


def test_a_duplicate_on_the_retry_is_still_recognised():
    """The retry re-POSTs, so it can hit Alma's duplicate check exactly as a
    next-run re-POST would (§8.2) — that must still mean 'already created',
    not an error."""
    users = _FakeUsersSeq(
        _self_ownership_error(),
        _alma_error("Failed to save the request: Patron has duplicate request",
                    "402362"))
    result = _builder_with(users).submit(_build())

    assert result["status"] == "duplicate"
    assert users.creates == 2


def test_the_override_is_not_applied_twice():
    """If the override itself is refused 401604, that is a genuine failure —
    never loop."""
    users = _FakeUsersSeq(_self_ownership_error(), _self_ownership_error())
    with pytest.raises(AlmaAPIError):
        _builder_with(users).submit(_build())
    assert users.creates == 2
