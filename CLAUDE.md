# Alma RS Lending Request Automation

Automated processing of Resource Sharing lending requests from Microsoft Forms (via Power Automate/SharePoint) to Alma ILS, with citation metadata enrichment from PubMed and Crossref.

## Commands

```bash
poetry install
poetry run pytest
poetry run python resource_sharing_forms_processor.py --config config/rs_forms_config.json          # dry run (default)
poetry run python resource_sharing_forms_processor.py --config config/rs_forms_config.json --live   # live, one run
```

## Rules for every change

- **Dry run by default**: API calls only with `--live`.
- **One attempt per file, no automatic retry** (GH #48): any failure moves the file to `failed_files/`; a person moves it back to retry. Don't reintroduce automatic retries.
- **`SHEB` is ambiguous**: a *partner code* on the lending path, a *proxy user code* on the borrowing path. Never move one between paths.
- **Borrowing field values are evidence-backed**: change a value in `docs/BORROWING_REQUESTS.md`, with evidence, before changing it in code.
- **Production's duplicate check stays off**: `check_patron_duplicate_borrowing_requests` was deliberately left unchanged at go-live (2026-10-22); duplicates are caught by monitoring `[BORROWING-UNCONFIRMED]` (guidebook §8.3–8.4). Don't flip it.

## Where it runs

Production: a Windows scheduled task on the production host, every 5 minutes, from the `prod` branch (local-only batch file). Deployment and operations notes for the production host are kept in the owner's private documentation; the user-level instructions say where. Keys: `ALMA_SB_API_KEY` (sandbox), `ALMA_PROD_API_KEY` (production).

## Where to look

- Folder map, how the pipeline works, deployment details, repo quirks: [docs/architecture.md](docs/architecture.md)
- Alma resource-sharing API (requests, partners, error codes such as 401604 and 402362): load the `alma-resource-sharing` skill
- Borrowing field values and their evidence: [docs/BORROWING_REQUESTS.md](docs/BORROWING_REQUESTS.md)
- Changing the `almaapitk` pin: follow [docs/almaapitk-bump-protocol.md](docs/almaapitk-bump-protocol.md) (binding; one bump at a time, audit in `docs/almaapitk-<version>-audit.md`)
- Open work: [docs/OPEN-TASKS.md](docs/OPEN-TASKS.md)
- `AGENTS.md` is the reviewer's brief (Codex reviews, report only)
