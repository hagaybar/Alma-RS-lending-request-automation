"""Shared fixtures for borrowing request tests."""

# Minimal config for borrowing tests (required by test_borrowing_tsv.py)
CONFIG = {
    "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
}
