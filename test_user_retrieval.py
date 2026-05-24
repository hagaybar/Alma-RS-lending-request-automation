#!/usr/bin/env python3
"""
Simple diagnostic to retrieve user information from Alma API.

By default, contact fields (email, phone, address) are masked and the raw
JSON is suppressed, so running this does not spill patron PII to the terminal.
Pass --show-raw to print the full unmasked record (explicit opt-in).

Usage:
    python test_user_retrieval.py
    python test_user_retrieval.py --user-id 027393602
    python test_user_retrieval.py --environment PRODUCTION --show-raw
"""

import argparse
import json
import sys

from almaapitk import AlmaAPIClient, Users


def _mask_email(addr: str) -> str:
    if not addr or "@" not in addr:
        return "***"
    return "***@" + addr.split("@", 1)[1]


def _mask_phone(num: str) -> str:
    if not num:
        return "***"
    digits = str(num)
    return "***" + digits[-2:] if len(digits) > 2 else "***"


def format_user_report(user_data: dict, show_raw: bool = False) -> str:
    """Build the human-readable user report.

    Identity fields (name, group, status) are shown; contact fields are
    masked unless show_raw is True. The full JSON is included only when
    show_raw is True.
    """
    lines = []
    lines.append(f"Primary ID:    {user_data.get('primary_id', 'N/A')}")
    lines.append(f"First Name:    {user_data.get('first_name', 'N/A')}")
    lines.append(f"Last Name:     {user_data.get('last_name', 'N/A')}")
    lines.append(f"Full Name:     {user_data.get('full_name', 'N/A')}")
    lines.append(f"User Group:    {user_data.get('user_group', {}).get('desc', 'N/A')}")
    lines.append(f"Status:        {user_data.get('status', {}).get('desc', 'N/A')}")
    lines.append(f"Account Type:  {user_data.get('account_type', {}).get('desc', 'N/A')}")
    lines.append(f"Expiry Date:   {user_data.get('expiry_date', 'N/A')}")

    contact_info = user_data.get("contact_info", {})

    lines.append("")
    lines.append("Email Addresses:")
    emails = contact_info.get("email", [])
    if emails:
        for email in emails:
            preferred = " (preferred)" if email.get("preferred") else ""
            raw = email.get("email_address", "N/A")
            shown = raw if show_raw else _mask_email(raw)
            lines.append(f"  - {shown}{preferred}")
    else:
        lines.append("  (no emails found)")

    lines.append("")
    lines.append("Phone Numbers:")
    phones = contact_info.get("phone", [])
    if phones:
        for phone in phones:
            preferred = " (preferred)" if phone.get("preferred") else ""
            raw = phone.get("phone_number", "N/A")
            shown = raw if show_raw else _mask_phone(raw)
            lines.append(f"  - {shown}{preferred}")
    else:
        lines.append("  (no phones found)")

    lines.append("")
    lines.append("Addresses:")
    addresses = contact_info.get("address", [])
    if addresses:
        for addr in addresses:
            preferred = " (preferred)" if addr.get("preferred") else ""
            country = addr.get("country", {}).get("desc", "")
            if show_raw:
                city = addr.get("city", "")
                lines.append(f"  - {city}, {country}{preferred}")
            else:
                lines.append(f"  - (masked), {country}{preferred}")
    else:
        lines.append("  (no addresses found)")

    if show_raw:
        lines.append("")
        lines.append("-" * 60)
        lines.append("Full JSON Response:")
        lines.append("-" * 60)
        lines.append(json.dumps(user_data, indent=2, ensure_ascii=False))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Retrieve user information from Alma API")
    parser.add_argument("--user-id", default="027393602", help="User ID to retrieve")
    parser.add_argument("--environment", "-e", choices=["SANDBOX", "PRODUCTION"],
                        default="SANDBOX", help="Alma environment")
    parser.add_argument("--show-raw", action="store_true",
                        help="Print full unmasked record incl. raw JSON (PII!)")
    args = parser.parse_args()

    print("=" * 60)
    print("USER RETRIEVAL TEST")
    print("=" * 60)
    print(f"Environment: {args.environment}")
    print(f"User ID: {args.user_id}")
    print("=" * 60)

    client = AlmaAPIClient(args.environment)
    users = Users(client)

    print("\nRetrieving user data...")
    try:
        response = users.get_user(args.user_id)
        user_data = response.data
        print("\n" + "=" * 60)
        print("USER DATA RETRIEVED SUCCESSFULLY")
        print("=" * 60 + "\n")
        print(format_user_report(user_data, show_raw=args.show_raw))
        if not args.show_raw:
            print("\n(contact fields masked; pass --show-raw to print the full record)")
    except Exception as e:
        print(f"\nERROR: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
