import pytest

from rs_requests import get_builder
from rs_requests.base import BuiltRequest, RequestBuilder


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
