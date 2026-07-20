# Borrowing Requests — SANDBOX Test Matrix

> **Nothing in this file has been executed.** These are proposed requests.
> Every payload targets the Alma **SANDBOX** only.

## Rules for every test below

1. **SANDBOX only.** `AlmaAPIClient("SANDBOX")`, key from `ALMA_SB_API_KEY`.
   Never pass a key on a command line; never print it.
2. **Generous timeout.** `AlmaAPIClient("SANDBOX", timeout=180)`. A create can
   exceed the 60s default and *still save*.
3. **Never hand-retry a create blindly.** A timed-out POST may already have
   saved. `VERIFIED` 2026-07-20: an identical re-POST is rejected `402362`
   while the original is active — that rejection **is** the recovery signal
   (guidebook §8.3). Reconcile-by-`external_id` is **not** available: Alma
   discards client external_ids on POST (guidebook §8.1).
4. **Distinctive titles.** Every test title below is deliberately unlikely to
   match TAU holdings, to avoid `401604` ("institutional inventory has
   services for the requested title"), which blocks the create with HTTP 400.
5. **`SBTEST-<id>-<YYYYMMDD>` external_ids are payload markers only.**
   `VERIFIED` 2026-07-20: Alma discards them on POST (guidebook §8.1), so
   they are *not* an idempotency key and *not* queryable. The cleanup handle
   is the `request_id` from the create **response** — record it immediately.
6. **Clean up.** Every created request must be cancelled via
   `Users.cancel_user_rs_request(user_id, request_id)` and recorded in §4.
   Three test requests from 2026-07-19 were left behind; do not repeat that.
7. **No `override_blocks`** unless a test explicitly calls for it.

Shared constants for all payloads (see `docs/BORROWING_REQUESTS.md` §4.1):

```python
BASE = {
    "owner": "AM1",                          # plain string
    "pickup_location": {"value": "AM1"},     # wrapped
    "pickup_location_type": "LIBRARY",       # plain string
    "allow_other_formats": False,
    "willing_to_pay": False,
}
```

---

## 1. Tests that settle an open question

### T-01 — Minimal baseline (establishes the floor)

**Settles:** the smallest body Alma accepts for a `CR` + `DIGITAL` article.
Everything else is measured as a delta from this.

**User:** `SHEB` · **Expect:** HTTP 200 + `request_id`, in ~3s.

```python
{
    **BASE,
    "format": {"value": "DIGITAL"},
    "citation_type": {"value": "CR"},
    "title": "Interlibrary loan latency under synthetic load: a sandbox baseline",
    "journal_title": "Journal of Resource Sharing Diagnostics",
    "author": "Testerson, A.",
    "year": "2024",
    "external_id": "SBTEST-T01-20260720",
}
```

### T-02 — Full template round-trip ⭐ **the decisive test**

**Settles:** *which fields are settable at create.* Send every field observed
in the 100-record sample, then `GET` the created request and diff field-by-field
against what was sent. **Anything that vanishes is output-only.**

**User:** `SHEB` · **Expect:** HTTP 200, then a diff report.

```python
{
    **BASE,
    "format": {"value": "DIGITAL"},
    "citation_type": {"value": "CR"},
    "title": "Field settability of the Alma user resource-sharing create endpoint",
    "journal_title": "Journal of Resource Sharing Diagnostics",
    "author": "Testerson, A.; Probe, B.",
    "year": "2024",
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
    # --- the fields under suspicion ---
    "requested_media": "7",
    "specific_edition": True,
    "need_patron_info": False,
    "maximum_fee": 0.0,
    "lcc_number": "SHEBA-TAU-9001 Test Patron",
    "external_id": "SBTEST-T02-20260720",
}
```

**Record for each field:** sent → returned → verdict (`settable` /
`dropped` / `transformed`). This table becomes the authority for the builder.

### T-03 — Book chapter (`BK` + `DIGITAL`)

**Settles:** that `BK` is accepted with `DIGITAL`, and which fields a book
request needs (the article trio may not apply).

**User:** `BEIL` · **Expect:** HTTP 200. If it fails with `401930`, the
mandatory-field rule differs for books — record which fields it names.

```python
{
    **BASE,
    "format": {"value": "DIGITAL"},
    "citation_type": {"value": "BK"},
    "title": "Handbook of Sandbox Cataloguing Practice",
    "chapter_title": "Chapter 4: Test Fixtures",
    "author": "Testerson, A.",
    "year": "2021",
    "publisher": "Sandbox Press",
    "isbn": "978-0-000000-00-0",
    "pages": "55-72",
    "external_id": "SBTEST-T03-20260720",
}
```

### T-04 — `agree_to_copyright_terms` (three variants) ⭐

**Settles:** the §4.6 contradiction — the field is `false` on 98/100 real
requests, but our 2026-07-19 recipe sent `true` and the skill file calls it
mandatory.

Run three creates, identical but for this one field:

| Variant | `agree_to_copyright_terms` | External ID |
|---|---|---|
| T-04a | *omitted entirely* | `SBTEST-T04A-20260720` |
| T-04b | `False` | `SBTEST-T04B-20260720` |
| T-04c | `True` | `SBTEST-T04C-20260720` |

**User:** `IC` · Body is T-01's, with the title
`"Copyright agreement flag behaviour on the borrowing create endpoint"`.

**Decision rule:**
- If **a** and **b** both succeed → the field is not mandatory. **Send `false`**
  to match the manual population.
- If **a** or **b** fails and **c** succeeds → it *is* mandatory at create.
  Send `true` and note in the guidebook that stored state will differ from
  manual requests.
- Then `GET` all three and record what each **persisted** — a create may accept
  `true` and store `false`.

### T-05 — Missing article fields (negative)

**Settles:** that the `401930` rule still holds, so our validation can fail
fast locally instead of paying a round trip.

**User:** `SHEB` · **Expect:** HTTP 400, `alma_code 401930`, message naming
Journal Title / Publication Date / Author.

```python
{
    **BASE,
    "format": {"value": "DIGITAL"},
    "citation_type": {"value": "CR"},
    "title": "Article missing its mandatory companions",
    "external_id": "SBTEST-T05-20260720",
    # journal_title, author, year deliberately absent
}
```

### T-06 — Wrong wrapper on `owner` (negative)

**Settles:** confirms the plain-vs-wrapped asymmetry, and gives us the exact
error string to match on for a helpful local message.

**User:** `SHEB` · **Expect:** HTTP 400 `BAD_REQUEST`, "Cannot construct
instance of … UserResourceSharingRequest".

```python
{
    **BASE,
    "owner": {"value": "AM1"},   # WRONG on purpose — should be "AM1"
    "format": {"value": "DIGITAL"},
    "citation_type": {"value": "CR"},
    "title": "Wrapper asymmetry probe",
    "journal_title": "Journal of Resource Sharing Diagnostics",
    "author": "Testerson, A.",
    "year": "2024",
    "external_id": "SBTEST-T06-20260720",
}
```

### T-07 — `lcc_number` conventions

**Settles:** that all three observed conventions are accepted as free text, so
the per-hospital template can be pure config.

**User:** `WOLF` · **Expect:** all three HTTP 200, each round-tripping its
exact string.

| Variant | `lcc_number` | External ID |
|---|---|---|
| T-07a | `WOLF-TAU-9002 Test Patron` | `SBTEST-T07A-20260720` |
| T-07b | `WOLF248; 20260720` | `SBTEST-T07B-20260720` |
| T-07c | `WOLF9003` | `SBTEST-T07C-20260720` |

### T-08 — Duplicate / idempotency — ✅ **SETTLED 2026-07-20 (both halves)**

Two probes ran ahead of the matrix (guidebook §8; GH #14/#35):

- **First half `VERIFIED`:** an identical body re-POSTed for `SHEB` was
  rejected `402362` "Patron has duplicate request" while the original was
  active (request `39940250330004146`, cancelled).
- **Second half `DISPROVEN`:** recovery via
  `get_user_rs_request(user_id, external_id, request_id_type="external")` is
  impossible — Alma discards the POSTed `external_id` (stored `972TAU0068653`
  instead) and the lookup returns "No result found" (request
  `39940249320004146`, cancelled).

**Decision (operator, 2026-07-20):** the `402362` rejection is the
duplicate-safety mechanism; the processor treats it as already-created.
Config dependency: `check_patron_duplicate_borrowing_requests=true`
(false by default; enabled at TAU — **verify in PROD before go-live**).

### T-09 — All eight proxy users

**Settles:** that every hospital proxy user is affiliated with a resource
sharing library. A create for a non-affiliated user fails `401768`, and we
would rather find that now than in production.

One minimal T-01-shaped create for each of `ASAF`, `BEIL`, `IC`, `LE`, `ME`,
`SHEB`, `SHH`, `WOLF`. External IDs `SBTEST-T09-<USER>-20260720`. Title:
`"Proxy user affiliation probe (<USER>)"`.

**Note:** `LE` and `SHH` have very low volume (43 and 8 census records) — they
are the most likely to be misconfigured.

---

## 2. End-to-end tests (after the pipeline is wired)

### T-10 — PMID path, dry-run then live

A borrowing TSV with a real PMID → enrichment → payload → create. **Run
`--dry-run` first** and inspect the built body before any live run.

### T-11 — DOI path, dry-run then live

Same, with a DOI. Note the guidebook §4.4 point: we will populate `doi` far
more often than the manual flow does (4%). Confirm that is accepted.

### T-12 — Lending regression

A **lending** TSV through the unchanged lending path, asserting the built
citation params are byte-identical to `tests/golden/l2_citation_params.json`.
This is the guard that the refactor did not disturb the production path. It
must pass **before** any borrowing test is run live.

---

## 3. Suggested order

1. **T-12** (lending unharmed) — gate everything on this.
2. **T-01** (baseline works at all).
3. **T-02** (settability) — rewrites the builder's field list.
4. **T-04** (copyright) — decides one config default.
5. **T-05, T-06** (negatives) — cheap, improve local validation.
6. **T-03** (books), **T-07** (`lcc_number`), **T-09** (all users).
7. **T-08** (duplicate) — last, since it deliberately creates a conflict.
8. **T-10 / T-11** end-to-end.

## 4. Cleanup log

Fill in as tests are run. **A request created and not cancelled is a defect.**

| Test | `external_id` | `request_id` | User | Cancelled | Date |
|---|---|---|---|---|---|
| GH #14 probe (pre-matrix) | sent `SBTEST-EXT14-20260720`, stored `972TAU0068653` | `39940249320004146` | SHEB | ✅ yes | 2026-07-20 |
| GH #35 probe (pre-matrix) | none sent, stored `972TAU0068654` | `39940250330004146` | SHEB | ✅ yes | 2026-07-20 |

Outstanding from 2026-07-19 (created before this matrix existed, still not
cleaned up): `39940155760004146`, `39940156450004146`, `39940157570004146`.
