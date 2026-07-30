# Borrowing Requests — SANDBOX Test Matrix

> Originally all-proposed; **execution began 2026-07-30** — tests carry dated
> ✅/❌ verdict notes inline as they run (see also §4 cleanup log).
> Every payload targets the Alma **SANDBOX** only.
>
> **Updated 2026-07-22:** T-03 dropped (articles-only scope), T-05
> effectively settled and T-06 downgraded by the upstream AlmaAPITK session
> (guidebook §9); T-09 extended with the TOU-limits question (GH #32).

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

> 2026-07-22: this shape (DIGITAL+CR with journal_title/author/year) was
> already accepted live upstream with a `build_user_rs_request`-produced
> body (guidebook §9). T-01 stays as the cheap first check that **our**
> config and payload reproduce it.

**User:** `SHEB` · **Expect:** HTTP 200 + `request_id`, in ~3s.

> ✅ **PASSED 2026-07-30** — `request_id 39940482970004146`, `REQUEST_CREATED_BOR`,
> ~11s, via the harness (builder-produced body). Two deviations from the spec
> below: (1) the first attempt sent `agree_to_copyright_terms: false` and was
> **rejected at create** (`401897 Invalid field value`) — see T-04; the pass
> used `true`, which also **stored** as `true`. (2) the builder body sends no
> `external_id`; Alma stored it *empty* (unlike the GH #35 probe, which got an
> auto-generated one). Settability diff was clean — all sent fields stored
> verbatim (wrapped fields gain only a `desc` label).

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

> ✅ **PASSED 2026-07-30** — `request_id 39940483500004146`, ~3s, via the
> harness (builder body + `extra`; `agree_to_copyright_terms: true` added per
> the T-01/T-04 verdict). **The authority table** (immediate GET after create;
> fake pmid/doi kept augmentation silent by design — real-id behaviour is
> T-02b's):
>
> | Field | Sent | Stored | Verdict |
> |---|---|---|---|
> | `title`, `journal_title`, `author`, `year` | as spec | = sent | settable |
> | `volume`, `issue`, `pages`, `start_page`, `end_page` | as spec | = sent | settable |
> | `issn`, `pmid`, `doi` | fake values | = sent | settable |
> | `publisher`, `place_of_publication` | as spec | = sent | settable |
> | `note`, `bib_note` | as spec | = sent | settable |
> | `requested_media` | `"7"` | = sent | **settable** (was suspect) |
> | `specific_edition` | `True` | = sent | **settable** (was suspect) |
> | `need_patron_info` | `False` | = sent | **settable** (was suspect) |
> | `maximum_fee` | `0.0` | = sent | **settable** (was suspect) |
> | `lcc_number` | `"SHEBA-TAU-9001 Test Patron"` | = sent | **settable** (was suspect) |
> | `owner`, `pickup_location_type` | plain strings | = sent | settable |
> | `allow_other_formats`, `willing_to_pay`, `agree_to_copyright_terms` | booleans | = sent | settable |
> | `format`, `citation_type`, `pickup_location` | wrapped `{value}` | value = sent, gains `desc` | transformed (cosmetic) |
> | `external_id` | `"SBTEST-T02-20260720"` | `""` | **dropped** (re-confirms §8.1) |
>
> **Bottom line for the builder: every field in the production template is
> settable; nothing is silently dropped except `external_id`, which stays a
> local log-correlation marker only.** §7.1 open question 1 is settled.

### T-03 — Book chapter (`BK` + `DIGITAL`) — ❌ **DROPPED 2026-07-22 (out of scope)**

Articles-only decision (guidebook §4.3): the pipeline creates `CR`+`DIGITAL`
requests exclusively, and the builder rejects `BK` before any API call.
**Do not run.** Background: `PHYSICAL`+`BOOK` reproducibly 500s in SANDBOX
(AlmaAPITK #207, culprit undetermined) and no book recipe is proven live.
The payload below is kept only as the starting point if book support ever
returns to scope.

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
mandatory. (2026-07-22, GH #31: the upstream builder now defaults `True` —
a third voice. The contradiction stands; this test still decides.)

Run three creates, identical but for this one field:

| Variant | `agree_to_copyright_terms` | External ID |
|---|---|---|
| T-04a | *omitted entirely* | `SBTEST-T04A-20260720` |
| T-04b | `False` | `SBTEST-T04B-20260720` |
| T-04c | `True` | `SBTEST-T04C-20260720` |

> **2026-07-30 — b and c verdicts landed early, via T-01** (user `SHEB`, T-01
> body, not the `IC` variants above): `false` is **rejected at create**
> (`401897 Invalid field value. Field: agree_to_copyright_terms, Value:
> false.`) and `true` succeeds **and stores as `true`** on immediate GET.
> Per the decision rule this is the "b fails and c succeeds" branch → the
> field is mandatory at create; **send `true`** (`borrowing.
> agree_to_copyright_terms: true` in config) and note in the guidebook §4.6
> that API-created requests will differ from the 98/100-`false` manual
> population. Still open if wanted: T-04a (field omitted), and whether the
> stored `true` survives the rota/UI lifecycle (the manual `false`s may be
> a UI-population artifact rather than a persistence rewrite).

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

### T-05 — Missing article fields (negative) — ✅ **effectively SETTLED 2026-07-22**

**Settles:** that the `401930` rule still holds, so our validation can fail
fast locally instead of paying a round trip.

> The upstream session confirmed it live: `journal_title` + `year` (with
> `author`) are mandatory for a `DIGITAL` article — Alma error `401930`
> (guidebook §9). Local validation already enforces the trio. Optional
> re-run with our exact body; not a gate.

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

### T-06 — Wrong wrapper on `owner` (negative) — ⬇ **downgraded 2026-07-22 (optional)**

**Settles:** confirms the plain-vs-wrapped asymmetry, and gives us the exact
error string to match on for a helpful local message.

> With the body built by `almaapitk.build_user_rs_request` (>= 0.5.0) the
> wrapper mistake can no longer be produced by our code, and the upstream
> session verified the error surface live (wrong-table code → 400 with an
> `[almaapitk hint: …]` naming the field — guidebook §9). Optional; not a
> gate.

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

**Extension (GH #32, 2026-07-22):** creation succeeding once per user does
not probe **velocity limits** — Alma's per-patron "Active Resource Sharing
Requests Limit" / "Yearly Requests Limit" TOU checks. Each hospital funnels
its entire volume through one proxy account, and `submit()` never passes
`override_blocks`, so a hospital at its limit fails every create until
requests complete. While running T-09, ask the RS librarians for the 8
accounts' TOU limits and have them raised if needed **before go-live**.

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

*(revised 2026-07-22 — T-03 dropped, T-08 settled, T-05/T-06 optional)*

1. **T-12** (lending unharmed) — gate everything on this.
2. **T-01** (baseline works at all).
3. **T-02** + **T-02b** (settability) — rewrites the builder's field list.
4. **T-04** (copyright) — decides one config default (GH #31).
5. **T-07** (`lcc_number`), **T-09** incl. the TOU-limits question (GH #32).
6. *(optional)* **T-05, T-06** — effectively settled/downgraded, see each.
7. **T-10 / T-11** end-to-end.

## 4. Cleanup log

Fill in as tests are run. **A request created and not cancelled is a defect.**

| Test | `external_id` | `request_id` | User | Cancelled | Date |
|---|---|---|---|---|---|
| GH #14 probe (pre-matrix) | sent `SBTEST-EXT14-20260720`, stored `972TAU0068653` | `39940249320004146` | SHEB | ✅ yes | 2026-07-20 |
| GH #35 probe (pre-matrix) | none sent, stored `972TAU0068654` | `39940250330004146` | SHEB | ✅ yes | 2026-07-20 |
| T-01 attempt 1 (`agree_to_copyright_terms: false`) | — | — (create rejected, 401897; nothing to clean) | SHEB | n/a | 2026-07-30 |
| T-01 (passed, flag `true`) | none sent, stored *empty* | `39940482970004146` | SHEB | ❌ kept for UI inspection (user request) | 2026-07-30 |
| T-02 (passed) | sent `SBTEST-T02-20260720`, stored *empty* | `39940483500004146` | SHEB | ❌ kept for UI inspection (user request) | 2026-07-30 |

Outstanding from 2026-07-19 (created before this matrix existed, still not
cleaned up): `39940155760004146`, `39940156450004146`, `39940157570004146`.

**Upstream leftovers — not ours, do not "clean up" (2026-07-22):** the
AlmaAPITK session deliberately left four requests in SANDBOX for inspection
(owner/pickup `AM1`, operator override): `39940272600004146` (E_CR A/B),
`39940273040004146` (CR A/B), `39940273500004146` (chunk test),
`39940276180004146` (hospital-format demo). Cancel only after the AlmaAPITK
side is done with them.

### T-02b — Real-identifier augmentation diff (GH #33)

**Settles:** what Alma's Augmentation Integration Profile overwrites when the
identifiers are *real*. T-02 deliberately uses fake ids so augmentation stays
silent — but production always sends real PMIDs/DOIs, so T-02's sent→stored
verdicts are measured under different conditions than production runs in
(AlmaAPITK borrowing guide: augmentation resolves a valid `pmid`/`doi` and
overwrites "any corresponding manually provided metadata strings").

**User:** `SHEB` · One T-02-shaped body but with a **real** PMID and its true
metadata deliberately perturbed (e.g. wrong `year`, truncated `title`), then
`GET` the created request and diff field-by-field:

- Which sent values survived, which were overwritten by augmentation?
- Record the overwritten set next to T-02's settability table — together they
  are the full sent→stored contract for production.

**Cleanup:** cancel, record in §4.
