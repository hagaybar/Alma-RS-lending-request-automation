# Identifier Detection Logic

## Overview

The Resource Sharing Forms Processor automatically detects whether an identifier is a **PMID** (PubMed ID) or **DOI** (Digital Object Identifier) by analyzing the identifier format using pattern matching.

**Important:** The script **IGNORES** the user-provided `identifier_type` column in the TSV file, as user input is often incorrect or unreliable. Auto-detection based on objective patterns is more accurate.

## Detection Rules

### PMID Detection

**Pattern:** `^\d{6,9}$`

**Characteristics:**
- **Numeric only** (no letters or special characters)
- **6-9 digits** (typically 7-8, but allow 6-9 for edge cases)

**Examples:**

| Identifier | Detected As | Reason |
|------------|-------------|--------|
| `33219451` | **PMID** ✓ | 8 digits, numeric only |
| `12345678` | **PMID** ✓ | 8 digits, numeric only |
| `123456` | **PMID** ✓ | 6 digits (min length) |
| `123456789` | **PMID** ✓ | 9 digits (max length) |
| `123` | **None** ✗ | Too short (< 6 digits) |
| `1234567890` | **None** ✗ | Too long (> 9 digits) |
| `abc123` | **None** ✗ | Contains letters |
| `123-456` | **None** ✗ | Contains hyphen |

**Validation:**
```python
import re
pmid_pattern = re.compile(r'^\d{6,9}$')

identifier = "33219451".strip()
if pmid_pattern.match(identifier):
    # Detected as PMID
    pass
```

### DOI Detection

**Pattern:** `^10\.\d+/.*`

**Characteristics:**
- **Starts with "10."** (all DOIs begin with this prefix)
- **Contains at least one "/"** separator
- **May include various characters:** letters, numbers, hyphens, periods, underscores, etc.

**Prefix Handling:**

Common DOI URL prefixes are **automatically stripped** before pattern matching:
- `https://doi.org/`
- `http://dx.doi.org/`
- `doi:`

**Examples:**

| Original Identifier | After Prefix Strip | Detected As | Reason |
|---------------------|-------------------|-------------|--------|
| `10.1038/s41591-020-1124-9` | (unchanged) | **DOI** ✓ | Starts with "10.", has "/" |
| `10.1000/example.2024.001` | (unchanged) | **DOI** ✓ | Starts with "10.", has "/" |
| `https://doi.org/10.1038/example` | `10.1038/example` | **DOI** ✓ | Prefix stripped, valid format |
| `http://dx.doi.org/10.1234/abc` | `10.1234/abc` | **DOI** ✓ | Prefix stripped, valid format |
| `doi:10.1000/test` | `10.1000/test` | **DOI** ✓ | Prefix stripped, valid format |
| `11.1038/example` | (unchanged) | **None** ✗ | Wrong prefix (11. not 10.) |
| `10.abc` | (unchanged) | **None** ✗ | No slash separator |
| `10.1234` | (unchanged) | **None** ✗ | No slash separator |

**Validation:**
```python
import re

identifier = "https://doi.org/10.1038/example"

# Strip common prefixes
for prefix in ['https://doi.org/', 'http://dx.doi.org/', 'doi:']:
    if identifier.lower().startswith(prefix.lower()):
        identifier = identifier[len(prefix):]
        break

# Check DOI pattern
doi_pattern = re.compile(r'^10\.\d+/.*')
if doi_pattern.match(identifier.strip()):
    # Detected as DOI
    pass
```

### Unknown Identifiers

If the identifier doesn't match either PMID or DOI patterns:

**Behavior:**
- Detection returns `None`
- File is **skipped** (not processed)
- Error logged with identifier value
- Status in CSV report: `skipped`
- Error message: "Could not detect identifier type: '{identifier}'"
- File remains in input folder for manual review

**Example Unknown Identifiers:**

| Identifier | Issue |
|------------|-------|
| `` (empty) | No value provided |
| `invalid123` | Not numeric (PMID), wrong prefix (DOI) |
| `12345` | Too short for PMID (< 6 digits) |
| `11.1234/example` | Wrong DOI prefix (11. instead of 10.) |
| `ABC-123-XYZ` | Invalid format for both PMID and DOI |

## Implementation Flow

```
┌─────────────────────────────────────┐
│ Input: identifier from TSV          │
│ (user-provided identifier_type      │
│  is IGNORED)                        │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Strip whitespace                    │
│   identifier = identifier.strip()   │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Strip DOI prefixes (if present)     │
│   - https://doi.org/                │
│   - http://dx.doi.org/              │
│   - doi:                            │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Apply PMID pattern: ^\d{6,9}$       │
│ Match? → Return 'pmid'              │
└────────────────┬────────────────────┘
                 │ No match
                 ▼
┌─────────────────────────────────────┐
│ Apply DOI pattern: ^10\.\d+/.*      │
│ Match? → Return 'doi'               │
└────────────────┬────────────────────┘
                 │ No match
                 ▼
┌─────────────────────────────────────┐
│ Return None (unknown format)        │
│ → File skipped, error logged        │
└─────────────────────────────────────┘
```

## Why Ignore User-Provided Type?

The `identifier_type` column in the TSV (provided by users via Microsoft Forms) is **unreliable** for several reasons:

### Common User Errors

1. **Confusion between PMID and DOI**
   - Users may not understand the difference
   - Example: User enters "PMID" but provides DOI

2. **Typos**
   - "PIMD" instead of "PMID"
   - "DO1" instead of "DOI"

3. **Optional field**
   - User may leave it blank or select "Other"

4. **Case sensitivity issues**
   - "pmid", "Pmid", "PMID" - inconsistent casing

### Benefits of Auto-Detection

✓ **100% reliable** - Based on objective pattern matching
✓ **No user error** - Not dependent on user knowledge
✓ **Consistent** - Same logic applied to all identifiers
✓ **Testable** - Can be unit tested with known patterns
✓ **Graceful failure** - Unknown formats are skipped with clear error messages

## Integration with Metadata Enrichment

After detection, the identifier type is used to fetch metadata from the correct source:

### PMID → PubMed API

```python
detected_type = detect_identifier_type("33219451")
# Returns: 'pmid'

# Fetch metadata from PubMed explicitly
from almaapitk.utils.citation_metadata import enrich_citation_metadata

metadata = enrich_citation_metadata(
    pmid="33219451",
    source_type='pmid'  # Explicit source (no fallback)
)

# Returns metadata from NCBI E-utilities API
```

### DOI → Crossref API

```python
detected_type = detect_identifier_type("10.1038/s41591-020-1124-9")
# Returns: 'doi'

# Fetch metadata from Crossref explicitly
metadata = enrich_citation_metadata(
    doi="10.1038/s41591-020-1124-9",
    source_type='doi'  # Explicit source (no fallback)
)

# Returns metadata from Crossref REST API
```

### Unknown → Skip with Error

```python
detected_type = detect_identifier_type("invalid123")
# Returns: None

# Raises IdentifierDetectionError
raise IdentifierDetectionError(
    "Could not detect identifier type: 'invalid123'. "
    "Expected PMID (6-9 digits) or DOI (10.xxxx/...)."
)

# File skipped, error logged, continues to next file
```

## Testing Identifier Detection

### Test Cases

```python
test_cases = [
    # PMID tests
    ("33219451", "pmid"),       # Valid PMID (8 digits)
    ("12345678", "pmid"),       # Valid PMID (8 digits)
    ("123456", "pmid"),         # Valid PMID (6 digits, minimum)
    ("123456789", "pmid"),      # Valid PMID (9 digits, maximum)
    ("123", None),              # Invalid (too short)
    ("1234567890", None),       # Invalid (too long)
    ("abc123", None),           # Invalid (contains letters)

    # DOI tests
    ("10.1038/s41591-020-1124-9", "doi"),  # Valid DOI
    ("10.1000/example.2024.001", "doi"),   # Valid DOI
    ("https://doi.org/10.1038/example", "doi"),  # With prefix
    ("http://dx.doi.org/10.1234/abc", "doi"),    # With prefix
    ("doi:10.1000/test", "doi"),           # With prefix
    ("11.1038/example", None),             # Invalid (wrong prefix)
    ("10.abc", None),                      # Invalid (no slash)

    # Edge cases
    ("", None),                 # Empty
    ("   33219451   ", "pmid"), # With whitespace (stripped)
    ("  10.1038/example  ", "doi"),  # With whitespace (stripped)
]

for identifier, expected_type in test_cases:
    detected = detect_identifier_type(identifier)
    assert detected == expected_type, \
        f"Failed: {identifier!r} → expected {expected_type}, got {detected}"

print("All tests passed!")
```

### Running Tests

```python
# Test PMID detection
python3 -c "from resource_sharing_forms_processor import ResourceSharingFormsProcessor as P; \
  p = P({'alma_settings': {'environment': 'SANDBOX', 'owner': 'MAIN'}, \
         'file_processing': {'input_folder': '.', 'processed_folder': '.', 'output_dir': '.'}, \
         'verbose': False}, dry_run=True); \
  assert p.detect_identifier_type('33219451') == 'pmid'; \
  assert p.detect_identifier_type('10.1038/test') == 'doi'; \
  assert p.detect_identifier_type('invalid') == None; \
  print('Tests passed!')"
```

## Debugging Detection Issues

### Enable Verbose Logging

```bash
python3 \
  resource_sharing_forms_processor.py \
  --config config.json \
  --verbose
```

**Look for log messages:**
```
DEBUG: Detected PMID: 33219451
DEBUG: Detected DOI: 10.1038/example
WARNING: Could not detect identifier type: invalid123
```

### Check CSV Report

Open the CSV report in `output/reports/`:

| Column | What to Check |
|--------|---------------|
| `Identifier_Type` | Should be "pmid" or "doi" (lowercase) |
| `Status` | If "skipped", check `Error_Message` |
| `Error_Message` | Shows detection error details |

### Manual Testing

Test detection logic with specific identifiers:

```bash
# Create test TSV
echo -e "RELAIS\tTest\ttest@test.com\tPMID\t33219451\tTest" > test.tsv

# Run with verbose logging
python3 \
  resource_sharing_forms_processor.py \
  --config config.json \
  --verbose

# Check detection in log
grep "Detected" output/logs/processor_*.log
```

## Edge Cases

### 1. Multiple Identifiers in One Field

**Input:** `33219451, 10.1038/example`

**Behavior:** Script expects single identifier per field. This will fail detection (contains comma).

**Solution:** Submit separate form entries for each article.

### 2. Identifier with Extra Spaces

**Input:** `  33219451  ` or `  10.1038/example  `

**Behavior:** Whitespace is **automatically stripped** before detection.

**Result:** Works correctly.

### 3. DOI with Multiple Prefixes

**Input:** `https://doi.org/doi:10.1038/example`

**Behavior:** Only the first matching prefix is stripped.

**Result:** May fail detection if nested prefixes create invalid format.

**Solution:** Clean identifier value before submission.

### 4. DOI in PDF URL Format

**Input:** `https://doi.org/10.1038/example.pdf`

**Behavior:** Detected as DOI (`.pdf` is part of DOI suffix).

**Result:** May fail metadata fetch if actual DOI doesn't include `.pdf`.

**Solution:** Remove `.pdf` extension from DOI.

## Summary

| Detection Feature | Implementation |
|-------------------|----------------|
| PMID Pattern | `^\d{6,9}$` (numeric, 6-9 digits) |
| DOI Pattern | `^10\.\d+/.*` (starts with 10., has slash) |
| Prefix Stripping | Yes (https://doi.org/, http://dx.doi.org/, doi:) |
| Whitespace Handling | Automatic strip before detection |
| User Input | **IGNORED** (unreliable) |
| Unknown Format | Skip file, log error, continue processing |
| Validation | Pattern matching + format checks |
| Logging | DEBUG level for successful detection, WARNING for failures |

**Key Principle:** Trust the identifier format, not the user-provided type.
