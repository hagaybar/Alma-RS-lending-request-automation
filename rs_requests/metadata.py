"""Citation metadata, normalised to one internal shape.

The toolkit's PubMed and Crossref helpers return slightly different keys.
Everything downstream consumes this module's output, so any upstream change
is absorbed in one place.
"""
from __future__ import annotations

from typing import Any, Dict

from almaapitk.utils.citation_metadata import (
    CitationMetadataError, get_crossref_metadata, get_pubmed_metadata,
)

# isbn is NOT in FIELDS: neither toolkit helper extracts it (verified against
# 0.4.6 — GH #18); a name that can only ever be empty must not pretend to be
# part of the normalised shape.
FIELDS = ("title", "author", "journal", "year", "volume", "issue", "pages",
          "start_page", "end_page", "issn", "doi", "pmid", "publisher")

#: Placeholder metadata used when building in dry-run: no network calls
#: happen (GH #20), but the payload keeps a valid, inspectable structure.
#: Mirrors the lending path's '[DRY-RUN - Not fetched]' convention.
DRY_RUN_METADATA = {
    "title": "[DRY-RUN - Not fetched]",
    "author": "[DRY-RUN]",
    "journal": "[DRY-RUN]",
    "year": "[DRY-RUN]",
}


def fetch_citation_metadata(identifier: str, id_type: str) -> Dict[str, str]:
    """Fetch and normalise citation metadata for a PMID or DOI."""
    if id_type == "pmid":
        raw: Dict[str, Any] = get_pubmed_metadata(identifier)
    elif id_type == "doi":
        raw = get_crossref_metadata(identifier)
    else:
        raise CitationMetadataError(f"unsupported identifier type: {id_type!r}")

    out = {k: str(raw.get(k, "") or "").strip() for k in FIELDS}
    # Alma stores page range both whole and split; derive the split when the
    # source only gives the range.
    if out["pages"] and not out["start_page"]:
        parts = out["pages"].replace("--", "-").split("-", 1)
        out["start_page"] = parts[0].strip()
        out["end_page"] = parts[1].strip() if len(parts) > 1 else ""
    return out
