#!/usr/bin/env python3
"""
Simple test script to retrieve user information from Alma API.

Usage:
    python test_user_retrieval.py
    python test_user_retrieval.py --user-id 027393602
    python test_user_retrieval.py --environment PRODUCTION
"""

import argparse
import json
import sys
from pathlib import Path

from almaapitk import AlmaAPIClient, Users


def main():
    parser = argparse.ArgumentParser(description="Retrieve user information from Alma API")
    parser.add_argument("--user-id", default="027393602", help="User ID to retrieve")
    parser.add_argument("--environment", "-e", choices=["SANDBOX", "PRODUCTION"],
                        default="SANDBOX", help="Alma environment")
    args = parser.parse_args()

    print("=" * 60)
    print("USER RETRIEVAL TEST")
    print("=" * 60)
    print(f"Environment: {args.environment}")
    print(f"User ID: {args.user_id}")
    print("=" * 60)

    # Initialize client and domain
    client = AlmaAPIClient(args.environment)
    users = Users(client)

    print("\nRetrieving user data...")

    try:
        response = users.get_user(args.user_id)
        user_data = response.data

        print("\n" + "=" * 60)
        print("USER DATA RETRIEVED SUCCESSFULLY")
        print("=" * 60)

        # Display key fields
        print(f"\nPrimary ID:    {user_data.get('primary_id', 'N/A')}")
        print(f"First Name:    {user_data.get('first_name', 'N/A')}")
        print(f"Last Name:     {user_data.get('last_name', 'N/A')}")
        print(f"Full Name:     {user_data.get('full_name', 'N/A')}")
        print(f"User Group:    {user_data.get('user_group', {}).get('desc', 'N/A')}")
        print(f"Status:        {user_data.get('status', {}).get('desc', 'N/A')}")
        print(f"Account Type:  {user_data.get('account_type', {}).get('desc', 'N/A')}")

        # Expiry date
        expiry_date = user_data.get('expiry_date', 'N/A')
        print(f"Expiry Date:   {expiry_date}")

        # Email addresses
        print("\nEmail Addresses:")
        contact_info = user_data.get('contact_info', {})
        emails = contact_info.get('email', [])
        if emails:
            for email in emails:
                preferred = " (preferred)" if email.get('preferred') else ""
                email_type = email.get('email_type', [{}])
                if isinstance(email_type, list):
                    type_desc = email_type[0].get('desc', 'N/A') if email_type else 'N/A'
                else:
                    type_desc = email_type.get('desc', 'N/A')
                print(f"  - {email.get('email_address', 'N/A')} [{type_desc}]{preferred}")
        else:
            print("  (no emails found)")

        # Phone numbers
        print("\nPhone Numbers:")
        phones = contact_info.get('phone', [])
        if phones:
            for phone in phones:
                preferred = " (preferred)" if phone.get('preferred') else ""
                print(f"  - {phone.get('phone_number', 'N/A')}{preferred}")
        else:
            print("  (no phones found)")

        # Addresses
        print("\nAddresses:")
        addresses = contact_info.get('address', [])
        if addresses:
            for addr in addresses:
                preferred = " (preferred)" if addr.get('preferred') else ""
                city = addr.get('city', '')
                country = addr.get('country', {}).get('desc', '')
                print(f"  - {city}, {country}{preferred}")
        else:
            print("  (no addresses found)")

        # Full JSON (optional - commented out to reduce output)
        print("\n" + "-" * 60)
        print("Full JSON Response:")
        print("-" * 60)
        print(json.dumps(user_data, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
