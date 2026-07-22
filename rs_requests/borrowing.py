"""Borrowing (user resource-sharing) request builder.

Field values trace to docs/BORROWING_REQUESTS.md §4 (1912 real SANDBOX
requests, 100 read in full) and §9 (live upstream evidence, 2026-07-22). Do
not change a value without updating that document and the evidence behind it.

The wire shape is assembled by almaapitk.build_user_rs_request (>= 0.5.0),
which encodes Alma's plain-vs-{"value": ...} wrapping rules once, upstream.
This module owns WHAT to send; the toolkit owns HOW to shape it.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from almaapitk import AlmaAPIError, build_user_rs_request

from rs_requests.base import BuiltRequest, RequestBuilder
from rs_requests.errors import BorrowingValidationError
from rs_requests.pii import mask_lcc_number


#: DECISION 2026-07-22 — articles only. CR is the librarians' UI value and
#: the live-proven shape (DIGITAL+CR, guidebook §9). BK is out of scope
#: (PHYSICAL+BOOK reproducibly 500s in SANDBOX — AlmaAPITK #207); E_CR is
#: accepted at create but DISCARDS journal_title/issue/doi/pmid at persist
#: (A/B probe 2026-07-22) and appears in 0 of 1912 real requests.
ALLOWED_CITATION_TYPES = ("CR",)


class BorrowingRequestBuilder(RequestBuilder):
    kind = "borrowing"
    needs_metadata = True     # the processor enriches before calling build()

    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        cfg = self.processor.borrowing_config
        meta = metadata or {}

        citation_type = (form_data.get("material_type")
                         or cfg.get("default_citation_type", "CR")).upper()
        if citation_type not in ALLOWED_CITATION_TYPES:
            raise BorrowingValidationError(
                f"citation_type {citation_type!r} is out of scope: this "
                f"pipeline creates DIGITAL article requests only "
                f"(DECISION 2026-07-22). Allowed: "
                f"{', '.join(ALLOWED_CITATION_TYPES)}."
            )

        title = meta.get("title", "").strip()
        if not title:
            raise BorrowingValidationError("citation metadata has no title")

        # Every request is an article — the trio is unconditionally
        # mandatory (Alma 401930, confirmed live 2026-07-22).
        missing = [name for name, key in
                   (("journal_title", "journal"), ("author", "author"), ("year", "year"))
                   if not meta.get(key, "").strip()]
        if missing:
            raise BorrowingValidationError(
                f"an article request requires {', '.join(missing)} "
                f"(Alma returns alma_code 401930 without them)"
            )

        hospital = form_data["requestor"]
        order_number = (form_data.get("order_number") or "").strip()
        # Stable across retries (GH #13): the token is the input file's mtime
        # (stamped by the reader), and the sanitized stem is unique among
        # concurrently pending files (a directory cannot hold two files with
        # one name). Same file → same id in every log line and report row, so
        # a retry is traceable to its earlier attempts. Alma does NOT store
        # this id (GH #14) — duplicate safety is Alma's 402362 rejection, see
        # submit().
        token = (form_data.get("file_token") or "").strip()
        if not token:
            raise BorrowingValidationError(
                "file_token missing from form data — reader must stamp it"
            )
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", form_data.get("filename") or "")[:40]
        external_id = f"FORMS-BR-{hospital}-{token}-{stem}"
        if order_number:
            external_id = f"{external_id}-{order_number}"

        # --- extra: everything build_user_rs_request has no kwarg for ----
        # Constants: 100/100 in the verified sample (guidebook §4.1). The
        # builder applies its wrapping rules to `extra` too, so plain values
        # here stay correct even if a field is reclassified upstream.
        extra: Dict[str, Any] = {
            "requested_media": cfg.get("requested_media", "7"),
            "allow_other_formats": False,
            "willing_to_pay": False,
        }

        # Bibliographic fields: included only when non-empty ("" must be
        # omitted, not sent blank). isbn is not mapped: neither toolkit
        # metadata helper can produce it (GH #18); reinstate only after
        # almaapitk grows ISBN extraction.
        for key, source in (("volume", "volume"), ("issue", "issue"),
                            ("pages", "pages"), ("start_page", "start_page"),
                            ("end_page", "end_page"), ("issn", "issn"),
                            ("doi", "doi"), ("pmid", "pmid"),
                            ("publisher", "publisher")):
            value = (meta.get(source) or "").strip()
            if value:
                extra[key] = value

        note = (form_data.get("notes") or "").strip()
        if note:
            extra["note"] = note

        template = (cfg.get("lcc_number_template") or "").strip()
        if template:
            extra["lcc_number"] = template.format(
                hospital=hospital,
                order_number=order_number,
                patron_name=(form_data.get("patron_name") or "").strip(),
            ).strip()
            self.processor._log_pii(
                logging.DEBUG,
                f"  lcc_number: {extra['lcc_number']}",
                f"  lcc_number: {mask_lcc_number(extra['lcc_number'])}",
            )

        # Deliberately NOT sent — see docs/BORROWING_REQUESTS.md:
        #   external_id   Alma discards the client value and substitutes a
        #                 broker id (972TAU…) — GH #14, re-confirmed upstream
        #                 2026-07-22. The local FORMS-BR-… id above exists
        #                 only for logs, reports and file correlation.
        #   partner       assigned by the rota after creation
        #   mms_id        Alma generates a placeholder bib from this metadata
        #   oclc_number   written by the supplier, not the requester
        #   level_of_service / copyright_status  empty in 100/100

        # The toolkit builder owns the wire shape: owner plain,
        # format/citation_type/pickup_location wrapped {"value": ...},
        # pickup_location_type plain (the §4.1 asymmetry, encoded once
        # upstream — AlmaAPITK PR #206, live-proven 2026-07-22). The trio
        # below was validated non-empty above, so the builder's
        # _require_rs_text guards cannot fire here.
        payload = build_user_rs_request(
            owner=cfg.get("owner", "AM1"),
            format=cfg.get("default_format", "DIGITAL"),
            citation_type=citation_type,
            title=title,
            journal_title=meta.get("journal", "").strip(),
            author=meta.get("author", "").strip(),
            year=meta.get("year", "").strip(),
            pickup_location=cfg.get("pickup_location", "AM1"),
            pickup_location_type=cfg.get("pickup_location_type", "LIBRARY"),
            agree_to_copyright_terms=bool(cfg.get("agree_to_copyright_terms", False)),
            extra=extra,
        )

        return BuiltRequest(
            kind=self.kind,
            external_id=external_id,
            payload=payload,
            summary={"detected_type": form_data.get("identifier_type", ""),
                     "title": title, "requestor": hospital,
                     "citation_type": citation_type},
        )

    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        # The processor already wires a Users client (see the processor's
        # __init__); reuse it rather than constructing a second one.
        users = self.processor.users
        hospital = built.summary["requestor"]
        try:
            # validate=True (almaapitk >= 0.5.0): a wrong code-table value
            # raises AlmaValidationError naming the field BEFORE any HTTP.
            response = users.create_user_rs_request(
                hospital, built.payload, validate=True)
        except AlmaAPIError as e:
            if self._is_duplicate_rejection(e):
                # DECISION 2026-07-20 (GH #35): Alma's duplicate check IS the
                # safety mechanism. This fires when an identical request is
                # already active for this patron — most importantly when a
                # previous run's create timed out AFTER saving. Treat as
                # already created: report it and let the file move out of
                # input, ending the retry loop.
                self.processor.logger.warning(
                    f"  Alma rejected as duplicate (402362): an identical "
                    f"active request already exists for {hospital} — "
                    f"treating as already created."
                )
                return {"status": "duplicate",
                        "request_id": "",   # unknowable — Alma doesn't say which
                        "external_id": built.external_id, **built.summary}
            raise
        # requests.RequestException (socket timeout, connection reset) is
        # deliberately NOT caught: almaapitk does not wrap transport errors
        # (GH #9; re-verified on the 2026-07-22 main), and re-raising is
        # correct here — the file stays in
        # input, the next scheduled run re-POSTs, and if this create actually
        # saved, Alma answers 402362 and the branch above finishes the job.
        data = response.data or {}
        self.processor.logger.info("✓ Borrowing request created")
        self.processor.logger.info(f"  Request ID: {data.get('request_id')}")
        return {"status": "success", "request_id": data.get("request_id"),
                "external_id": built.external_id, **built.summary}

    @staticmethod
    def _is_duplicate_rejection(e: AlmaAPIError) -> bool:
        """True when Alma refused the create because an identical request is
        already active for this patron (verified live 2026-07-20, GH #35).

        alma_code is the structural match; the message fallback covers error
        bodies the toolkit could not parse into a code. The substring match
        is unaffected by the ``[almaapitk hint: ...]`` suffix that >= 0.5.0
        appends to some unrenderable Alma 400s.
        """
        if getattr(e, "alma_code", "") == "402362":
            return True
        return "patron has duplicate request" in str(e).lower()
