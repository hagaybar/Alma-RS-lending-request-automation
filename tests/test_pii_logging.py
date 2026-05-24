"""Tests for PII-safe console logging helpers."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resource_sharing_forms_processor import mask_user_id


def test_mask_user_id_keeps_last_four():
    assert mask_user_id("123456789") == "*****6789"


def test_mask_user_id_short_is_fully_masked():
    assert mask_user_id("1234") == "***"
    assert mask_user_id("12") == "***"


def test_mask_user_id_empty_or_none():
    assert mask_user_id("") == "***"
    assert mask_user_id(None) == "***"
