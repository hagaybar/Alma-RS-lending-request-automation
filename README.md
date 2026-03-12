# Resource Sharing Forms Processor

Automated processing of Microsoft Forms submissions to create Alma lending requests with citation metadata enrichment from PubMed and Crossref.

## Overview

This script monitors a folder (typically synced with SharePoint) for TSV files containing form submissions from users requesting articles/materials. For each submission, it:

1. **Auto-detects identifier type** (PMID or DOI) from the identifier value
2. **Fetches citation metadata** from PubMed (PMID) or Crossref (DOI)
3. **Verifies Academic Staff status** by looking up user in Alma (when user_id provided)
4. **Creates lending request** in Alma via Partners API
5. **Moves processed file** to completed folder with timestamp
6. **Generates CSV report** with all results

## Features

- **Automatic identifier detection** - Ignores user-provided type, uses pattern matching
- **Citation metadata enrichment** - Auto-populates title, author, journal, year, volume, issue, pages, etc.
- **Academic Staff verification** - Looks up user in Alma to verify membership in "Academic staff" user group (code '04')
- **Two run modes:**
  - **Single-run**: Process all pending files once and exit
  - **Watch mode**: Continuous monitoring with graceful shutdown (Ctrl+C)
- **Skip on error** - Continues processing other files if one fails
- **Dry-run by default** - Safe testing without API calls
- **Comprehensive logging** - File and console output
- **CSV reporting** - Detailed results with success/error tracking

## Prerequisites

- Python 3.12+
- Poetry for dependency management
- Alma API access (SANDBOX or PRODUCTION)
- Environment variables:
  - `ALMA_SB_API_KEY` (for SANDBOX)
  - `ALMA_PROD_API_KEY` (for PRODUCTION)

## Installation

```bash
# Clone the repository
git clone https://github.com/hagaybar/Alma-RS-lending-request-automation.git
cd Alma-RS-lending-request-automation

# Install dependencies
poetry install

# Verify installation
poetry run python resource_sharing_forms_processor.py --help
```

## Quick Start

### 1. Generate Configuration File

```bash
poetry run python resource_sharing_forms_processor.py --generate-config my_config.json
```

Edit `my_config.json` to set your paths and settings.

### 2. Run Dry-Run Test

```bash
# Process files without making API calls
poetry run python resource_sharing_forms_processor.py --config my_config.json
```

### 3. Run Live (Single-Run Mode)

```bash
# Process all pending files once and exit
poetry run python resource_sharing_forms_processor.py --config my_config.json --live
```

### 4. Run Watch Mode (Continuous Monitoring)

```bash
# Monitor folder continuously, process new files as they appear
poetry run python resource_sharing_forms_processor.py --config my_config.json --watch --live
```

Press **Ctrl+C** to stop gracefully (completes current file before exiting).

## Configuration

See `config/rs_forms_config.example.json` for all options.

### Key Settings

```json
{
  "alma_settings": {
    "environment": "SANDBOX",     // or "PRODUCTION"
    "owner": "MAIN",               // Resource sharing library code
    "format_type": "DIGITAL"       // or "PHYSICAL"
  },

  "file_processing": {
    "input_folder": "/path/to/sharepoint/sync",
    "processed_folder": "/path/to/processed",
    "output_dir": "/path/to/output"
  },

  "watch_mode": {
    "poll_interval": 60   // Seconds between checks
  }
}
```

### WSL Path Conversion

If using Windows SharePoint sync with WSL:
- Windows path: `C:\Users\username\SharePoint\folder`
- WSL path: `/mnt/c/Users/username/SharePoint/folder`

## TSV File Format

Expected columns (tab-separated, no header row):

| Column | Name | Description | Used By Script |
|--------|------|-------------|----------------|
| 0 | partner_code | Partner institution code (e.g., "RELAIS") | ✓ Yes (required) |
| 1 | user_name | Requester full name | ✓ Yes (optional - fallback if Alma lookup fails) |
| 2 | user_id | Requester ID (Alma primary_id) | ✓ Yes (optional - triggers Alma lookup for Academic Staff verification) |
| 3 | is_faculty | Faculty status (yes/no) | ✓ Yes (optional - fallback if Alma lookup fails) |
| 4 | identifier | PMID or DOI value | ✓ Yes (auto-detected) |
| 5 | comments | Optional additional notes | ✓ Yes (appended to note) |
| 6 | order_number | Form order number | ✓ Yes (required - used in external_id) |

**Example TSV:**
```
SHEB	David, Levi	User_ID_1234	yes	33393893	שיבא - הזמנה עם פרטי משתמש	Order_Num_24586
RELAIS				10.1038/example	Urgent request	Order_Num_24587
```

## Identifier Detection

The script automatically detects whether an identifier is a PMID or DOI based on its format:

### PMID Detection
- **Pattern:** Numeric only, 6-9 digits
- **Examples:**
  - ✓ `33219451` → PMID
  - ✓ `12345678` → PMID
  - ✗ `123` → Too short
  - ✗ `abc123` → Contains letters

### DOI Detection
- **Pattern:** Starts with "10.", contains "/"
- **Examples:**
  - ✓ `10.1038/s41591-020-1124-9` → DOI
  - ✓ `https://doi.org/10.1038/example` → DOI (prefix stripped)
  - ✓ `doi:10.1000/example` → DOI (prefix stripped)

See `docs/IDENTIFIER_DETECTION.md` for detailed logic.

## Testing

```bash
# Run smoke test
poetry run python scripts/smoke_project.py

# Run unit tests
poetry run python -m pytest tests/ -v
```

## Output

### Logs
Located in `<output_dir>/logs/`:
- **Filename:** `processor_YYYYMMDD_HHMMSS.log`
- **Contains:** Detailed processing log with DEBUG-level info

### CSV Reports
Located in `<output_dir>/reports/`:
- **Filename:** `processing_report_YYYYMMDD_HHMMSS.csv`
- **Columns:** Timestamp, Filename, Partner_Code, Full_Name, Requestor_ID, IsFaculty, Order_Number, Identifier_Type, Identifier, Status, Request_ID, External_ID, Title, Error_Message

### Processed Files
Located in `<processed_folder>/`:
- **Filename:** `YYYYMMDD_HHMMSS_originalname.tsv`
- **Purpose:** Preserves original file with timestamp for audit trail

## Error Handling

**The script continues processing on errors** - it does not fail the entire batch if one file has issues.

### Error Types

1. **Identifier Detection Error** → Status: `skipped`
2. **Metadata Fetch Error** → Status: `error`
3. **Lending Request Error** → Status: `error`
4. **File Processing Error** → Status: `error`

**All errors are logged with full details in the log file.**

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'almaapitk'"

**Solution:** Ensure dependencies are installed:
```bash
poetry install
```

### Issue: "Input folder does not exist"

**Solution:** Verify path in config file. For WSL, convert Windows paths:
- Windows: `C:\Users\...` → WSL: `/mnt/c/Users/...`

### Issue: "Could not detect identifier type"

**Cause:** Identifier doesn't match PMID or DOI pattern.
**Solution:** Check identifier value in TSV. Verify format: PMID = 6-9 digits, DOI = starts with "10." and has "/"

## Credits

- **PubMed API:** NCBI E-utilities (free, no API key required)
- **Crossref API:** Crossref REST API (free, no API key required)
- **Alma API:** Ex Libris Alma Partners API
- **AlmaAPITK:** Python toolkit for Alma API interactions

## Support

For issues or questions:
- Check `docs/IDENTIFIER_DETECTION.md` for identifier detection details
- Review log files in `output/logs/`
- Check CSV reports in `output/reports/`
- Review Alma API documentation at `https://developers.exlibrisgroup.com/alma/apis/partners/`
