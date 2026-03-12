#!/usr/bin/env python3
"""Smoke test - verifies almaapitk imports work correctly."""
import sys
from pathlib import Path

# Add project root to path for local imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    print("Testing almaapitk imports...")

    try:
        from almaapitk import (
            AlmaAPIClient,
            AlmaAPIError,
            ResourceSharing,
            Users,
            CitationMetadataError,
        )
        print("  AlmaAPIClient: OK")
        print("  AlmaAPIError: OK")
        print("  ResourceSharing: OK")
        print("  Users: OK")
        print("  CitationMetadataError: OK")
    except ImportError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("\nTesting main script import...")
    try:
        from resource_sharing_forms_processor import ResourceSharingFormsProcessor
        print("  ResourceSharingFormsProcessor: OK")
    except ImportError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("\nAll imports OK!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
