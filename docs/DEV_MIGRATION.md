# Project Extraction Guide: From AlmaAPITK to Standalone Repos

This document describes how to extract a project from `AlmaAPITK/src/projects/` into a standalone GitHub repository that depends on the `almaapitk` package.

## Overview

### Why Extract?

- **Clean dependencies** — Standalone repos depend on `almaapitk` via pip/Poetry, not PYTHONPATH
- **Independent versioning** — Each project can have its own release cycle
- **Easier deployment** — Clone repo, `poetry install`, run
- **Better isolation** — Changes to one project don't affect others

### Extraction Pattern

```
AlmaAPITK/src/projects/MyProject/    →    MyProject-standalone/
├── my_script.py                          ├── my_script.py
├── config/                               ├── config/
│   └── config.example.json               │   └── config.example.json
└── docs/                                 ├── pyproject.toml (NEW)
    └── README.md                         ├── .gitignore (NEW)
                                          ├── README.md (UPDATED)
                                          ├── scripts/smoke_project.py (NEW)
                                          └── tests/test_imports.py (NEW)
```

---

## Prerequisites

### On Development Machine (WSL)

- Python 3.12+
- Poetry installed
- Git configured with GitHub access
- AlmaAPITK repo cloned at `/home/hagaybar/projects/AlmaAPITK`

### On Target Machine (Masedet)

- Python 3.12+
- Poetry installed
- Git configured
- Environment variables: `ALMA_SB_API_KEY`, `ALMA_PROD_API_KEY`

### Before Starting

1. **Create empty GitHub repo** for the new project
2. **Verify source project uses `almaapitk` imports** (not `from src.*`)
3. **Identify all files to extract** (scripts, configs, docs, batch files)

---

## Step-by-Step Extraction Process

### Phase 1: Verify Source Project Imports

Before extraction, ensure the source project uses the public API:

```bash
# Check for forbidden imports
grep -r "from src\." /home/hagaybar/projects/AlmaAPITK/src/projects/MyProject/
grep -r "import src\." /home/hagaybar/projects/AlmaAPITK/src/projects/MyProject/

# Should find NONE. If found, fix them first:
# OLD: from src.client.AlmaAPIClient import AlmaAPIClient
# NEW: from almaapitk import AlmaAPIClient
```

### Phase 2: Create Local Repository

```bash
# Create directory
mkdir -p /home/hagaybar/projects/MyProject-standalone
cd /home/hagaybar/projects/MyProject-standalone

# Initialize git
git init
git remote add origin https://github.com/hagaybar/MyProject-standalone.git
```

### Phase 3: Create .gitignore

Create `.gitignore` with these patterns:

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.eggs/
dist/
build/

# Virtual environments
.venv/
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Secrets and production configs
.env
*.env
config/*_prod*.json
config/*_sandbox*.json
config/test_config.json

# Data files (user data, never commit)
input/*.tsv
processed/*.tsv
*.tsv

# Output (logs and reports, never commit)
output/logs/*.log
output/reports/*.csv
*.log

# Keep directory structure
!input/.gitkeep
!processed/.gitkeep
!output/.gitkeep
!output/logs/.gitkeep
!output/reports/.gitkeep

# OS
.DS_Store
Thumbs.db

# Testing
.pytest_cache/
.coverage
htmlcov/
```

### Phase 4: Create pyproject.toml

```toml
[tool.poetry]
name = "my-project-standalone"
version = "1.0.0"
description = "Description of what this project does"
authors = ["Hagay Bar-Or <hagaybar@tauex.tau.ac.il>"]
readme = "README.md"
package-mode = false

[tool.poetry.dependencies]
python = "^3.12"
# Pin to specific release tag
almaapitk = { git = "https://github.com/hagaybar/AlmaAPITK.git", tag = "v0.2.2" }

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**Important:** Always pin to a release tag (e.g., `v0.2.2`), not a branch.

### Phase 5: Copy Files

```bash
SOURCE=/home/hagaybar/projects/AlmaAPITK/src/projects/MyProject
TARGET=/home/hagaybar/projects/MyProject-standalone

# Copy Python scripts
cp $SOURCE/*.py $TARGET/

# Create directories
mkdir -p $TARGET/config $TARGET/docs $TARGET/batch
mkdir -p $TARGET/input $TARGET/output/logs $TARGET/output/reports $TARGET/processed

# Copy config EXAMPLES only (not production configs)
cp $SOURCE/config/*.example.json $TARGET/config/

# Copy documentation
cp $SOURCE/docs/*.md $TARGET/docs/

# Copy batch files (if any)
cp $SOURCE/batch/*.bat $TARGET/batch/ 2>/dev/null || true

# Create .gitkeep files
touch $TARGET/input/.gitkeep
touch $TARGET/output/.gitkeep
touch $TARGET/output/logs/.gitkeep
touch $TARGET/output/reports/.gitkeep
touch $TARGET/processed/.gitkeep
```

**DO NOT copy:**
- `config/*_prod*.json` (production configs)
- `config/*_sandbox*.json` (sandbox configs with real paths)
- `config/test_config.json` (test configs with user paths)
- `__pycache__/`

### Phase 6: Create Smoke Test

Create `scripts/smoke_project.py`:

```python
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
            # Add other imports your project uses
        )
        print("  AlmaAPIClient: OK")
        print("  AlmaAPIError: OK")
    except ImportError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("\nTesting main script import...")
    try:
        from my_script import MyMainClass  # Adjust to your main class
        print("  MyMainClass: OK")
    except ImportError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("\nAll imports OK!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Phase 7: Create Unit Test

Create `tests/__init__.py` (empty) and `tests/test_imports.py`:

```python
"""Test that all imports use almaapitk public API only."""
import unittest
import re
from pathlib import Path

class TestImports(unittest.TestCase):
    """Verify import hygiene."""

    def test_almaapitk_imports(self):
        """Verify almaapitk public API imports work."""
        from almaapitk import AlmaAPIClient, AlmaAPIError
        self.assertIsNotNone(AlmaAPIClient)

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
```

### Phase 8: Update README

Move `docs/README.md` to root `README.md` and update:

1. **Remove PYTHONPATH references** — Replace with `poetry run python`
2. **Update Installation section:**
   ```markdown
   ## Installation

   ```bash
   git clone https://github.com/hagaybar/MyProject-standalone.git
   cd MyProject-standalone
   poetry install
   ```
   ```

3. **Update Usage examples:**
   ```markdown
   ## Usage

   ```bash
   # Dry-run (safe, no API calls)
   poetry run python my_script.py --config config/my_config.json

   # Live mode
   poetry run python my_script.py --config config/my_config.json --live
   ```
   ```

4. **Add Testing section:**
   ```markdown
   ## Testing

   ```bash
   poetry run python scripts/smoke_project.py
   poetry run python -m pytest tests/ -v
   ```
   ```

### Phase 9: Update Batch Files

If your project has Windows batch files, update them:

**Before:**
```batch
cd /d D:\Scripts\Prod\AlmaAPITK
set PYTHONPATH=D:\Scripts\Prod\AlmaAPITK
poetry run python src\projects\MyProject\my_script.py --config ...
```

**After:**
```batch
cd /d D:\Scripts\DevSandbox\MyProject-standalone
poetry run python my_script.py --config config\my_config.json --live
```

### Phase 10: Local Validation

```bash
cd /home/hagaybar/projects/MyProject-standalone

# Install dependencies
poetry install

# Run smoke test
poetry run python scripts/smoke_project.py

# Run unit tests
poetry run python -m pytest tests/ -v
```

All tests must pass before proceeding.

### Phase 11: Commit and Push

```bash
git add .
git status  # Review what will be committed

git commit -m "$(cat <<'EOF'
Initial commit: Extract MyProject from AlmaAPITK

- Brief description of what the project does
- Key features
- Depends on almaapitk vX.Y.Z

Extracted from: https://github.com/hagaybar/AlmaAPITK

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"

git push -u origin main
```

---

## Testing on Masedet (Production Machine)

### Safe Testing Sequence

1. **Clone to DevSandbox (not Prod)**
   ```powershell
   cd D:\Scripts\DevSandbox
   git clone https://github.com/hagaybar/MyProject-standalone.git
   cd MyProject-standalone
   poetry install
   ```

2. **Create SANDBOX config**
   ```powershell
   copy config\my_config.example.json config\my_config_sandbox.json
   # Edit to use SANDBOX environment and local paths
   ```

3. **Test sequence**
   ```powershell
   # Verify imports
   poetry run python scripts/smoke_project.py

   # Dry-run
   poetry run python my_script.py --config config\my_config_sandbox.json

   # Live against SANDBOX
   poetry run python my_script.py --config config\my_config_sandbox.json --live
   ```

4. **Only after success:** Consider adding to auto-deploy

---

## Checklist

### Before Extraction
- [ ] Source project uses `from almaapitk import ...` (no `from src.*`)
- [ ] Empty GitHub repo created
- [ ] Identified all files to copy

### During Extraction
- [ ] .gitignore created
- [ ] pyproject.toml created with pinned almaapitk version
- [ ] Python scripts copied
- [ ] Config EXAMPLES copied (not production configs)
- [ ] Documentation copied and updated
- [ ] Batch files updated (removed PYTHONPATH)
- [ ] Smoke test created
- [ ] Unit tests created
- [ ] README updated for standalone usage

### Validation
- [ ] `poetry install` succeeds
- [ ] `poetry run python scripts/smoke_project.py` passes
- [ ] `poetry run python -m pytest tests/ -v` passes
- [ ] No forbidden imports found

### Deployment
- [ ] Pushed to GitHub
- [ ] Cloned on Masedet DevSandbox
- [ ] Tested with SANDBOX environment
- [ ] Tested with dry-run mode
- [ ] Tested with live mode against SANDBOX
- [ ] (Optional) Added to auto-deploy

---

## Completed Extractions

| Project | Source | Standalone Repo | almaapitk Version |
|---------|--------|-----------------|-------------------|
| Update Expired Users Emails | `src/projects/update_expired_users_emails/` | [Alma-update-expired-users-emails](https://github.com/hagaybar/Alma-update-expired-users-emails) | v0.2.2 |
| Resource Sharing Forms | `src/projects/ResourceSharing/` | [Alma-RS-lending-request-automation](https://github.com/hagaybar/Alma-RS-lending-request-automation) | v0.2.2 |

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'almaapitk'"

**Cause:** Dependencies not installed.
**Solution:** Run `poetry install`

### "ModuleNotFoundError: No module named 'src'"

**Cause:** Script still has legacy imports.
**Solution:** Update imports to use `from almaapitk import ...`

### Poetry install fails with git dependency

**Cause:** Tag doesn't exist or network issue.
**Solution:**
- Verify tag exists: `git ls-remote --tags https://github.com/hagaybar/AlmaAPITK.git`
- Check network connectivity

### Tests pass locally but fail on Masedet

**Cause:** Different Python version or missing env vars.
**Solution:**
- Verify Python version: `python --version`
- Verify env vars: `echo %ALMA_SB_API_KEY%`

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-12 | 1.0 | Initial version based on ResourceSharing extraction |
