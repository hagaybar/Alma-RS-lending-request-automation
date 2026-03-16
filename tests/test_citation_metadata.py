#!/usr/bin/env python3
"""
Test: Citation Metadata Fetching and Enriched Request Creation

Tests the citation metadata utility and ResourceSharing domain integration:
1. Fetch metadata from PubMed using PMID
2. Fetch metadata from Crossref using DOI
3. Create lending requests enriched with fetched metadata

Test Articles:
- PMID 33219451: "Remdesivir for the Treatment of Covid-19" (Nature Medicine)
- DOI 10.1038/s41591-020-1124-9: Same article (cross-verification)
"""

import argparse
import json
import sys
from pathlib import Path

from almaapitk.utils.citation_metadata import (
    get_pubmed_metadata,
    get_crossref_metadata,
    enrich_citation_metadata,
    CitationMetadataError
)


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


def print_metadata(metadata: dict, source: str):
    """Print formatted metadata."""
    print(f"Source: {source}")
    print(f"Title:        {metadata.get('title', 'N/A')}")
    print(f"Authors:      {metadata.get('author', 'N/A')}")
    print(f"Journal:      {metadata.get('journal', 'N/A')}")
    print(f"Year:         {metadata.get('year', 'N/A')}")
    print(f"Volume:       {metadata.get('volume', 'N/A')}")
    print(f"Issue:        {metadata.get('issue', 'N/A')}")
    print(f"Pages:        {metadata.get('pages', 'N/A')}")
    print(f"DOI:          {metadata.get('doi', 'N/A')}")
    print(f"PMID:         {metadata.get('pmid', 'N/A')}")
    print(f"ISSN:         {metadata.get('issn', 'N/A')}")
    print(f"Publisher:    {metadata.get('publisher', 'N/A')}")

    if metadata.get('abstract'):
        abstract = metadata['abstract']
        print(f"Abstract:     {abstract[:100]}..." if len(abstract) > 100 else f"Abstract:     {abstract}")


def test_pubmed_fetch(pmid: str):
    """Test fetching metadata from PubMed."""
    print_section(f"Test 1: Fetch from PubMed (PMID: {pmid})")

    try:
        metadata = get_pubmed_metadata(pmid)

        print("✅ SUCCESS! Metadata fetched from PubMed")
        print()
        print_metadata(metadata, "PubMed")

        return metadata

    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return None


def test_crossref_fetch(doi: str):
    """Test fetching metadata from Crossref."""
    print_section(f"Test 2: Fetch from Crossref (DOI: {doi})")

    try:
        metadata = get_crossref_metadata(doi)

        print("✅ SUCCESS! Metadata fetched from Crossref")
        print()
        print_metadata(metadata, "Crossref")

        return metadata

    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return None


def test_enrich_metadata(pmid: str = None, doi: str = None, source_type: str = None):
    """Test the enrich_citation_metadata convenience function."""
    mode_desc = f"explicit source_type={source_type}" if source_type else "auto-detect mode"
    print_section(f"Test 3: Enrich Metadata (PMID: {pmid}, DOI: {doi}, {mode_desc})")

    try:
        metadata = enrich_citation_metadata(pmid=pmid, doi=doi, source_type=source_type)

        print(f"✅ SUCCESS! Metadata enriched from {metadata.get('source', 'unknown')}")
        print()
        print_metadata(metadata, metadata.get('source', 'Unknown').upper())

        return metadata

    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return None


def test_enriched_request_creation(pmid: str = None, doi: str = None, source_type: str = None, dry_run: bool = True):
    """Test creating an enriched lending request."""
    mode_desc = f" (source_type={source_type})" if source_type else " (auto-detect)"
    print_section(f"Test 4: Create Enriched Lending Request{mode_desc}")

    if dry_run:
        print("⚠️  DRY RUN MODE - Will fetch metadata but NOT create actual request")
        print()

    from almaapitk import AlmaAPIClient, ResourceSharing
    from datetime import datetime

    # Initialize
    client = AlmaAPIClient('SANDBOX')
    rs = ResourceSharing(client)

    # Generate external ID
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    external_id = f"CITATION-TEST-{timestamp}"

    print(f"External ID:  {external_id}")
    print(f"Partner:      ANC")
    print(f"Owner:        AS1")
    print(f"Format:       DIGITAL")
    print(f"PMID:         {pmid or 'N/A'}")
    print(f"DOI:          {doi or 'N/A'}")
    print(f"Source Type:  {source_type or 'auto-detect'}")
    print()

    if dry_run:
        # Just fetch and show what would be created
        try:
            from almaapitk.utils.citation_metadata import enrich_citation_metadata
            metadata = enrich_citation_metadata(pmid=pmid, doi=doi, source_type=source_type)

            print("Metadata that would be used:")
            print_metadata(metadata, metadata.get('source', 'Unknown').upper())
            print()
            print("✅ Metadata fetch successful - request would be created with this data")

        except Exception as e:
            print(f"❌ FAILED to fetch metadata: {e}")

    else:
        # Actually create the request
        try:
            request = rs.create_lending_request_from_citation(
                partner_code="ANC",
                external_id=external_id,
                owner="AS1",
                format_type="DIGITAL",
                pmid=pmid,
                doi=doi,
                source_type=source_type
            )

            print("✅ SUCCESS! Enriched lending request created!")
            print()
            print(f"Request ID:   {request.get('request_id')}")
            print(f"Title:        {request.get('title', 'N/A')}")
            print(f"Author:       {request.get('author', 'N/A')}")
            print(f"Journal:      {request.get('publisher', 'N/A')}")
            print(f"Year:         {request.get('publication_date', 'N/A')}")
            print(f"Volume:       {request.get('volume', 'N/A')}")
            print(f"Issue:        {request.get('issue', 'N/A')}")
            print(f"Pages:        {request.get('pages', 'N/A')}")
            print(f"DOI:          {request.get('doi', 'N/A')}")
            print(f"PMID:         {request.get('pmid', 'N/A')}")
            print(f"Status:       {request.get('status', {}).get('value', 'N/A')}")

            return request

        except Exception as e:
            print(f"❌ FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None


def compare_sources(pubmed_data: dict, crossref_data: dict):
    """Compare metadata from PubMed and Crossref."""
    print_section("Test 5: Compare PubMed vs Crossref")

    if not pubmed_data or not crossref_data:
        print("⚠️  Skipped - both sources not available")
        return

    fields_to_compare = ['title', 'author', 'journal', 'year', 'volume', 'issue', 'pages', 'doi']

    print("Field Comparison:")
    print("-" * 80)
    for field in fields_to_compare:
        pm_value = pubmed_data.get(field, 'N/A')
        cr_value = crossref_data.get(field, 'N/A')

        match = "✅" if pm_value == cr_value else "⚠️"

        print(f"{field:12s} {match}")
        print(f"  PubMed:   {pm_value}")
        print(f"  Crossref: {cr_value}")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test citation metadata fetching and enriched request creation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with default article (PMID + DOI, auto-detect mode)
  python test_citation_metadata.py

  # Test with custom PMID (explicit source type - recommended)
  python test_citation_metadata.py --pmid 12345678 --source-type pmid

  # Test with custom DOI (explicit source type - recommended)
  python test_citation_metadata.py --doi "10.1038/nature12345" --source-type doi

  # Create actual lending request with explicit DOI source (not dry-run)
  python test_citation_metadata.py --doi "10.4102/ajod.v8i0.490" --source-type doi --live

  # Run specific tests
  python test_citation_metadata.py --test pubmed
  python test_citation_metadata.py --test crossref
  python test_citation_metadata.py --test enrich --source-type doi
  python test_citation_metadata.py --test create --source-type pmid
        """
    )

    parser.add_argument(
        "--pmid",
        default="33219451",
        help="PubMed ID to test (default: 33219451 - Remdesivir COVID-19 article)"
    )

    parser.add_argument(
        "--doi",
        default="10.1038/s41591-020-1124-9",
        help="DOI to test (default: 10.1038/s41591-020-1124-9 - same article)"
    )

    parser.add_argument(
        "--test",
        choices=['pubmed', 'crossref', 'enrich', 'create', 'all'],
        default='all',
        help="Which test to run (default: all)"
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Create actual lending request (default: dry-run)"
    )

    parser.add_argument(
        "--source-type",
        choices=['pmid', 'doi'],
        help="Explicit source type for metadata fetch (pmid or doi). If not specified, uses auto-detect mode."
    )

    args = parser.parse_args()

    print_header("CITATION METADATA TEST")

    print(f"Test PMID:    {args.pmid}")
    print(f"Test DOI:     {args.doi}")
    print(f"Tests:        {args.test}")
    print(f"Mode:         {'LIVE' if args.live else 'DRY-RUN'}")
    print(f"Source Type:  {args.source_type or 'auto-detect'}")

    results = {}

    # Test PubMed
    if args.test in ['pubmed', 'all']:
        results['pubmed'] = test_pubmed_fetch(args.pmid)

    # Test Crossref
    if args.test in ['crossref', 'all']:
        results['crossref'] = test_crossref_fetch(args.doi)

    # Test enrich
    if args.test in ['enrich', 'all']:
        results['enrich'] = test_enrich_metadata(
            pmid=args.pmid,
            doi=args.doi,
            source_type=args.source_type
        )

    # Test enriched request creation
    if args.test in ['create', 'all']:
        results['create'] = test_enriched_request_creation(
            pmid=args.pmid,
            doi=args.doi,
            source_type=args.source_type,
            dry_run=not args.live
        )

    # Compare sources if both available
    if args.test == 'all' and results.get('pubmed') and results.get('crossref'):
        compare_sources(results['pubmed'], results['crossref'])

    # Summary
    print_section("Test Summary")

    success_count = sum(1 for v in results.values() if v is not None)
    total_count = len(results)

    print(f"Tests Run:    {total_count}")
    print(f"Successful:   {success_count}")
    print(f"Failed:       {total_count - success_count}")
    print()

    if success_count == total_count:
        print("✅ All tests passed!")
        return 0
    else:
        print(f"⚠️  {total_count - success_count} test(s) failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
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
