"""Tests for PII masking in the test_user_retrieval diagnostic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_user_retrieval import format_user_report

SAMPLE = {
    "primary_id": "0273601",
    "first_name": "Jane",
    "last_name": "Patron",
    "contact_info": {
        "email": [{"email_address": "jane.patron@example.com", "preferred": True,
                   "email_type": [{"desc": "Personal"}]}],
        "phone": [{"phone_number": "0521234567", "preferred": True}],
        "address": [{"city": "Tel Aviv", "country": {"desc": "Israel"}, "preferred": True}],
    },
}


def test_contacts_masked_by_default():
    report = format_user_report(SAMPLE, show_raw=False)
    assert "jane.patron@example.com" not in report
    assert "0521234567" not in report
    assert "Tel Aviv" not in report
    # Domain may remain as a non-identifying hint; full address must not.
    assert "example.com" in report


def test_show_raw_includes_full_record():
    report = format_user_report(SAMPLE, show_raw=True)
    assert "jane.patron@example.com" in report
    assert "0521234567" in report
