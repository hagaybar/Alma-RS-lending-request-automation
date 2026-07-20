# Borrowing Requests — Project Guidebook

> Status: **reference document, pre-implementation.** Written 2026-07-20.
> Every claim below is tagged with how it is known. Do not promote an
> `INFERRED` or `OPEN` line to a design decision without testing it.

## 1. What a borrowing request is, and how it differs from lending

Both are Alma "resource sharing" requests, but they are **different endpoints
on different domain objects**, and almost nothing about the request body is
shared.

| | Lending (this repo today) | Borrowing (this document) |
|---|---|---|
| Meaning | A partner asks **us** to supply an item we hold | We ask a partner to supply an item **we do not hold** |
| Endpoint | `POST /almaws/v1/partners/{partner_code}/lending-requests` | `POST /almaws/v1/users/{user_id}/resource-sharing-requests` |
| Scoped to | a **partner** | a **user** |
| AlmaAPITK | `ResourceSharing.create_lending_request_from_citation(...)` | `Users.create_user_rs_request(user_id, request_data, ...)` |
| Body built by | the toolkit (takes kwargs, enriches, builds) | **us** (the toolkit forwards `request_data` verbatim) |
| `SHEB` means | a **partner code** | a **user (proxy patron) code** |

That last row is the single most dangerous ambiguity in this project. The
string `SHEB` appears in both flows and means something completely different
in each. Anything that carries a code between the two paths must say which
namespace it is in.

## 2. The shared upstream, and where it forks

The two request types are **two terminal branches of one pipeline**, not two
systems:

1. A hospital librarian fills in a Microsoft Form (identifier + fields).
2. A Power Automate flow checks whether TAU holds the article.
3. **Fork:**
   - **Held** → a file lands in the lending input folder → lending request.
   - **Not held** → a file lands in the **borrowing** input folder → borrowing request.
4. A Windows Task Scheduler job on `masedet` picks the file up.
5. Metadata is enriched from PubMed (PMID) or Crossref (DOI).
6. A request is created in Alma; the file is moved to `processed/`.

Steps 1, 2, 4, 5 and the file/logging/reporting machinery of 6 are **identical**.
Only the request-building and the API call differ. That is why this is an
extension of this repo and not a new one.

## 3. The evidence base

Everything in §4 comes from reading real requests out of the Alma **SANDBOX**
on 2026-07-20, not from the schema:

- **Census:** all resource-sharing requests for all 8 hospital proxy users —
  **1912 requests** (`ASAF`, `BEIL`, `IC`, `LE`, `ME`, `SHEB`, `SHH`, `WOLF`).
- **Deep sample:** full request JSON for **100 requests**, allocated in
  proportion to each hospital's share of the census (SHEB 23, BEIL 21, IC 19,
  ASAF 17, WOLF 13, ME 4, LE 2, SHH 1) and drawn at even intervals through
  each hospital's history rather than taking the most recent.

Caveat that applies to the whole document: these are **GET** responses for
requests created through the **UI/broker**, not through the API. A field being
present on every GET does **not** prove it is accepted on POST. §6 is the
experiment that closes that gap.

## 4. The verified field template

### 4.1 Constants — 100/100 in the deep sample

`VERIFIED`. These do not vary by hospital, citation type, format, partner, or
across four years of history.

| Field | Value | Wrapped? |
|---|---|---|
| `owner` | `"AM1"` | plain string |
| `pickup_location` | `{"value": "AM1"}` | wrapped |
| `pickup_location_type` | `"LIBRARY"` | plain string |
| `requested_media` | `"7"` | plain string |
| `allow_other_formats` | `false` | boolean |
| `willing_to_pay` | `false` | boolean |
| `maximum_fee` | `0.0` | number |

`level_of_service` and `copyright_status` are **empty in 100/100** — omit them.

Note `owner` is a **plain string** while `pickup_location` is **wrapped**, even
though both hold `AM1`. This asymmetry is real and is the most common cause of
a `BAD_REQUEST` / "Cannot construct instance of ... UserResourceSharingRequest".

### 4.2 Near-constants

`VERIFIED` as overwhelmingly dominant; the exception is a single record each.

| Field | Dominant | Exception |
|---|---|---|
| `format` | `{"value": "DIGITAL"}` — 99/100 | 1 × `PHYSICAL` |
| `specific_edition` | `true` — 99/100 | 1 × `false` |
| `use_alternative_address` | `false` — 99/100 | 1 × `true` |

Treat `DIGITAL` as the default, configurable — not hardcoded.

### 4.3 Real variables

| Field | Distribution | Notes |
|---|---|---|
| `citation_type` | `CR` 95, `BK` 5 | `VERIFIED`. **Zero `E_CR` / `E_BK` in 1912 requests.** |
| `need_patron_info` | `false` 75, `true` 25 | `VERIFIED` that it varies. What drives it is `OPEN`. |
| `partner` | populated 75/100 | `VERIFIED` not required at create — the rota assigns it. **Omit.** |
| `external_id` | populated 75/100 | Ours to define; see §4.5. |

**`BK` requests are `DIGITAL` too** (5/5) — books are requested as scans, not
loans. Do not couple `BK` to `PHYSICAL`.

#### Why there is no `E_CR`

The Alma code table `ReadingListCitationTypes` contains `BK`, `CR`, `E_BK`,
`E_CR`, and a SANDBOX test on 2026-07-19 confirmed Alma **accepts** `E_CR`.
It never appears in production because **the librarians' UI only offers `CR`
and `BK`.** `VERIFIED` by the operator, and consistent with 1912/1912 records.

> ⚠️ `~/.claude/skills/alma-api-expert/references/resource_sharing_api.md`
> currently records a decision to prefer `E_CR` for born-digital articles.
> That was reasoned from a one-off sanity check and is **contradicted by 1912
> real requests.** It needs correcting; see §7.

### 4.4 Bibliographic fields

Populated rates across the deep sample (n=100). All are **plain strings**.

| 100% | `title`, `citation_type`, `format`, `owner`, `requested_media`, `pickup_location*`, `mms_id`¹ |
|---|---|
| 90–99% | `author` 99, `year` 99, `journal_title` 95, `volume` 93, `issn` 92 |
| 60–80% | `issue` 75, `pmid` 75, `pages` 66, `start_page` 62, `end_page` 61 |
| 20–45% | `publisher` 37, `place_of_publication` 36, `bib_note` 31, `note` 27, `other_standard_id` 24 |
| < 5% | `doi` 4, `chapter_title` 4, `source` 4, `chapter_author` 3, `isbn` 3, `edition` 2 |

¹ `mms_id` is present on every stored request but is **flow-generated** — Alma
builds a placeholder bib from the request's own metadata. `INFERRED`: we should
**not** send `mms_id` at create. `OPEN` until §6 confirms.

`doi` at 4% is notable: our input is DOI-or-PMID, so we will populate `doi`
far more often than the manual flow does. That is a deliberate improvement,
not a deviation to correct.

### 4.5 The three carrier fields

These hold operational data under misleading names. `VERIFIED` shapes:

**`lcc_number`** — 98/100 populated. Carries the **requesting patron's
identity**. The leading token matches the proxy user in 95/98, but note
`SHEBA` (22) vs the user code `SHEB` (1) — it is a label, not the code. Three
competing conventions coexist:

| Shape | n | Reads like |
|---|---:|---|
| `W-W-# W W` | ~55 | `SHEBA-TAU-1680 <patron name>` |
| `W#; #` | 21 | `BEIL248; 20233913` |
| `W#` | 14 | `IC2055` |

`OPEN` — **what we write here is undecided pending the librarians.** Design it
as a per-hospital configurable template so the answer lands in config, not code.

**`oclc_number`** — 43/100 populated. Not an OCLC number: it is the
**supplier's reference**, formatted however that supplier does it — bare digits
(24), `REG-#` (8), `ID: #` (5), `SUBITO:#` (2), `ID: # NLMPILOT` (2). The
`SUBITO:` prefix tracks the SUBITO partner. `INFERRED`: this is written by the
*supplier* after the fact, not by the requester. **Omit at create.**

**`external_id`** — 75/100 populated, in two grammars: `<8 digits>` (53) and
`972TAU<digits>` (22). These come from two different upstream broker systems.
`VERIFIED` 2026-07-20 (probe, §8): **a client-supplied value is discarded on
POST** — Alma substitutes its own `972TAU…` broker id in the create response,
and `request_id_type="external"` cannot find our value. **Omit at create.**
The pipeline still mints a local `FORMS-BR-…` id, but it exists only in logs
and CSV reports for file correlation — Alma never sees or stores it.

### 4.6 The copyright fields

There are **two**, and they are unrelated:

- **`agree_to_copyright_terms`** — the librarian's signature on the UI
  copyright statement. `VERIFIED`: **98 × `false`, 2 × `true`** in the deep
  sample. `OPEN`: yesterday's SANDBOX recipe sent `true`, and the skill file
  records it as "mandatory TRUE for borrowing". Real data contradicts that.
  Whether Alma *requires* `true` at create but does not persist it is exactly
  what test `T-04` in the test matrix settles.
- **`copyright_status`** — an internal Alma copyright mechanism that **is not
  used here** (`VERIFIED` by the operator; empty in 100/100). **Omit.**

## 5. Operational gotchas

| Gotcha | Evidence |
|---|---|
| `40166422` on ~6% of reads — a `resource_sharing.id` nested in a hold request is not always retrievable under that proxy user | `VERIFIED`: 6 failures in 106 fetches |
| The RS request id is **not** the hold request id. In `GET /bibs/{mms_id}/requests` the top-level `request_id` is the HOLD; the RS id is at `resource_sharing.id` | `VERIFIED` |
| There is **no GET-collection** endpoint for user RS requests — `/users/{id}/resource-sharing-requests` is POST-only. To enumerate, read `/users/{id}/requests` and take the nested `resource_sharing` block | `VERIFIED` against the users swagger |
| A create can **time out and still save**. The retry then fails `402362` — which is the *safety mechanism*, not a bug (see §8) | `VERIFIED` 2026-07-19, re-verified 2026-07-20 |
| `external_id` sent on POST is **discarded** — Alma substitutes a `972TAU…` broker id; external lookup for our value returns "No result found" | `VERIFIED` 2026-07-20 (§8) |
| The `402362` duplicate check is **config-dependent**: customer parameter `check_patron_duplicate_borrowing_requests`, **false by default**, enabled at TAU. Active requests only; compares user + citation fields (Title, ISBN, Volume…) | `VERIFIED` live + Ex Libris FAQ, 2026-07-20 (§8) |
| `override_blocks=true` pushed a create past a 60s timeout; without it the same body returned in ~3s | `VERIFIED` 2026-07-19. Treat override as a workaround, not the recipe |
| `401604` "institutional inventory has services for the requested title" blocks a create with HTTP 400 despite the "Warning" wording | `VERIFIED` 2026-07-19. Should be rare here — Power Automate has already established we do *not* hold the item |

### Error codes

| Code | Meaning |
|---|---|
| `401607` | `owner` missing/empty |
| `401768` | Patron not affiliated with a resource sharing library |
| `401929` | `pickup_location` not a valid borrowing pickup for `owner` |
| `401930` | Missing mandatory article fields (Journal Title, Publication Date, Author) |
| `401604` | Institution already has services for the title — blocks create |
| `402362` | Patron has duplicate request |
| `40166422` | `request_id` invalid for this `user_id` |
| `Invalid field value … {1}` | A code-table value from the wrong table (Alma cannot say which field) |
| `BAD_REQUEST` + "Cannot construct instance of … UserResourceSharingRequest" | Body shape mismatch — wrong field name, or plain-vs-wrapped wrong |

## 6. What is still unverified

Nothing below can be resolved by reading. Each needs a SANDBOX create; see
`docs/BORROWING_SB_TEST_MATRIX.md`.

1. **Which fields are settable at create.** Every field in §4 is confirmed on
   GET only. `requested_media`, `specific_edition`, `lcc_number`, `maximum_fee`
   and `need_patron_info` are the ones most likely to be silently dropped.
2. **`agree_to_copyright_terms`** — required `true`, or should we send `false`
   to match the manual population?
3. **Whether omitting `partner` and `mms_id`** produces a request that looks
   like the manual ones once the rota has run.
4. ~~**Whether the almaapitk floor pinned in `pyproject.toml` exposes
   `create_user_rs_request` at all.**~~ `SETTLED` 2026-07-20: the installed
   0.4.6 exposes all three RS methods with matching signatures; Task 0's
   contract test passes against it.

## 7. Follow-up outside this repo

- Correct the `E_CR` recommendation in
  `~/.claude/skills/alma-api-expert/references/resource_sharing_api.md` — it is
  contradicted by 1912 real requests (§4.3).
- Correct "`agree_to_copyright_terms` … mandatory TRUE for borrowing" in the
  same file to reflect the 98/100 `false` observation, pending `T-04`.

## 8. Probe log — 2026-07-20 (all `VERIFIED` live in SANDBOX)

Two targeted probes, run before implementation began, to settle GH issues
#14/#35. Both requests were cancelled immediately (see the matrix §4 cleanup
log).

### 8.1 `external_id` is not ours to set

T-01-shaped create for `SHEB` with `"external_id": "SBTEST-EXT14-20260720"`
(request `39940249320004146`):

- The **create response itself** carried `external_id = '972TAU0068653'` —
  Alma assigns a broker id at create time and silently discards the client's
  value. This explains the census's `972TAU…` grammar (§4.5).
- `get_user_rs_request(user, our_id, request_id_type="external")` →
  `AlmaAPIError: No result found for given parameters.` A never-sent id fails
  with the **identical** message, so dropped and never-created are
  indistinguishable through this endpoint.
- Consequence: **reconcile-by-external_id is impossible.** Any idempotency
  design leaning on it is void.

### 8.2 Alma's duplicate rejection is real — and is the safety mechanism

The same T-01-shaped body POSTed twice for `SHEB` (request
`39940250330004146`):

- Attempt 1: accepted in ~3s.
- Attempt 2: `AlmaAPIError: Failed to save the request: Patron has duplicate
  request` (alma_code `402362`).

Ex Libris documentation (Borrowing Requests FAQ) adds the scope: the check
compares, for the same user, citation fields "such as Title, ISBN, and
Volume"; it considers **active requests only** (completed/cancelled requests
do not block a re-request); and it is controlled by the customer parameter
`check_patron_duplicate_borrowing_requests` — **false by default**, enabled
at TAU.

### 8.3 The decision (2026-07-20)

**Alma's `402362` rejection is the duplicate-safety mechanism for this
pipeline.** A create that times out after saving is recovered on the next
scheduled run: the re-POST is rejected `402362`, the processor records the
file as `duplicate` (success-like) and moves it to `processed/`.

- **Go-live precondition:** RS librarians confirm
  `check_patron_duplicate_borrowing_requests=true` in **PRODUCTION** config.
  The sandbox proves the sandbox, not prod.
- **Accepted residual risk** (operator decision): a retry whose rebuilt body
  differs — e.g. PubMed/Crossref metadata drift between runs — could escape
  the check. Judged low-probability.
- The local `FORMS-BR-…` id remains for logs/reports only (§4.5).
- Note for any future list-based reconcile: there is **no GET-collection**
  endpoint for user RS requests (§5); enumeration goes through
  `/users/{id}/requests` and its nested `resource_sharing` block.
