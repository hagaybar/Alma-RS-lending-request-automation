#!/usr/bin/env python3
"""Run one SANDBOX test from docs/BORROWING_SB_TEST_MATRIX.md.

Refuses to run without RUN_SB_BORROWING_TESTS=1. SANDBOX only. Prints a
create/GET diff so field settability can be recorded.

    RUN_SB_BORROWING_TESTS=1 poetry run python scripts/sb_borrowing_tests.py --test T-01
    RUN_SB_BORROWING_TESTS=1 poetry run python scripts/sb_borrowing_tests.py --cancel <request_id> --user SHEB
"""
import argparse
import json
import os
import sys

from almaapitk import AlmaAPIClient, AlmaAPIError, Users, build_user_rs_request

if os.environ.get("RUN_SB_BORROWING_TESTS") != "1":
    sys.exit("Refusing to run: set RUN_SB_BORROWING_TESTS=1 to enable SANDBOX writes.")

# Constants the builder has no kwarg for (guidebook §4.1); the builder wraps
# what needs wrapping and passes these through.
EXTRA = {
    "requested_media": "7",
    "allow_other_formats": False,
    "willing_to_pay": False,
}

TESTS = {
    # Bodies come from build_user_rs_request — the same call path production
    # uses — so a harness pass vouches for the real payload shape.
    # agree_to_copyright_terms must be True at create: SANDBOX rejects False
    # outright (401897 "Invalid field value", 2026-07-30) — the T-04b verdict.
    # Stored state may still differ from sent; T-04's GET step records that.
    "T-01": ("SHEB", build_user_rs_request(
        owner="AM1",
        format="DIGITAL",
        citation_type="CR",
        title="Interlibrary loan latency under synthetic load: a sandbox baseline",
        journal_title="Journal of Resource Sharing Diagnostics",
        author="Testerson, A.",
        year="2024",
        pickup_location="AM1",
        pickup_location_type="LIBRARY",
        agree_to_copyright_terms=True,
        extra=EXTRA,
    )),
    # T-02 sends every field from the 100-record sample (matrix §1) so the
    # GET diff can classify each as settable/dropped/transformed. Fields the
    # builder has no kwarg for ride in extra. agree_to_copyright_terms=True
    # per the T-01/T-04 verdict; the fake pmid/doi keep augmentation silent
    # (real-identifier behaviour is T-02b's job).
    "T-02": ("SHEB", build_user_rs_request(
        owner="AM1",
        format="DIGITAL",
        citation_type="CR",
        title="Field settability of the Alma user resource-sharing create endpoint",
        journal_title="Journal of Resource Sharing Diagnostics",
        author="Testerson, A.; Probe, B.",
        year="2024",
        pickup_location="AM1",
        pickup_location_type="LIBRARY",
        agree_to_copyright_terms=True,
        external_id="SBTEST-T02-20260720",
        extra={
            **EXTRA,
            "volume": "12",
            "issue": "3",
            "pages": "101-115",
            "start_page": "101",
            "end_page": "115",
            "issn": "0000-0000",
            "pmid": "99999901",
            "doi": "10.9999/sbtest.t02",
            "publisher": "Sandbox Press",
            "place_of_publication": "Tel Aviv",
            "note": "T-02 settability probe",
            "bib_note": "T-02 bib note probe",
            "specific_edition": True,
            "need_patron_info": False,
            "maximum_fee": 0.0,
            "lcc_number": "SHEBA-TAU-9001 Test Patron",
        },
    )),
    # T-02b: T-02 shape but a REAL pmid (33219451, the repo's canonical test
    # article — Remdesivir/Covid-19, 2020) with every metadata string
    # deliberately wrong, so anything augmentation overwrites is unmissable
    # in the diff. No doi — production sends one identifier. The title is
    # wrong-but-distinctive rather than truncated to keep the title-based
    # 401604 holdings check out of the way (matrix rule 4).
    "T-02b": ("SHEB", build_user_rs_request(
        owner="AM1",
        format="DIGITAL",
        citation_type="CR",
        title="Remdesivir probe with deliberately perturbed metadata (T-02b)",
        journal_title="Journal of Resource Sharing Diagnostics",
        author="Testerson, A.",
        year="2015",
        pickup_location="AM1",
        pickup_location_type="LIBRARY",
        agree_to_copyright_terms=True,
        external_id="SBTEST-T02B-20260730",
        extra={
            **EXTRA,
            "volume": "1",
            "issue": "1",
            "pages": "1-2",
            "start_page": "1",
            "end_page": "2",
            "issn": "0000-0000",
            "pmid": "33219451",
            "publisher": "Sandbox Press",
            "place_of_publication": "Tel Aviv",
            "note": "T-02b augmentation probe",
            "bib_note": "T-02b bib note probe",
            "specific_edition": True,
            "need_patron_info": False,
            "maximum_fee": 0.0,
            "lcc_number": "SHEBA-TAU-9001 Test Patron",
        },
    )),
    # Add T-04a/T-07/T-09 from the matrix as they are run.
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", choices=sorted(TESTS))
    ap.add_argument("--cancel")
    ap.add_argument("--user")
    args = ap.parse_args()

    client = AlmaAPIClient("SANDBOX", timeout=180)
    users = Users(client)

    if args.cancel:
        if not args.user:
            return print("--cancel requires --user") or 2
        users.cancel_user_rs_request(args.user, args.cancel)
        print(f"cancelled {args.cancel} for {args.user}")
        return 0

    if not args.test:
        return print("nothing to do: pass --test or --cancel") or 2

    user_id, payload = TESTS[args.test]
    print(f"[{args.test}] POST for user {user_id}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    try:
        response = users.create_user_rs_request(user_id, payload, validate=True)
    except AlmaAPIError as e:
        print(f"FAILED alma_code={getattr(e, 'alma_code', '?')}: {e}")
        return 1

    created = response.data or {}
    request_id = created.get("request_id")
    print(f"created request_id={request_id}")

    fetched = users.get_user_rs_request(user_id, request_id)
    print("\n--- settability diff (sent -> stored) ---")
    for key, sent in sorted(payload.items()):
        stored = fetched.get(key, "<ABSENT>")
        verdict = "ok" if stored == sent else "DIFFERS"
        print(f"  {key:<28} {verdict:<8} sent={sent!r} stored={stored!r}")
    print(f"\nRecord request_id {request_id} in the matrix cleanup log, then cancel it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
