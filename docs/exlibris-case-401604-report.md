# Alma error `401604` on `POST /users/{user_id}/resource-sharing-requests`

**Full API request and response, captured live.**
Prepared for the open Ex Libris support case. Tel Aviv University.

---

## 1. What this report shows

Two API calls, captured byte-for-byte, for a **journal article that Tel Aviv
University cannot supply** although it holds the journal title. The request
bodies are identical; the calls differ only in one query parameter.

```
Call A  no override parameter        HTTP 400  401604  request refused
Call B  ?override_blocks=true        HTTP 200          request created
```

A third call, B′, repeats B and is **left live in SANDBOX** as request
`43257186260004146`, so the result can be inspected in Alma directly.

Call A is the failure reported on this case:

```
HTTP 400
errorCode    401604
errorMessage Warning - The institutional inventory has services for the requested title.
```

This is the example the Product Manager asked for: *an article that is not
included in TAU's inventory, but whose title is.* Section 5 proves both halves
of that statement from Alma's own API.

Both calls were made against **SANDBOX**. The production occurrence of
2026-09-02 used the same identifier and returned the same error; a production
capture can be supplied if it is needed.

## 2. Environment and identifiers

| | |
|---|---|
| Environment | Alma **SANDBOX**, EU region (`api-eu.hosted.exlibrisgroup.com`) |
| Endpoint | `POST /almaws/v1/users/{user_id}/resource-sharing-requests` |
| User (proxy patron) | `SHEB` — calls A and B; `ASAF` for the live call B′ |
| Resource sharing library (`owner`) | `AM1` |
| Original production occurrence | 2026-09-02, same identifier, same error |

Identifiers for the individual calls, for log retrieval:

| Call | Time (UTC) | Alma tracking ID | `X-Request-ID` |
|---|---|---|---|
| A — JSON, no override | 2026-09-14 09:57:47 | `E01-1409095747-SS4OE-AWAE1612166395` | `MEyDSySoty` |
| A — XML, no override | 2026-09-14 09:57:48 | `E01-1409095748-ZYFO9-AWAE1612166395` | `6eYNoqQBfF` |
| B — `override_blocks=true` | 2026-09-14 10:16:54 | *(none — HTTP 200)* | `Mm0aPgUstx` |
| B′ — live request, left in SANDBOX | 2026-09-14 10:19:09 | *(none — HTTP 200)* | `Sa820EdnS9` |

The request created by call B′ is **`43257186260004146`** and has deliberately
been left in place in SANDBOX so it can be opened and inspected (section 6.3).

The requested article:

| | |
|---|---|
| PMID | `36374288` |
| DOI | `10.1097/JMQ.0000000000000095` |
| Article | "Validation of the Algorithmic Prediction of Failure Modes in Health Care Methodology: Applied to the Department of Sterile Supply and Equipment." |
| Journal | *American Journal of Medical Quality* |
| Published | **2023**, volume **38**, issue **1**, pages 23–28 |
| e-ISSN as sent | `1555-824X` |

## 3. Call A — the request, verbatim

```http
POST /almaws/v1/users/SHEB/resource-sharing-requests HTTP/1.1
Host: api-eu.hosted.exlibrisgroup.com
Authorization: apikey <redacted>
Content-Type: application/json
Accept: application/json
Content-Length: 841
```

No query parameters were sent. In particular **no `override_blocks`**, and no
`user_id_type`.

Body:

```json
{
  "owner": "AM1",
  "format": { "value": "DIGITAL" },
  "citation_type": { "value": "CR" },
  "pickup_location_type": "LIBRARY",
  "pickup_location": { "value": "AM1" },
  "title": "Validation of the Algorithmic Prediction of Failure Modes in Health Care Methodology: Applied to the Department of Sterile Supply and Equipment.",
  "author": "Kobo-Greenhut A, Sharlin O, Fishman T, Daniel L, Frankenthal H, Eisenberg VH, Zimlichman E, Orkin D",
  "journal_title": "American journal of medical quality : the official journal of the American College of Medical Quality",
  "year": "2023",
  "volume": "38",
  "issue": "1",
  "pages": "23-28",
  "start_page": "23",
  "end_page": "28",
  "issn": "1555-824X",
  "doi": "10.1097/JMQ.0000000000000095",
  "pmid": "36374288",
  "agree_to_copyright_terms": true,
  "requested_media": "7",
  "allow_other_formats": false,
  "willing_to_pay": false
}
```

## 4. Call A — the response, verbatim

**HTTP 400**, returned after **7.675 seconds**.

Response headers (JSON call):

```http
HTTP/1.1 400
Content-Type: application/json;charset=UTF-8
Content-Length: 211
X-Request-ID: MEyDSySoty
X-Exl-Api-Remaining: 498668
Date: Mon, 14 Sep 2026 09:57:47 GMT
Server: Layer7-API-Gateway
```

Response body (JSON):

```json
{
  "errorsExist": true,
  "errorList": {
    "error": [
      {
        "errorCode": "401604",
        "errorMessage": "Warning - The institutional inventory has services for the requested title.",
        "trackingId": "E01-1409095747-SS4OE-AWAE1612166395"
      }
    ]
  }
}
```

The identical request with `Accept: application/xml` — the XML form that was
requested:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<web_service_result xmlns="http://com/exlibris/urm/general/xmlbeans">
  <errorsExist>true</errorsExist>
  <errorList>
    <error>
      <errorCode>401604</errorCode>
      <errorMessage>Warning - The institutional inventory has services for the requested title.</errorMessage>
      <trackingId>E01-1409095748-ZYFO9-AWAE1612166395</trackingId>
    </error>
  </errorList>
</web_service_result>
```

Note the wording is **"Warning"**, but the response is HTTP 400 and no request
is created.

## 5. Why this is exactly the requested example

All of the following comes from read-only Alma API calls made immediately
after the failed create, in the same tenant.

### 5.1 The title is in TAU's inventory

`GET /almaws/v1/bibs/9932873215504146`

| | |
|---|---|
| MMS ID | `9932873215504146` |
| `245 $a` | `American journal of medical quality.` |
| `022 $a` | **`1555-824X`** — the exact ISSN sent in the request |
| `023 $a` | `1062-8606` |
| `010 $a` | `2005212289` (LCCN) |
| `035 $a` | `(OCoLC)59822929`, `(CONSER)  2005212289`, `(EXLCZ)99954925598629`, … |

So the record carries a matching **Title**, a matching **ISSN**, an **LCCN**
and **System Control Numbers** — the four fields that *Locating Items for
Resource Sharing* documents as the default "Locate by Fields" set.

### 5.2 The article is not in TAU's inventory

`GET /almaws/v1/bibs/9932873215504146/holdings`

```
total_record_count: 0
```

No physical holdings at all.

`GET /almaws/v1/bibs/9932873215504146/portfolios`

```
total_record_count: 1
```

Exactly one electronic portfolio, `53328251740004146`, availability
`11 / Available`, in electronic collection `61328259000004146`
(Sage Journals, service `62328258990004146`), activated 2020-08-03.

`GET /almaws/v1/electronic/e-collections/61328259000004146/e-services/62328258990004146/portfolios/53328251740004146`

```json
"coverage_details": {
  "coverage_in_use": { "value": "0", "desc": "Only local" },
  "global_date_coverage_parameters": [
    { "from_year": "1993", "from_month": "3", "from_day": "1",
      "from_volume": "8", "from_issue": "1",
      "until_year": "2020", "until_month": "12", "until_day": "31",
      "until_volume": "35", "until_issue": "6" }
  ],
  "local_date_coverage_parameters": [
    { "from_year": "1986", "from_volume": "1", "from_issue": "1",
      "until_year": "2020", "until_volume": "35", "until_issue": "6" }
  ],
  "perpetual_date_coverage_parameters": []
}
```

The coverage in use is **local**, and it ends at **2020, volume 35, issue 6**.
There is **no perpetual coverage**.

### 5.3 The two facts side by side

| | |
|---|---|
| Requested | **2023**, volume **38**, issue **1** |
| Held | up to **2020**, volume **35**, issue **6** |
| Gap | **3 years, 3 volumes** |

TAU holds the *journal*. TAU does not, and cannot, supply the *article*. The
title-level match is real; the service for this citation does not exist.

(For context: the journal changed publisher — the `10.1097` DOI prefix is
Lippincott, while the portfolio TAU holds is Sage — which is why the coverage
stops where it does.)

## 6. Call B — the same request with `override_blocks=true`

The identical body was then posted again, adding one query parameter and
changing nothing else. It was accepted.

### 6.1 The request

```http
POST /almaws/v1/users/SHEB/resource-sharing-requests?override_blocks=true HTTP/1.1
Host: api-eu.hosted.exlibrisgroup.com
Authorization: apikey <redacted>
Content-Type: application/json
Accept: application/json
Content-Length: 841
```

The body is byte-for-byte the body in section 3 — same 841 bytes, same user,
same `owner`, same citation. `override_blocks=true` is the only difference
between a refused create and an accepted one.

### 6.2 The response

**HTTP 200**, returned after **11.086 seconds** (`X-Request-ID: Mm0aPgUstx`,
2026-09-14 10:16:54 GMT). Selected fields of the created request:

```json
{
  "request_id": "43257185010004146",
  "external_id": "972TAU0075707",
  "status": { "value": "LOCATE_IN_PROCESS", "desc": "Locate in process" },
  "partner": { "value": "TLL", "desc": "RapidILL" },
  "owner": "AM1",
  "format": { "value": "DIGITAL", "desc": "Digital" },
  "citation_type": { "value": "CR", "desc": "Physical Article" },
  "pickup_location": { "value": "AM1", "desc": "Life Sciences and Medicine Library" },
  "journal_title": "American Journal of Medical Quality",
  "year": "2023",
  "volume": "38",
  "issue": "1",
  "issn": "1062-8606",
  "created_date": "2026-09-14Z"
}
```

Two details of the stored request are worth recording.

Alma assigned partner `TLL` (RapidILL) and status *Locate in process* on
create.

The stored `issn` is **`1062-8606`**, not the `1555-824X` that was sent — the
print ISSN of bib `9932873215504146`, the record in section 5.1. Alma's
augmentation resolved the citation to that same bib.

### 6.3 A live request in SANDBOX, for your inspection

So that this can be examined in Alma directly rather than only on paper, the
same body was posted once more — again with `override_blocks=true`, changing
nothing but the proxy patron — and **left in place**:

| | |
|---|---|
| Request ID | **`43257186260004146`** |
| Requesting user | `ASAF` |
| Resource sharing library | `AM1` |
| Alma external ID | `972TAU0075708` |
| Created | 2026-09-14 10:19:09 UTC (`X-Request-ID: Sa820EdnS9`) |
| Status **on read-back, ~2 seconds later** | `READY_TO_SEND` — "Ready to be sent" |
| Partner | `TLL` — RapidILL |

The status was read back about two seconds after the create, with no staff
action in between.

The request from section 6.2 (`43257185010004146`, user `SHEB`) was cancelled
and will show in SANDBOX as *Cancelled by staff*; it is retained as the A/B
twin of Call A.

B′ runs under a different patron because an identical create under `SHEB`
after that cancellation was refused with `402362` "Patron has duplicate
request" (tracking ID `E01-1409101906-JRTJG-AWAE673038864`).

## 7. Our questions

These are the questions from the original case, unchanged. Sections 1–6 are
the data they were asked for.

1. **Which validation or blocking conditions does the override parameter
   actually bypass?**

2. **Is the institutional-inventory check based only on a title match, or are
   additional matching criteria used?**

3. **When a user submits an ILL request through the Primo Resource Sharing
   form, is the request creation performed through this same API endpoint?**

Any tracking ID or `X-Request-ID` in section 2 will locate these calls in your
logs, and request `43257186260004146` is live in our SANDBOX for inspection.

---

## Appendix — how this capture was produced

The request body was built once, by the production code path
(`rs_requests/borrowing.py` → `almaapitk.build_user_rs_request` →
`Users.create_user_rs_request`), and then reused **unchanged** for every call
in this report. Calls A, B and B′ therefore differ only in the query string
and, for B′, the patron in the path. The HTTP session was instrumented to
record the prepared request and the raw response; the API key is the only
value redacted anywhere in this document.

Call A created nothing — it was refused. Call B created request
`43257185010004146`, which was then cancelled. Call B′ created request
`43257186260004146`, which is **live in SANDBOX** and awaiting your
inspection.

The capture scripts and the raw JSON are retained and can be supplied, or the
whole sequence reproduced, on request.
