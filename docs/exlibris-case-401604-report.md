# Alma error `401604` on `POST /users/{user_id}/resource-sharing-requests`

**Full API request and response, captured live.**
Prepared for the open Ex Libris support case. Tel Aviv University.

---

> **Internal note — read before sending, then delete this block.**
>
> 1. This capture was run against **SANDBOX**, because the production
>    occurrence (2026-09-02) cannot be re-run safely: the production pipeline
>    now clears `401604` automatically, so a live production re-run would
>    create and send a real ILL request. Say the word and the same capture can
>    be produced against PRODUCTION — the create is *rejected*, so nothing
>    would be created there either, but it is a production call and needs your
>    go-ahead.
> 2. The earlier case text said *"when using the `override=true` parameter"*.
>    The parameter this endpoint defines is **`override_blocks`**, not
>    `override`. Decide how you want to correct that before sending. This
>    report deliberately sends **no override parameter of any kind**, so what
>    follows is Alma's plain default behaviour and is not affected either way.
> 3. Section 6 does not disclose what happens *with* `override_blocks=true`.
>    That is a separate decision.

---

## 1. What this report shows

One API call, captured byte-for-byte: a borrowing (user resource-sharing)
request for a **journal article that Tel Aviv University cannot supply**, for
which Alma nevertheless refuses the create with

```
HTTP 400
errorCode    401604
errorMessage Warning - The institutional inventory has services for the requested title.
```

This is the case the Product Manager asked for: *an article that is not
included in TAU's inventory, but whose title is.* Section 5 proves both halves
of that statement from Alma's own API.

No override parameter was sent. This is the endpoint's default behaviour.

## 2. Environment and identifiers

| | |
|---|---|
| Environment | Alma **SANDBOX**, EU region (`api-eu.hosted.exlibrisgroup.com`) |
| Endpoint | `POST /almaws/v1/users/{user_id}/resource-sharing-requests` |
| User (proxy patron) | `SHEB` |
| Resource sharing library (`owner`) | `AM1` |
| Date/time of capture | **2026-09-14, 09:57:47–48 UTC** |
| Alma tracking ID (JSON call) | `E01-1409095747-SS4OE-AWAE1612166395` |
| Alma tracking ID (XML call) | `E01-1409095748-ZYFO9-AWAE1612166395` |
| `X-Request-ID` (JSON / XML) | `MEyDSySoty` / `6eYNoqQBfF` |
| Original production occurrence | 2026-09-02, same identifier, same error |

The requested article:

| | |
|---|---|
| PMID | `36374288` |
| DOI | `10.1097/JMQ.0000000000000095` |
| Article | "Validation of the Algorithmic Prediction of Failure Modes in Health Care Methodology: Applied to the Department of Sterile Supply and Equipment." |
| Journal | *American Journal of Medical Quality* |
| Published | **2023**, volume **38**, issue **1**, pages 23–28 |
| e-ISSN as sent | `1555-824X` |

## 3. The request, verbatim

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

## 4. The response, verbatim

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

Note the wording is **"Warning"**, but the create is refused with HTTP 400 and
no request is created. Over the API there is no equivalent of the staff UI's
**Confirm** button.

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

### 5.4 How the request reached the API at all

Requests are routed to this endpoint by an upstream availability check
(LibKey) that asks whether **this article** is available to TAU. It answered
"not available", correctly, and routed the citation to the borrowing path.
Alma then answers a different question — "does the institution have any
service for this title?" — and answers "yes", also correctly. Both answers are
right; they are answers to different questions.

## 6. The questions on the case

Restated, with what our own testing already establishes, so the remaining gaps
are clear.

**Q1 — Which validation or blocking conditions does the override parameter
actually bypass?**
Still open. The parameter is documented as a *patron block* override, but the
case concerns a *self-ownership* block, and the documentation does not say
whether one parameter governs both. Please state the full list of conditions
it suppresses, so we can judge what else we would be switching off.

**Q2 — Is the institutional-inventory check title-level only, or are
additional criteria used?**
Section 5 shows a match occurring on Title and ISSN with an article three
volumes outside every coverage statement on the only portfolio that exists.
That is consistent with the documented "Locate by Fields" set (LCCN, System
Control Number, Title, ISBN/ISSN), none of which is article-level.
**Please confirm explicitly: does the Self Ownership check consult electronic
coverage dates, volumes or issues at any point?** Our evidence says no; we
would like that confirmed rather than inferred.

**Q3 — When an end user submits an ILL request through the Primo Resource
Sharing form, does Primo use this same endpoint, or the same underlying
request-creation mechanism?**
Still open, and material: through Primo, self-ownership appears to be
determined by resolving the incoming OpenURL, which *is* coverage-aware — so
the same citation may behave differently through Primo than through the API.
Please confirm whether the two paths share a creation mechanism and whether
they share this check.

## 7. What we are asking for

1. Confirmation that `401604` firing here is expected behaviour given the
   configuration — or, if it is not, what in our configuration causes it. The
   Product Manager's view that "this error is not supposed to occur" does not
   match section 5; we would like that reconciled.
2. Direct answers to Q1–Q3 above.
3. Whether the Self Ownership check can be made **coverage-aware**, or the API
   given the staff UI's **Confirm** semantics, so that an article outside
   coverage is not blocked by the presence of the journal title.

Any of the tracking IDs in section 2 will locate these exact calls in your
logs.

---

## Appendix — how this capture was produced

The request body was built by the production code path
(`rs_requests/borrowing.py` → `almaapitk.build_user_rs_request` →
`Users.create_user_rs_request`), with the pipeline's automatic
self-ownership retry switched off (`borrowing.override_self_ownership:
false`) so that the first attempt is the only attempt. The HTTP session was
instrumented to record the prepared request and the raw response; the API key
is the only value redacted. Nothing was created in Alma — the create was
rejected — so there is nothing to clean up.

Capture script and raw JSON are held outside this repository (job scratch,
not committed) and can be reproduced on demand.
