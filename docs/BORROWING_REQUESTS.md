# Borrowing Requests — Project Guidebook

> Status: **reference document, pre-implementation.** Written 2026-07-20;
> updated 2026-07-22 with live upstream evidence (§9) and the articles-only
> scope decision (§4.3). Every claim below is tagged with how it is known.
> Do not promote an `INFERRED` or `OPEN` line to a design decision without
> testing it.

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

#### 2026-07-22: `E_CR` also loses metadata at persist

An upstream A/B probe (AlmaAPITK session, two bodies identical but for the
citation type — §9) settled it beyond convention: `E_CR` is accepted at
create and *validates* the journal fields, but **discards `journal_title`,
`issue`, `doi`, `pmid` at persist** (empty on JSON GET, XML GET and in the
placeholder bib; `volume` misfiled into the bib's `490$v`). `CR` persists
everything and triggers Alma's citation enrichment (ISSN added unprompted,
full `773` host item, DOI/PMID in `856`). `CR` is not just the census
convention — it is the only citation type that keeps our metadata.
`VERIFIED` live 2026-07-22.

#### Scope decision 2026-07-22 — articles only

This pipeline creates **`CR` + `DIGITAL`** requests exclusively (operator
decision). `BK` is out of scope: the upstream session found `PHYSICAL`+`BOOK`
reproducibly returns a raw HTTP 500 in SANDBOX (AlmaAPITK #207 — whether the
culprit is `PHYSICAL`, `BOOK`, or the pair is undetermined), and no book
recipe has been proven live. Revisit only with a proven SANDBOX recipe.

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
  copyright statement. **`SETTLED` 2026-07-30 (SB, T-04 via T-01, GH #31):
  Alma rejects `false` at create** (`401897 Invalid field value`), and `true`
  succeeds **and stores as `true`** on immediate GET. So the API contract is:
  send `true`, always. The **98 × `false`, 2 × `true`** in the deep sample of
  manual requests is how the *UI* populates the field, not Alma rewriting an
  API-sent `true` — API-created requests will simply differ from the manual
  population here, which is acceptable. Config ships
  `borrowing.agree_to_copyright_terms: true`; the code fallback for a missing
  key is also `true` (a payload with `false` is known to fail). The skill
  file's "mandatory TRUE for borrowing" turned out to be correct.
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
| `401604` "institutional inventory has services for the requested title" blocks a create with HTTP 400 despite the "Warning" wording | `VERIFIED` 2026-07-19. ~~Should be rare here — Power Automate has already established we do *not* hold the item.~~ **Wrong — see §10.** Alma's check is *title-level* self-ownership; Power Automate's is *article-level*. They disagree on every article we hold the journal for but not the year, so this is a routine outcome, not a rare one. Re-hit in production 2026-09-03 |
| The identifier column is **free text** — requesters type the label in with the value (`PMID: 15320862`). Stripped at the borrowing parse site by `normalize_identifier()`; see [IDENTIFIER_DETECTION.md](IDENTIFIER_DETECTION.md) | `VERIFIED` in production on the lending path, issue #7 |

### Error codes

| Code | Meaning |
|---|---|
| `401607` | `owner` missing/empty |
| `401768` | Patron not affiliated with a resource sharing library |
| `401929` | `pickup_location` not a valid borrowing pickup for `owner` |
| `401930` | Missing mandatory article fields (Journal Title, Publication Date, Author) |
| `401604` | Institution already has services for **the title** — blocks create. Alma's *Self Ownership* check, matched on bib fields only (Title, ISBN/ISSN, LCCN, System Control Number); coverage dates are **not** consulted, so it fires on articles we cannot actually supply — §10 |
| `402362` | Patron has duplicate request |
| `40166422` | `request_id` invalid for this `user_id` |
| `Invalid field value … {1}` | A code-table value from the wrong table (Alma cannot say which field) |
| `BAD_REQUEST` + "Cannot construct instance of … UserResourceSharingRequest" | Body shape mismatch — wrong field name, or plain-vs-wrapped wrong |

## 6. What is still unverified

Nothing below can be resolved by reading. Each needs a SANDBOX create; see
`docs/BORROWING_SB_TEST_MATRIX.md` (and §9 for what the 2026-07-22 upstream
session already settled).

1. ~~**Which fields are settable at create.**~~ **`SETTLED` 2026-07-30 (T-02 +
   T-02b, matrix):** *every* template field is settable — including all five
   suspects (`requested_media`, `specific_edition`, `lcc_number`,
   `maximum_fee`, `need_patron_info`); the only dropped field is
   `external_id` (§4.5, already known). With a **real** identifier, Alma's
   augmentation synchronously overwrites the bib core (`title`, `author`,
   `year`, `volume`, `issue`, `start_page`, `end_page`, `issn`) from the
   resolved record; `journal_title`, `pages`, `publisher`,
   `place_of_publication`, `note`, `bib_note` and all operational fields stay
   as sent.
2. ~~**`agree_to_copyright_terms`**~~ **`SETTLED` 2026-07-30:** required
   `true` at create — `false` is rejected with `401897` (§4.6).
3. **Whether omitting `partner` and `mms_id`** produces a request that looks
   like the manual ones once the rota has run.
4. ~~**Whether the almaapitk floor pinned in `pyproject.toml` exposes
   `create_user_rs_request` at all.**~~ `SETTLED` 2026-07-20: the installed
   0.4.6 exposes all three RS methods. **Superseded 2026-07-22:** the plan
   now builds the body with `almaapitk.build_user_rs_request`, absent
   through 0.4.6 — plan Task 0 raises the floor to the release that ships
   it (expected 0.5.0) and is blocked until that release is on PyPI (§9).

## 7. Follow-up outside this repo

- ~~Correct the `E_CR` recommendation in
  `~/.claude/skills/alma-api-expert/references/resource_sharing_api.md`.~~
  **Done upstream 2026-07-22** — the skill file now records "use `CR`, not
  `E_CR`" with the A/B persistence evidence (§9), in section "Borrowing
  create — observed behavior (SB 2026-07-22)".
- ~~Correct "`agree_to_copyright_terms` … mandatory TRUE for borrowing" in the
  same file to reflect the 98/100 `false` observation, pending `T-04`.~~
  **Resolved 2026-07-30 — no correction needed:** T-04 confirmed the skill
  file was right (`false` is rejected at create, `401897`). The skill file
  instead gained the dated evidence note plus the T-02/T-02b settability and
  augmentation verdicts.

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

## 9. Upstream evidence — 2026-07-22 (AlmaAPITK `rs-borrowing-ergonomics`)

The AlmaAPITK session of 2026-07-22 (PR #206 merged to its `main`, closing
its issues #197/#194; 5/5 SANDBOX tests green) ran live creates this project
inherits as evidence. All `VERIFIED` live unless noted.

- **`build_user_rs_request` exists upstream.** Pure, network-free body
  builder exported at the package root; encodes the §4.1 plain-vs-wrapped
  asymmetry once. A body produced entirely by it was accepted on a live
  create round-trip (build → create → GET). **Unreleased at the time of
  writing** — PyPI's latest is 0.4.6; this project's plan gates on the
  0.5.0 release (plan Task 0).
- **`create_user_rs_request(..., validate=True)`** — new opt-in pre-flight
  check of `format` / `citation_type` / `pickup_location_type` against
  documented borrowing codes; raises `AlmaValidationError` naming the field
  before any HTTP. Off by default (tables are tenant-extensible).
- **`DIGITAL`+`CR` proven; `PHYSICAL`+`BOOK` 500s.** The originally
  prescribed PHYSICAL+BOOK body hit a reproducible **raw HTTP 500** (no
  alma_code) across every owner/pickup combination, minimal body, with and
  without `external_id`. Whether the culprit is PHYSICAL, BOOK, or the pair
  is undetermined — AlmaAPITK #207 tracks the decomposition.
- **`E_CR` discards metadata at persist** (A/B probe, §4.3): journal_title,
  issue, doi, pmid empty after create; volume misfiled into the bib's
  `490$v`. `CR` persists everything and triggers citation enrichment.
  Requests `39940272600004146` (E_CR) / `39940273040004146` (CR).
- **`401930` confirmed live:** `journal_title` + `year` (with `author`)
  mandatory for a `DIGITAL` article.
- **`external_id` non-persistence re-confirmed** on the hospital-format demo
  (sent `"99990001"`, came back empty on GET) — independent confirmation of
  §8.1. Note the upstream builder's docstring still pitches `external_id` as
  an idempotency key; for this surface that is wrong.
- **Pickup validity is per-owner** (`401929` when the pickup library is not
  configured for that owner); pickup may equal owner — `AM1`/`AM1` works.
- **Error surfacing (ships with the same release):** Alma's unrenderable
  `Invalid field value … {1}` 400 gains an `[almaapitk hint: …]` suffix
  naming the likely field; `401890` maps to `AlmaResourceNotFoundError`
  despite arriving as HTTP 400; the `40166411` code collision is resolved
  endpoint-scoped. This repo's `402362` duplicate match keys on alma_code /
  message substring and is unaffected.
- **Four requests were left in SANDBOX deliberately** (owner/pickup `AM1`,
  upstream operator override — left for inspection): `39940272600004146`,
  `39940273040004146`, `39940273500004146` (chunk test),
  `39940276180004146` (hospital-format demo). They are **not** this
  project's leftovers; see the matrix cleanup log before touching them.

## 10. `401604` is a title-level self-ownership check — 2026-09-03

Production borrowing file `9_2_2026 11_46_25 AM.tsv`, PMID `36374288`, was
rejected with:

```
Unexpected error: Warning - The institutional inventory has services for the
requested title.
```

The request is an *article*; the thing Alma found is the *journal*. This
section records why those are not the same question, and why the 2026-07-22
assumption that `401604` would be rare here is wrong.

### 10.1 What Alma is checking

Ex Libris calls this the **Self Ownership** check, and documents it as a
bibliographic match:

> "The Self Ownership check determines whether a requested resource is
> locally owned at the requester's institution."

> "The record is located based on the selected Locate by Fields values on the
> Organization Unit Details page"

— defaulting, when nothing is configured, to **LCCN, System Control Number,
Title, and ISBN/ISSN**
([Locating Items for Resource Sharing](https://knowledge.exlibrisgroup.com/Alma/Product_Documentation/010Alma_Online_Help_(English)/030Fulfillment/050Resource_Sharing/Resource_Sharing_Configuration/Locating_Items_for_Resource_Sharing)).

Every one of those four is a field of the **bib record**. None is
article-level, and none carries the citation's year, volume or issue — so
the check cannot distinguish "we hold this journal" from "we can supply this
article". In the UI the same check is a warning the operator clears by hand:

> "If local resources exist but you are creating a resource-sharing request
> in any case, a self-ownership warning message appears when you save the
> request." … "if you are sure you want to create the borrowing request,
> select Confirm."

([Creating a Borrowing Request](https://knowledge.exlibrisgroup.com/Alma/Product_Documentation/010Alma_Online_Help_(English)/030Fulfillment/050Resource_Sharing/010Resource_Sharing_Workflow/Borrowing_Requests/010Creating_a_Borrowing_Request))

Over the API there is no Confirm: the create fails, HTTP 400, `401604`,
"Warning" wording and all.

**The vendor documentation is silent on electronic coverage.** It says what
the check matches on; it does not say whether coverage dates are consulted.
§10.2 settles that by demonstration.

### 10.2 `VERIFIED` 2026-09-03 — coverage is not consulted

Read-only SANDBOX reads (`GET /bibs/{mms_id}`, `GET /bibs/{mms_id}/portfolios`),
confirmed independently by the operator in the production Alma UI:

| | |
|---|---|
| Citation (PubMed `36374288`) | *American journal of medical quality*, **2023**, vol **38**, issue 1, pp 23–28, DOI `10.1097/JMQ.0000000000000095`, e-ISSN `1555-824X` |
| Bib matched | `9932873215504146` — "American journal of medical quality.", ISSN `1062-8606` |
| Inventory | exactly **one** portfolio, `53328251740004146`, availability **Available** |
| In collection | `61328259000004146` — "Sage Journals All Titles" (selective package, active) |
| Coverage — global | 1993-03-01 v8(1) → **2020-12-31 v35(6)** |
| Coverage — local | 1986 v1(1) → **2020 v35(6)** |
| Perpetual coverage | none |

The requested article is **three years and three volumes past the end of
every coverage statement on the only portfolio there is**, and Alma still
answered *"the institutional inventory has services for the requested
title"*. The check matched the title and never looked at coverage.
`VERIFIED` by demonstration, not by vendor documentation.

The journal changed publisher — the `10.1097` DOI prefix is Lippincott,
while the portfolio we hold is Sage — which is why the coverage stops where
it does.

### 10.3 Power Automate and Alma are both right

The upstream fork asks **LibKey** whether *this article* is available. That
is an article-level, coverage-aware question, and its answer here — not
held — is correct: we cannot supply a 2023 article from a portfolio that
ends in 2020. So the file was routed to `input_borrowing/` correctly.

Alma then asks a different question — *does the institution have any service
for this title?* — and its answer, yes, is also correct.

Neither system is wrong, and neither is misconfigured. They disagree because
they are answering different questions.

### 10.4 Consequence: `401604` is **not** rare here

§5 recorded, on 2026-07-19, that `401604` "should be rare here — Power
Automate has already established we do *not* hold the item". That reasoning
does not hold. The two checks disagree systematically on precisely the
population this pipeline exists to serve: **articles from journals we hold,
in years we do not**. Expect it from

- packages with an end date (cancelled, moved, or transferred titles),
- journals that changed publisher, and
- any request for a year outside a live subscription's coverage.

### 10.5 What the pipeline does with it today

`AlmaAPIError` is not in the processor's `except` ladder, so `401604` falls
through to the generic `except Exception` → status `error`, message
`Unexpected error: Warning - …`. `error` is not in the move list
(`success`, `dry_run_success`, `duplicate`), so the file **stays in
`input_borrowing/` and the scheduled task re-POSTs it every minute,
indefinitely**. `skipped` would not move it either — no status except the
three above moves a file.

**OPEN (2026-09-03):** whether a `401604` should become a permanent, parked
outcome rather than an infinite retry, and whether the operator wants these
surfaced for manual handling. Awaiting the RS librarians / operator.

### 10.6 `override_blocks` **does** clear `401604` — `VERIFIED` 2026-09-03

The plan document assumed `override_blocks=true` is the API equivalent of the
UI's **Confirm** button, but `override_blocks` is documented as a *patron
block* override (`create_user_rs_request` docstring, almaapitk), so this was
carried as `UNVERIFIED`. It has now been probed in SANDBOX with the exact
production payload for PMID `36374288` (matrix §4, three rows):

| Attempt | Result |
|---|---|
| **A** — no override | `AlmaAPIError`, `alma_code` `401604`, immediate |
| **B** — `override_blocks=True` | **Created.** `request_id` `43256809970004146`, ~20s |
| **B′** — re-created under `WOLF`, kept live | `43256811230004146`, status **`LOCATE_IN_PROCESS`**, partner **`TLL` (RapidILL)** assigned by the rota |

So one flag turns a hard `401604` into a normal, fully-routed borrowing
request. Two incidental confirmations from the B′ response:

- `external_id` came back `972TAU0075699` — Alma's own broker id, not ours.
  Independent re-confirmation of §8.1.
- The stored `issn` is **`1062-8606`** — the *print* ISSN of bib
  `9932873215504146`, not the `1555-824X` we sent. Alma's augmentation
  resolved our citation to the very bib whose single portfolio stops in 2020
  (§10.2), which is the self-ownership match, visible in the saved record.

**A cancelled request may still count as a duplicate.** B was cancelled
(HTTP 204, `remove_request` not set, so it survives as *Cancelled*); an
identical re-POST under the same patron seconds later was refused `402362`.
Observed once — whether that is replication lag or a genuine rule is
undetermined, and it qualifies §8.2's "active requests only". B′ therefore
had to run under a different proxy user.

**Policy — under review, not yet changed.** DECISION 2026-07-22 ("never pass
`override_blocks`") was reasoned from the assumption §10.4 has now falsified.
The operator has proposed the opposite default: **create in all cases and let
the librarians decide**, reviewing in Alma rather than gatekeeping in code.
Two refinements were agreed as conditions:

1. Override only on **retry after a `401604`** — never on the first attempt —
   so ordinary requests do not carry it and genuine patron blocks (fines,
   expired accounts, loan limits) stay enforced.
2. **Stamp the request** (the `note` field persists, §4.4) so an
   override-created request is identifiable in the Alma task list; otherwise
   it is indistinguishable from any other and the librarian must re-check
   everything.

`OPEN`: the librarians' sign-off. Until then the code is unchanged and
`401604` still fails as an error row (§10.5).

### 10.7 What Alma does with an override-created request — no human gate observed

This is the part that decides whether "create everything and let the
librarians decide" is even possible, so it is recorded as an observed
timeline rather than a summary. SANDBOX request `43256811230004146`
(§10.6 B′), created by API with `override_blocks=True`, **untouched by any
human afterwards**:

| Time (UTC) | Status | Partner |
|---|---|---|
| 11:06:01 — create response | `LOCATE_IN_PROCESS` "Locate in process" | `TLL` — **RapidILL** |
| 11:17:11 — +11 min, no human action | `READY_TO_SEND` "Ready to be sent" | `TUSM-ISO` — **TUSM** |

Two things follow.

**The rota runs itself.** Alma assigned RapidILL on create, then within
eleven minutes moved the request on to a different, ISO partner. Nobody
approved either step. A request created this way is already inside the
supply workflow before any librarian could look at it.

**The partner Alma picks is not the one it starts with.** The create response
said RapidILL; eleven minutes later it said TUSM. Reading the partner out of
the create response and reporting it would be reporting something already
stale — this pipeline should not do that.

`OPEN`: whether `READY_TO_SEND` transmits on its own or waits for staff is
**not yet established**. It is the last link in the chain, and it decides
whether a librarian review step exists at all. Watching the same request is
the cheapest way to settle it.

### 10.8 The question for the RS team

§10.6 recorded the operator's proposal — create in all cases, let the
librarians decide — and §10.7 is why it cannot simply be adopted: by the
time a librarian sees the request, Alma has already located a partner and
moved it toward sending. **"Let the librarians decide" needs a place in the
workflow where deciding is still possible, and we have not found one.**

What the team needs to choose between:

1. **Manual creation.** `401604` files are parked and reported; a librarian
   creates the request in Alma, sees the self-ownership warning, and clicks
   **Confirm** — or doesn't. Full review, no new failure modes, costs
   librarian time on every occurrence, and §10.4 says occurrences will be
   routine.
2. **Auto-override, no review.** We create with `override_blocks=True` on
   retry after a `401604`. Requests go out without a librarian seeing them.
   The safety net is upstream: LibKey already established we cannot supply
   the article. Cheapest, and irreversible per request once sent.
3. **Auto-override plus an Alma-side hold.** Same as 2, but configured so
   these requests stop somewhere a librarian works through them. Whether
   Alma can be configured to do that — a workflow-profile step, a partner
   that does not auto-send, or a customer parameter — is a question for
   Ex Libris, not something this repo can answer.

Questions to put to Ex Libris regardless of the choice: does
`READY_TO_SEND` send without staff action, and can the self-ownership check
be made coverage-aware (or the API given the UI's **Confirm** semantics)
rather than all-or-nothing?

`OPEN` (2026-09-03): awaiting the RS team. Until they answer, the code is
unchanged — `401604` fails as an error row and the file retries (§10.5).
