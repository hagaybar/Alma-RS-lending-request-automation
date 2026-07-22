"""Request builders for the resource-sharing forms processor."""
from typing import Any

from rs_requests.base import BuiltRequest, RequestBuilder

__all__ = ["BuiltRequest", "RequestBuilder", "get_builder"]


def get_builder(kind: str, *, processor: Any) -> RequestBuilder:
    """Return the builder for a request kind.

    Imported lazily so that a broken borrowing module can never prevent the
    production lending path from starting.
    """
    if kind == "lending":
        from rs_requests.lending import LendingRequestBuilder
        return LendingRequestBuilder(processor)
    if kind == "borrowing":
        from rs_requests.borrowing import BorrowingRequestBuilder
        return BorrowingRequestBuilder(processor)
    raise ValueError(f"unknown request kind: {kind!r}")
