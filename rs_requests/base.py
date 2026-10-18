"""Request-building interface shared by the lending and borrowing paths.

The processor owns the pipeline (watch, parse, enrich, move, report). A
builder owns only the last two steps: turning parsed form data into an Alma
request body, and submitting it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BuiltRequest:
    """A request that has been assembled but not necessarily sent."""

    kind: str
    external_id: str
    payload: Dict[str, Any]
    summary: Dict[str, str] = field(default_factory=dict)


class RequestBuilder(ABC):
    """Turns parsed form data into an Alma request, and submits it."""

    #: "lending" or "borrowing" — also the config key and report label.
    kind: str = ""

    #: When True the processor fetches citation metadata and passes it to
    #: build(). Lending is False because the toolkit enriches internally.
    needs_metadata: bool = False

    def __init__(self, processor: Any) -> None:
        self.processor = processor

    @abstractmethod
    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        """Assemble the request. Must not perform network I/O."""

    @abstractmethod
    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        """Send the request to Alma. Only called when not in dry-run."""
