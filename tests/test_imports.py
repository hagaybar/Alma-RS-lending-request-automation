"""Test that all imports use almaapitk public API only."""
import unittest
import re
from pathlib import Path

class TestImports(unittest.TestCase):
    """Verify import hygiene."""

    def test_almaapitk_imports(self):
        """Verify almaapitk public API imports work."""
        from almaapitk import (
            AlmaAPIClient,
            AlmaAPIError,
            ResourceSharing,
            Users,
            CitationMetadataError,
        )
        self.assertIsNotNone(AlmaAPIClient)
        self.assertIsNotNone(ResourceSharing)

    def test_no_legacy_imports(self):
        """Ensure no forbidden legacy imports exist."""
        forbidden_patterns = [
            r"from\s+src\.",
            r"import\s+src\.",
            r"from\s+client\.",
            r"from\s+domains\.",
            r"from\s+utils\.",
        ]

        project_root = Path(__file__).parent.parent
        python_files = list(project_root.glob("*.py"))

        for py_file in python_files:
            content = py_file.read_text()
            for pattern in forbidden_patterns:
                matches = re.findall(pattern, content)
                self.assertEqual(
                    len(matches), 0,
                    f"Found forbidden import {pattern!r} in {py_file.name}"
                )

if __name__ == "__main__":
    unittest.main()
