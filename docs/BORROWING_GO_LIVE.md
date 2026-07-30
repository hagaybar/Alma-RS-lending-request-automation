# Borrowing go-live sequence

> Written **2026-07-30**, the day PR #8 merged to `main` (merge commit
> `a11bbf1`). Context: implementation complete, decisive SANDBOX matrix tests
> green (T-12/T-01/T-02/T-02b + the T-04 copyright verdict — see
> `BORROWING_SB_TEST_MATRIX.md`). Borrowing is **inert everywhere** until a
> machine config gains `file_processing.borrowing_input_folder` — that edit
> *is* the activation decision (`borrowing.enabled` defaults `true` and is
> only a kill switch).

## The sequence

1. **Verify the DevSandbox auto-deploy** (automatic, next scheduled run on
   masedet): `main` pulled, `poetry install` brings almaapitk 0.5.0. Check
   the lending heartbeat log afterwards — lending must be unaffected
   (borrowing is not imported at startup and has no folder configured).

2. **Activate on the masedet sandbox config** (`DevSandbox`, gitignored
   `*_sandbox` config): add `borrowing_input_folder` and the `borrowing`
   block from `config/rs_forms_config.example.json`. The example already
   ships the correct values: 4-column mapping
   (`requestor/identifier/notes/order_number` — no `material_type`),
   `agree_to_copyright_terms: true` (Alma rejects `false` at create,
   error 401897), `enabled: true`.

3. **T-10/T-11 end-to-end rehearsal** (last unexecuted matrix item): drop a
   real 4-column borrowing TSV into the sandbox borrowing folder and let the
   scheduled sandbox batch process it `--live` against **Alma SANDBOX**.
   Verify: request created in the SB UI (remember augmentation rewrites
   title/author/year from the real PMID), per-file log, daily CSV row.
   Record the request_id in the matrix §4 cleanup log and cancel it.

4. **Librarian inputs** (parallel, not code-blocking):
   - GH #32 — the 8 proxy accounts' Active/Yearly TOU limits; run matrix
     T-09 (all-8 affiliation check) alongside.
   - `lcc_number_template` verdict (ships empty = field omitted); run T-07
     if a template is adopted.

5. **Production preflight**: confirm the customer parameter
   `check_patron_duplicate_borrowing_requests=true` in **PRODUCTION** Alma —
   the timeout-recovery mechanism (402362) depends on it.

6. **Ship to prod**: merge `main` → `prod` (explicit approval only, per repo
   rules — auto-deploys to `D:\Scripts\Prod\` on the next scheduled run),
   then add `borrowing_input_folder` + `borrowing` block to the prod config.
   Coordinate with the Power Automate flow owner: the not-held fork writes
   its 4-column TSV to the prod borrowing folder location.

7. **Partner-coordinated live tests**: first real borrowing requests against
   production Alma, with the partners in the loop.

## Outstanding cleanup

Three 2026-07-30 test requests were deliberately left in SANDBOX for UI
inspection (user `SHEB`, owner `AM1`): `39940482970004146`,
`39940483500004146`, `39940484010004146`. Cancel via
`scripts/sb_borrowing_tests.py --cancel <id> --user SHEB` when done and tick
them off in the matrix §4 cleanup log. (The four `AM1` requests from the
upstream AlmaAPITK session are **not ours** — leave them.)

## References

- `docs/BORROWING_REQUESTS.md` — the guidebook (field evidence, §4.6
  copyright verdict, error codes, operational gotchas)
- `docs/BORROWING_SB_TEST_MATRIX.md` — test matrix with dated verdicts and
  the §4 cleanup log
- `README.md` § Borrowing Requests — activation model and TSV format
