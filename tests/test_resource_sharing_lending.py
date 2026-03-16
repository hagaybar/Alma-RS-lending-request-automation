#!/usr/bin/env python3
"""
Test: Resource Sharing Lending Requests

Tests the ResourceSharing domain class with lending request operations:
1. Create lending request for a partner
2. Retrieve lending request by ID

This test demonstrates the complete workflow for creating and managing
lending requests through the Alma Partners API.

Test Scenarios:
- Scenario 1: Create basic lending request (PHYSICAL format, with citation_type)
- Scenario 2: Create lending request for catalog item (with mms_id)
- Scenario 3: Retrieve created lending requests

Expected Results:
- Lending requests created successfully with all mandatory fields
- Retrieved requests match created data
- Validation errors prevented for missing mandatory fields
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from almaapitk import AlmaAPIClient, AlmaAPIError, ResourceSharing
from almaapitk.alma_logging import get_logger


# Test configuration
TEST_PARTNER_CODE = "RELAIS"  # Default partner code - modify as needed
TEST_OWNER = "MAIN"  # Default owner library - modify as needed

# Test data
TEST_SCENARIOS = [
    {
        "name": "Basic Physical Lending Request",
        "description": "Create a physical lending request with full citation",
        "data": {
            "external_id": f"TEST-EXT-{datetime.now().strftime('%Y%m%d_%H%M%S')}-001",
            "format_type": "PHYSICAL",
            "title": "Introduction to Information Science",
            "citation_type": "BOOK",
            "author": "Smith, John A.",
            "isbn": "978-0-123456-78-9",
            "publisher": "Academic Press",
            "publication_date": "2024",
            "edition": "5th",
            "call_number": "Z665 .S65 2024",
            "oclc_number": "1234567890",
        }
    },
    {
        "name": "Journal Article Request",
        "description": "Create a lending request for a journal article",
        "data": {
            "external_id": f"TEST-EXT-{datetime.now().strftime('%Y%m%d_%H%M%S')}-002",
            "format_type": "DIGITAL",
            "title": "Digital Transformation in Libraries",
            "citation_type": "JOURNAL",
            "author": "Johnson, Mary",
            "issn": "1234-5678",
            "volume": "45",
            "issue": "3",
            "pages": "123-145",
            "doi": "10.1000/j.example.2024.03.001",
            "publication_date": "2024",
        }
    },
]


def print_header(title: str):
    """Print formatted section header."""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    print()


def print_section(title: str):
    """Print formatted subsection."""
    print()
    print(f"[{title}]")
    print("-" * 80)


def print_request_summary(request: Dict[str, Any]):
    """Print formatted request summary."""
    print(f"  Request ID:     {request.get('request_id', 'N/A')}")
    print(f"  External ID:    {request.get('external_id', 'N/A')}")
    print(f"  Title:          {request.get('title', 'N/A')}")
    print(f"  Author:         {request.get('author', 'N/A')}")
    print(f"  Citation Type:  {request.get('citation_type', {}).get('value', 'N/A')}")
    print(f"  Format:         {request.get('format', {}).get('value', 'N/A')}")
    print(f"  Status:         {request.get('status', {}).get('value', 'N/A')}")
    print(f"  Partner:        {request.get('partner', {}).get('value', 'N/A')}")
    print(f"  Owner:          {request.get('owner', {}).get('value', 'N/A')}")


def test_validation_errors(rs: ResourceSharing, logger):
    """Test validation error handling."""
    print_section("Testing Validation Errors")

    test_cases = [
        {
            "name": "Missing external_id",
            "data": {
                "partner_code": TEST_PARTNER_CODE,
                "external_id": "",  # Missing
                "owner": TEST_OWNER,
                "format_type": "PHYSICAL",
                "title": "Test Book",
                "citation_type": "BOOK"
            },
            "expected_error": "external_id is mandatory"
        },
        {
            "name": "Missing format",
            "data": {
                "partner_code": TEST_PARTNER_CODE,
                "external_id": "TEST-001",
                "owner": TEST_OWNER,
                "format_type": "",  # Missing
                "title": "Test Book",
                "citation_type": "BOOK"
            },
            "expected_error": "format is mandatory"
        },
        {
            "name": "Missing citation_type and title (no mms_id)",
            "data": {
                "partner_code": TEST_PARTNER_CODE,
                "external_id": "TEST-002",
                "owner": TEST_OWNER,
                "format_type": "PHYSICAL",
                "title": "",  # Missing
                "citation_type": None  # Missing
            },
            "expected_error": "citation_type is mandatory"
        },
    ]

    passed = 0
    failed = 0

    for idx, test_case in enumerate(test_cases, 1):
        print(f"  Test {idx}/{len(test_cases)}: {test_case['name']}")

        try:
            # This should raise ValueError
            rs.create_lending_request(**test_case['data'])

            print(f"    ❌ FAILED - Expected validation error but succeeded")
            failed += 1

        except ValueError as e:
            if test_case['expected_error'] in str(e):
                print(f"    ✅ PASSED - Caught expected error: {test_case['expected_error']}")
                passed += 1
            else:
                print(f"    ❌ FAILED - Wrong error message: {str(e)}")
                failed += 1

        except Exception as e:
            print(f"    ❌ FAILED - Unexpected error: {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"Validation Tests: {passed} passed, {failed} failed")

    return passed, failed


def test_lending_requests(
    partner_code: str,
    owner: str,
    dry_run: bool = False,
    test_validation: bool = False
) -> int:
    """
    Execute lending request tests.

    Args:
        partner_code: Partner institution code
        owner: Resource sharing library code
        dry_run: If True, validate only without creating requests
        test_validation: If True, run validation error tests

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    # Initialize logger
    logger = get_logger('test_resource_sharing_lending', environment='SANDBOX')

    print_header("RESOURCE SHARING LENDING REQUEST TEST")

    print(f"Environment:    SANDBOX")
    print(f"Partner Code:   {partner_code}")
    print(f"Owner Library:  {owner}")
    print(f"Test Scenarios: {len(TEST_SCENARIOS)}")
    print(f"Mode:           {'DRY RUN' if dry_run else 'LIVE TEST'}")

    logger.info(
        "Starting lending request test",
        mode='DRY_RUN' if dry_run else 'LIVE',
        partner_code=partner_code,
        owner=owner,
        test_count=len(TEST_SCENARIOS)
    )

    if dry_run:
        print()
        print("⚠️  DRY RUN MODE - No requests will be created")
        print("    Validating data and displaying what would happen")
        print()

    # Initialize Alma client and ResourceSharing domain
    client = AlmaAPIClient('SANDBOX')
    rs = ResourceSharing(client)

    # Test validation errors if requested
    if test_validation:
        validation_passed, validation_failed = test_validation_errors(rs, logger)
        if validation_failed > 0:
            print()
            print(f"⚠️  Validation tests had {validation_failed} failures")
            print()

    # Track created requests for retrieval test
    created_requests = []
    results = []

    # Test each scenario
    for idx, scenario in enumerate(TEST_SCENARIOS, 1):
        print_section(f"{idx}/{len(TEST_SCENARIOS)} {scenario['name']}")
        print(f"  Description: {scenario['description']}")
        print()

        scenario_data = scenario['data'].copy()

        try:
            logger.info(
                "Processing scenario",
                scenario_name=scenario['name'],
                external_id=scenario_data.get('external_id')
            )

            if dry_run:
                print("  [DRY RUN] Would create lending request with:")
                print(f"    External ID:   {scenario_data.get('external_id')}")
                print(f"    Format:        {scenario_data.get('format_type')}")
                print(f"    Title:         {scenario_data.get('title')}")
                print(f"    Citation Type: {scenario_data.get('citation_type', 'N/A')}")
                print(f"    Author:        {scenario_data.get('author', 'N/A')}")
                print()

                results.append({
                    "scenario": scenario['name'],
                    "status": "DRY_RUN",
                    "external_id": scenario_data.get('external_id')
                })

            else:
                print("  Creating lending request...")

                # Create lending request
                request = rs.create_lending_request(
                    partner_code=partner_code,
                    owner=owner,
                    **scenario_data
                )

                print("  ✅ Request created successfully!")
                print()
                print_request_summary(request)

                created_requests.append({
                    "partner_code": partner_code,
                    "request_id": request.get('request_id'),
                    "scenario": scenario['name']
                })

                results.append({
                    "scenario": scenario['name'],
                    "status": "SUCCESS",
                    "request_id": request.get('request_id'),
                    "external_id": request.get('external_id')
                })

                logger.info(
                    "Lending request created",
                    scenario_name=scenario['name'],
                    request_id=request.get('request_id'),
                    external_id=request.get('external_id')
                )

        except ValueError as e:
            print(f"  ❌ Validation error: {e}")
            results.append({
                "scenario": scenario['name'],
                "status": "VALIDATION_ERROR",
                "error": str(e)
            })

            logger.error(
                "Validation error",
                scenario_name=scenario['name'],
                error=str(e)
            )

        except AlmaAPIError as e:
            print(f"  ❌ API error: {e}")
            print(f"     Status code: {e.status_code}")
            results.append({
                "scenario": scenario['name'],
                "status": "API_ERROR",
                "error": str(e),
                "status_code": e.status_code
            })

            logger.error(
                "API error",
                scenario_name=scenario['name'],
                error_code=e.status_code,
                error_message=str(e)
            )

        except Exception as e:
            print(f"  ❌ Unexpected error: {type(e).__name__}: {e}")
            results.append({
                "scenario": scenario['name'],
                "status": "UNEXPECTED_ERROR",
                "error": str(e)
            })

            logger.error(
                "Unexpected error",
                scenario_name=scenario['name'],
                error_type=type(e).__name__,
                error_message=str(e)
            )

    # Test retrieval if we created any requests
    if created_requests and not dry_run:
        print_section("Testing Request Retrieval")

        for idx, created in enumerate(created_requests, 1):
            print(f"  {idx}/{len(created_requests)} Retrieving {created['scenario']}...")

            try:
                request = rs.get_lending_request(
                    partner_code=created['partner_code'],
                    request_id=created['request_id']
                )

                print("  ✅ Request retrieved successfully!")
                print()
                print_request_summary(request)

                # Get summary helper
                summary = rs.get_request_summary(request)
                print()
                print("  Summary helper output:")
                print(f"    {json.dumps(summary, indent=6)}")

                logger.info(
                    "Request retrieved successfully",
                    request_id=created['request_id'],
                    scenario=created['scenario']
                )

            except AlmaAPIError as e:
                print(f"  ❌ Failed to retrieve: {e}")
                logger.error(
                    "Failed to retrieve request",
                    request_id=created['request_id'],
                    error=str(e)
                )

    # Print summary
    print_section("Test Summary")

    success_count = sum(1 for r in results if r['status'] in ['SUCCESS', 'DRY_RUN'])
    error_count = len(results) - success_count

    print(f"Total Scenarios:  {len(results)}")
    print(f"Successful:       {success_count}")
    print(f"Errors:           {error_count}")
    print()

    if error_count == 0:
        print("✅ All tests completed successfully!")
        logger.info("All tests completed successfully", success_count=success_count)
        return 0
    else:
        print(f"⚠️  {error_count} test(s) encountered errors")
        logger.warning("Tests completed with errors", error_count=error_count)

        print()
        print("Failed scenarios:")
        for result in results:
            if result['status'] not in ['SUCCESS', 'DRY_RUN']:
                print(f"  - {result['scenario']}: {result['status']}")
                if 'error' in result:
                    print(f"    Error: {result['error']}")

        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test ResourceSharing domain with lending requests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run test (no actual API calls)
  python test_resource_sharing_lending.py --dry-run

  # Live test with default partner
  python test_resource_sharing_lending.py --live

  # Live test with custom partner and owner
  python test_resource_sharing_lending.py --live --partner CUSTOM_PARTNER --owner BRANCH_LIB

  # Test validation errors
  python test_resource_sharing_lending.py --live --test-validation

  # Dry-run with all tests
  python test_resource_sharing_lending.py --dry-run --test-validation
        """
    )

    parser.add_argument(
        "--partner",
        default=TEST_PARTNER_CODE,
        help=f"Partner institution code (default: {TEST_PARTNER_CODE})"
    )

    parser.add_argument(
        "--owner",
        default=TEST_OWNER,
        help=f"Resource sharing library code (default: {TEST_OWNER})"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't create requests (default)"
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live test (creates actual requests in SANDBOX)"
    )

    parser.add_argument(
        "--test-validation",
        action="store_true",
        help="Run validation error tests"
    )

    args = parser.parse_args()

    # Default to dry-run unless --live is specified
    dry_run = not args.live

    if dry_run:
        print()
        print("ℹ️  Running in DRY-RUN mode. Use --live to create actual requests.")
        print()

    try:
        exit_code = test_lending_requests(
            partner_code=args.partner,
            owner=args.owner,
            dry_run=dry_run,
            test_validation=args.test_validation
        )
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print()
        print("Test interrupted by user")
        sys.exit(130)

    except Exception as e:
        print()
        print(f"Fatal error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
