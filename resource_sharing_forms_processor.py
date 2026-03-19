#!/usr/bin/env python3
"""
Resource Sharing Forms Processor

Processes Microsoft Forms submissions from SharePoint sync to create Alma lending requests
with automatic citation metadata enrichment from PubMed and Crossref.

TSV Format (7 columns, tab-separated):
  0: Partner_Code - Partner institution code
  1: Full_Name - Requester full name (optional)
  2: Requestor_ID - Requester ID/email (optional)
  3: IsFaculty - Faculty status yes/no (optional)
  4: PMID/DOI - Identifier value (auto-detected)
  5: Comments - Optional additional notes
  6: Order_Number - Form order number (required)

The script constructs a structured note, including only non-empty fields:
  Format: "Full_Name, Requestor_ID, IsFaculty ; Comments"
  Example: "David, Levi, User_ID_1234, yes ; message"
  If user fields empty: "message"

External ID format: FORMS-{partner_code}-{DDMMYYYYHHMMSS}-{order_number}
  Example: FORMS-SHEB-07012025143022-Order_Num_24586
  Fallback (no order_number): FORMS-{partner_code}-{DDMMYYYYHHMMSS}

Usage:
    # Dry-run (default - no API calls)
    python resource_sharing_forms_processor.py --config config.json

    # Live processing (single-run)
    python resource_sharing_forms_processor.py --config config.json --live

    # Watch mode (continuous monitoring)
    python resource_sharing_forms_processor.py --config config.json --watch --live

    # Generate sample config
    python resource_sharing_forms_processor.py --generate-config sample_config.json
"""

import argparse
import csv
import json
import logging
import logging.handlers
import os
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from almaapitk import AlmaAPIClient, AlmaAPIError, ResourceSharing, Users, CitationMetadataError


class ProcessingError(Exception):
    """Base exception for processing errors."""
    pass


class IdentifierDetectionError(ProcessingError):
    """Raised when identifier cannot be detected or validated."""
    pass


class MetadataFetchError(ProcessingError):
    """Raised when citation metadata fetch fails."""
    pass


class LendingRequestError(ProcessingError):
    """Raised when lending request creation fails."""
    pass


class FileProcessingError(ProcessingError):
    """Raised when file I/O operations fail."""
    pass


class ResourceSharingFormsProcessor:
    """
    Processes Microsoft Forms submissions to create Alma lending requests.

    Features:
    - Auto-detection of PMID vs DOI identifiers
    - Citation metadata enrichment from PubMed/Crossref
    - Both single-run and continuous watch modes
    - Comprehensive error handling (skip on error, don't fail batch)
    - CSV reporting with detailed results
    """

    def __init__(self, config: Dict[str, Any], dry_run: bool = True, scheduled_mode: bool = False):
        """
        Initialize the forms processor.

        Args:
            config: Configuration dictionary
            dry_run: If True, validate only without API calls
            scheduled_mode: If True, enable Task Scheduler output channels
                           (per-file logs, daily reports, run log heartbeat)
        """
        self.config = config
        self.dry_run = dry_run
        self.scheduled_mode = scheduled_mode
        self.results: List[Dict[str, Any]] = []
        self.processed_files: set = set()

        # Extract configuration
        self.environment = config['alma_settings']['environment']
        self.owner = config['alma_settings']['owner']
        self.format_type = config['alma_settings'].get('format_type', 'DIGITAL')

        self.input_folder = Path(config['file_processing']['input_folder'])
        self.processed_folder = Path(config['file_processing']['processed_folder'])
        self.output_dir = Path(config['file_processing']['output_dir'])

        self.poll_interval = config.get('watch_mode', {}).get('poll_interval', 60)

        # Setup logging
        self.logger = self.setup_logging()

        # Setup dedicated heartbeat logger for folder monitoring
        self.heartbeat_logger = self.setup_heartbeat_logger()

        # Create file_logs directory for scheduled mode
        if self.scheduled_mode:
            file_logs_dir = self.output_dir / 'file_logs'
            file_logs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Alma clients (unless dry-run)
        if not dry_run:
            self.logger.info(f"Initializing Alma API client for {self.environment}")
            self.client = AlmaAPIClient(self.environment)
            self.rs = ResourceSharing(self.client)
            self.users = Users(self.client)

            # Test connection
            try:
                self.client.test_connection()
                self.logger.info("✓ Alma API connection successful")
            except Exception as e:
                self.logger.error(f"✗ Alma API connection failed: {e}")
                raise
        else:
            self.logger.info("[DRY-RUN MODE] Skipping Alma API initialization")
            self.client = None
            self.rs = None
            self.users = None

    def setup_logging(self) -> logging.Logger:
        """
        Configure logging with file and console handlers.

        In scheduled_mode, uses TimedRotatingFileHandler with daily rotation
        and 30-day retention to output/logs/processor.log. In watch mode (the
        default), uses a per-session timestamped file handler.

        Returns:
            Configured logger instance
        """
        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = self.output_dir / 'logs'
        logs_dir.mkdir(exist_ok=True)

        # Configure logger
        logger = logging.getLogger('ResourceSharingFormsProcessor')
        logger.setLevel(logging.DEBUG)

        # Clear any existing handlers to prevent duplicates on re-initialization
        logger.handlers.clear()

        if self.scheduled_mode:
            # Scheduled mode: TimedRotatingFileHandler with daily rotation
            log_file = logs_dir / 'processor.log'
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',
                interval=1,
                backupCount=30,  # Retain 30 days of logs
                encoding='utf-8'
            )
        else:
            # Watch mode: per-session timestamped file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = logs_dir / f'processor_{timestamp}.log'
            file_handler = logging.FileHandler(log_file, encoding='utf-8')

        # File handler (DEBUG level)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)

        # Console handler (INFO level by default)
        console_handler = logging.StreamHandler(sys.stdout)
        console_level = logging.DEBUG if self.config.get('verbose') else logging.INFO
        console_handler.setLevel(console_level)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)

        # Add handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        logger.info(f"Logging initialized - Log file: {log_file}")
        return logger

    def setup_heartbeat_logger(self) -> logging.Logger:
        """
        Configure a dedicated logger for folder monitoring heartbeat events.

        Uses TimedRotatingFileHandler with 10-day retention to keep heartbeat
        logs separate from operational logs. This prevents verbose polling
        messages from cluttering the main log file.

        Returns:
            Configured logger instance for heartbeat events
        """
        # Ensure logs directory exists
        logs_dir = self.output_dir / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)

        heartbeat_log_file = logs_dir / 'heartbeat_checks.log'

        # Configure heartbeat logger
        heartbeat_logger = logging.getLogger('empty_folder_monitor')
        heartbeat_logger.setLevel(logging.DEBUG)

        # Prevent propagation to root logger to avoid duplicate messages
        heartbeat_logger.propagate = False

        # Remove existing handlers to prevent duplicates on re-initialization
        heartbeat_logger.handlers.clear()

        # TimedRotatingFileHandler: rotates at midnight, keeps 10 days of logs
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=heartbeat_log_file,
            when='midnight',
            interval=1,
            backupCount=10,  # Retain 10 days of logs
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        # Format with clear timestamp
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        heartbeat_logger.addHandler(file_handler)

        self.logger.info(f"Heartbeat logger initialized - Log file: {heartbeat_log_file}")
        self.logger.info(f"Heartbeat log retention: 10 days (backupCount={file_handler.backupCount})")

        return heartbeat_logger

    def detect_identifier_type(self, identifier: str) -> Optional[str]:
        """
        Auto-detect identifier type from value (PMID or DOI).

        IGNORES user-provided identifier_type - uses pattern matching instead.

        Detection rules:
        - PMID: Numeric only, 6-9 digits
        - DOI: Starts with "10.", contains "/"

        Args:
            identifier: Identifier value to detect

        Returns:
            'pmid', 'doi', or None if cannot detect
        """
        if not identifier or not identifier.strip():
            return None

        # Clean identifier
        identifier = identifier.strip()

        # Remove common DOI prefixes
        doi_prefixes = ['https://doi.org/', 'http://dx.doi.org/', 'doi:']
        for prefix in doi_prefixes:
            if identifier.lower().startswith(prefix.lower()):
                identifier = identifier[len(prefix):]
                break

        # PMID detection: Numeric only, 6-9 digits
        pmid_pattern = r'^\d{6,9}$'
        if re.match(pmid_pattern, identifier):
            self.logger.debug(f"Detected PMID: {identifier}")
            return 'pmid'

        # DOI detection: Starts with "10.", contains "/"
        doi_pattern = r'^10\.\d+/.*'
        if re.match(doi_pattern, identifier):
            self.logger.debug(f"Detected DOI: {identifier}")
            return 'doi'

        self.logger.warning(f"Could not detect identifier type: {identifier}")
        return None

    def validate_identifier(self, identifier: str, id_type: str) -> bool:
        """
        Validate identifier format after detection.

        Args:
            identifier: Identifier value
            id_type: Detected type ('pmid' or 'doi')

        Returns:
            True if valid, False otherwise
        """
        # Strip whitespace
        identifier = identifier.strip()

        if id_type == 'pmid':
            # Must be numeric, 6-9 digits
            return bool(re.match(r'^\d{6,9}$', identifier))

        elif id_type == 'doi':
            # Strip DOI prefixes (same as detection)
            doi_prefixes = ['https://doi.org/', 'http://dx.doi.org/', 'doi:']
            for prefix in doi_prefixes:
                if identifier.lower().startswith(prefix.lower()):
                    identifier = identifier[len(prefix):]
                    break

            # Must start with "10." and contain "/"
            return bool(re.match(r'^10\.\d+/.*', identifier))

        return False

    # Academic Staff user group code
    ACADEMIC_STAFF_CODE = '04'

    def _lookup_and_verify_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Look up user in Alma and verify Academic Staff membership.

        Args:
            user_id: The user ID to look up

        Returns:
            Dictionary with user info and verification result:
                - full_name: User's full name from Alma
                - user_group_desc: User group description (e.g., 'Academic staff')
                - user_group_value: User group code (e.g., '04')
                - is_academic_staff: True if user_group.value == '04'
            Returns None if lookup fails or in dry_run mode.
        """
        if not user_id or not user_id.strip():
            return None

        if self.dry_run or self.users is None:
            return None

        user_id = user_id.strip()

        try:
            self.logger.debug(f"Looking up user in Alma: {user_id}")
            response = self.users.get_user(user_id)
            user_data = response.data

            # Extract name
            first_name = user_data.get('first_name', '').strip()
            last_name = user_data.get('last_name', '').strip()
            name_parts = [p for p in [first_name, last_name] if p]
            full_name = ' '.join(name_parts) if name_parts else user_id

            # Extract user group
            user_group = user_data.get('user_group', {})
            user_group_value = user_group.get('value', '') if isinstance(user_group, dict) else ''
            user_group_desc = user_group.get('desc', '') if isinstance(user_group, dict) else ''

            # Check Academic Staff
            is_academic_staff = (user_group_value == self.ACADEMIC_STAFF_CODE)

            self.logger.info(
                f"User lookup successful: {user_id} -> {full_name} "
                f"(group: {user_group_desc}, is_academic_staff: {is_academic_staff})"
            )

            return {
                'full_name': full_name,
                'user_group_desc': user_group_desc,
                'user_group_value': user_group_value,
                'is_academic_staff': is_academic_staff
            }

        except AlmaAPIError as e:
            if e.status_code == 404:
                self.logger.warning(f"User not found in Alma: {user_id}")
            else:
                self.logger.warning(f"Alma API error looking up user {user_id}: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"Unexpected error looking up user {user_id}: {e}")
            return None

    def find_pending_tsv_files(self) -> List[Path]:
        """
        Find all pending TSV files in input folder.

        Returns:
            List of Path objects for TSV files
        """
        if not self.input_folder.exists():
            self.logger.warning(f"Input folder does not exist: {self.input_folder}")
            return []

        tsv_files = list(self.input_folder.glob('*.tsv'))

        # Route log message based on whether files were found
        if tsv_files:
            # Operational log: files found, processing will occur
            self.logger.debug(f"Found {len(tsv_files)} TSV files in {self.input_folder}")
        else:
            # Heartbeat log: empty folder check (separate from operational logs)
            self.heartbeat_logger.debug(f"Folder check: 0 TSV files in {self.input_folder}")

        return tsv_files

    def read_tsv_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Read and parse TSV file.

        Expected columns:
        0: partner_code (partner institution code)
        1: user_name (requester name - Full_Name in form, optional)
        2: user_id (requester ID/email - Requestor_ID in form, optional)
        3: is_faculty (faculty status - yes/no, optional)
        4: identifier (PMID or DOI value)
        5: notes (optional additional notes)
        6: order_number (form order number - required)

        Args:
            file_path: Path to TSV file

        Returns:
            Dictionary with form data

        Raises:
            FileProcessingError: If file cannot be read or parsed
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter='\t')
                rows = list(reader)

            if not rows:
                raise FileProcessingError(f"TSV file is empty: {file_path.name}")

            # Filter out empty rows
            non_empty_rows = [row for row in rows if row and any(cell.strip() for cell in row)]

            if not non_empty_rows:
                raise FileProcessingError(f"TSV file contains only empty rows: {file_path.name}")

            # Assume single row (one submission per file)
            row = non_empty_rows[0]

            if len(row) < 5:
                raise FileProcessingError(
                    f"TSV file has insufficient columns (expected 5-7, got {len(row)}): {file_path.name}"
                )

            form_data = {
                'filename': file_path.stem,
                'filepath': file_path,
                'partner_code': row[0].strip(),
                'user_name': row[1].strip() if len(row) > 1 else '',
                'user_id': row[2].strip() if len(row) > 2 else '',
                'is_faculty': row[3].strip().lower() if len(row) > 3 else '',  # Faculty status: yes/no
                'identifier': row[4].strip() if len(row) > 4 else '',
                'notes': row[5].strip() if len(row) > 5 else '',
                'order_number': row[6].strip() if len(row) > 6 else ''
            }

            # Validate IsFaculty field (warning only - accept any value)
            if form_data['is_faculty'] not in ['yes', 'no', '']:
                self.logger.warning(
                    f"Unexpected IsFaculty value: '{form_data['is_faculty']}' "
                    f"(expected 'yes' or 'no') in {file_path.name} - proceeding anyway"
                )

            # Validate Order_Number field (warning if empty)
            if not form_data['order_number']:
                self.logger.warning(
                    f"Order_Number missing in {file_path.name} - will use timestamp fallback for external_id"
                )

            self.logger.debug(f"Parsed TSV file: {file_path.name}")
            self.logger.debug(f"  Partner: {form_data['partner_code']}")
            self.logger.debug(f"  Requester: {form_data['user_name']} ({form_data['user_id']})")
            self.logger.debug(f"  Faculty: {form_data['is_faculty']}")
            self.logger.debug(f"  Identifier: {form_data['identifier']}")
            self.logger.debug(f"  Order Number: {form_data['order_number']}")

            return form_data

        except Exception as e:
            raise FileProcessingError(f"Error reading TSV file {file_path.name}: {e}")

    def move_to_processed(self, file_path: Path) -> None:
        """
        Move file to processed folder with timestamp prefix.

        Args:
            file_path: Path to file to move
        """
        # Ensure processed folder exists
        self.processed_folder.mkdir(parents=True, exist_ok=True)

        # Generate new filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_name = f"{timestamp}_{file_path.name}"
        new_path = self.processed_folder / new_name

        # Move file
        file_path.rename(new_path)
        try:
            relative_path = new_path.relative_to(Path.cwd())
            self.logger.info(f"✓ Moved {file_path.name} → {relative_path}")
        except ValueError:
            self.logger.info(f"✓ Moved {file_path.name} → {new_path}")

    def create_lending_request_from_form(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process form submission into lending request.

        Args:
            form_data: Parsed form data dictionary

        Returns:
            Result dictionary with status, request_id, etc.

        Raises:
            IdentifierDetectionError: If identifier type cannot be detected
            MetadataFetchError: If metadata fetch fails
            LendingRequestError: If request creation fails
        """
        # Extract fields
        partner_code = form_data['partner_code']
        identifier = form_data['identifier']

        # Auto-detect identifier type
        detected_type = self.detect_identifier_type(identifier)
        if not detected_type:
            raise IdentifierDetectionError(
                f"Could not detect identifier type: '{identifier}'. "
                "Expected PMID (6-9 digits) or DOI (10.xxxx/...)."
            )

        # Validate identifier format
        if not self.validate_identifier(identifier, detected_type):
            raise IdentifierDetectionError(
                f"Invalid {detected_type.upper()} format: '{identifier}'"
            )

        # Generate unique external_id with partner code, timestamp, and optional order number
        partner_code = form_data['partner_code']
        timestamp = datetime.now().strftime('%d%m%Y%H%M%S')  # DDMMYYYYHHMMSS (no separators)
        order_number = form_data.get('order_number', '').strip()

        if order_number:
            external_id = f"FORMS-{partner_code}-{timestamp}-{order_number}"
        else:
            # Fallback without order number
            external_id = f"FORMS-{partner_code}-{timestamp}"
            self.logger.warning(f"Order_Number missing, using partner-timestamp format: {external_id}")

        self.logger.info(f"Creating lending request for {detected_type.upper()}: {identifier}")
        self.logger.info(f"  External ID: {external_id}")
        self.logger.info(f"  Partner: {partner_code}")

        # Prepare parameters
        params = {
            'partner_code': partner_code,
            'external_id': external_id,
            'owner': self.owner,
            'format_type': self.format_type,
            'source_type': detected_type  # Explicit: 'pmid' or 'doi'
        }

        # Add identifier
        if detected_type == 'pmid':
            params['pmid'] = identifier
        else:  # doi
            params['doi'] = identifier

        # Build structured note with Academic Staff verification
        note_parts = []
        user_fields = []

        # Try to look up user in Alma and verify Academic Staff status
        user_id = form_data.get('user_id', '').strip()
        alma_user_info = self._lookup_and_verify_user(user_id) if user_id else None

        if alma_user_info:
            # User found in Alma - check Academic Staff status
            if alma_user_info['is_academic_staff']:
                # User IS Academic Staff - include verified info
                user_fields.append(alma_user_info['full_name'])
                user_fields.append('Academic staff')
                user_fields.append(user_id)
            else:
                # User is NOT Academic Staff - include warning with actual group
                user_fields.append(
                    f"User {alma_user_info['full_name']} ({user_id}) is not Academic staff "
                    f"(actual: {alma_user_info['user_group_desc']})"
                )
        elif user_id and not self.dry_run:
            # Lookup was attempted but failed (user not found or API error)
            user_fields.append(f"User id: {user_id} not found in Alma")
            # Include form data if available
            if form_data.get('user_name') and form_data['user_name'].strip():
                user_fields.append(form_data['user_name'].strip())
            if form_data.get('is_faculty') and form_data['is_faculty'].strip():
                user_fields.append(form_data['is_faculty'].strip())
        else:
            # Dry_run mode or no user_id - use form data as-is
            if form_data.get('user_name') and form_data['user_name'].strip():
                user_fields.append(form_data['user_name'].strip())
            if user_id:
                user_fields.append(user_id)
            if form_data.get('is_faculty') and form_data['is_faculty'].strip():
                user_fields.append(form_data['is_faculty'].strip())

        # Add user fields if any present
        if user_fields:
            requester_info = ', '.join(user_fields)
            note_parts.append(requester_info)

        # Add comments if present
        if form_data.get('notes') and form_data['notes'].strip():
            note_parts.append(form_data['notes'].strip())

        # Add order number if present
        if form_data.get('order_number') and form_data['order_number'].strip():
            note_parts.append(form_data['order_number'].strip())

        # Combine with ' ; ' separator or use single part
        if len(note_parts) > 1:
            params['note'] = ' ; '.join(note_parts)
        elif len(note_parts) == 1:
            params['note'] = note_parts[0]
        else:
            # No note at all (valid when no user fields and no comments)
            params['note'] = ''

        self.logger.info(f"  Note: {params['note'][:100]}..." if params.get('note') else "  Note: (empty)")

        # Create request (or dry-run)
        if not self.dry_run:
            try:
                request = self.rs.create_lending_request_from_citation(**params)

                self.logger.info(f"✓ Lending request created successfully")
                self.logger.info(f"  Request ID: {request['request_id']}")
                self.logger.info(f"  Title: {request.get('title', 'N/A')[:60]}")

                return {
                    'status': 'success',
                    'request_id': request['request_id'],
                    'external_id': external_id,
                    'detected_type': detected_type,
                    'title': request.get('title', '')
                }
            except CitationMetadataError as e:
                raise MetadataFetchError(f"Metadata fetch failed: {e}")
            except AlmaAPIError as e:
                raise LendingRequestError(f"API error: {e}")
            except Exception as e:
                raise LendingRequestError(f"Unexpected error: {e}")
        else:
            self.logger.info(f"[DRY-RUN] Would create lending request")
            self.logger.info(f"  Type: {detected_type.upper()}")
            self.logger.info(f"  Identifier: {identifier}")
            self.logger.info(f"  External ID: {external_id}")

            return {
                'status': 'dry_run_success',
                'external_id': external_id,
                'detected_type': detected_type,
                'title': '[DRY-RUN - Not fetched]'
            }

    def process_tsv_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Process a single TSV file.

        Args:
            file_path: Path to TSV file

        Returns:
            Result dictionary with processing status
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"Processing: {file_path.name}")
        self.logger.info(f"{'='*80}")

        result = {
            'timestamp': datetime.now().isoformat(),
            'filename': file_path.name,
            'status': 'unknown',
            'error_message': ''
        }

        try:
            # Read TSV file
            form_data = self.read_tsv_file(file_path)
            result.update({
                'partner_code': form_data['partner_code'],
                'user_name': form_data['user_name'],
                'user_id': form_data['user_id'],
                'is_faculty': form_data['is_faculty'],
                'identifier': form_data['identifier'],
                'order_number': form_data['order_number']
            })

            # Create lending request
            request_result = self.create_lending_request_from_form(form_data)
            result.update(request_result)

            # Move to processed folder
            if result['status'] in ['success', 'dry_run_success']:
                self.move_to_processed(file_path)

        except IdentifierDetectionError as e:
            self.logger.error(f"✗ Identifier detection error: {e}")
            result['status'] = 'skipped'
            result['error_message'] = str(e)

        except MetadataFetchError as e:
            self.logger.error(f"✗ Metadata fetch error: {e}")
            result['status'] = 'error'
            result['error_message'] = str(e)

        except LendingRequestError as e:
            self.logger.error(f"✗ Lending request error: {e}")
            result['status'] = 'error'
            result['error_message'] = str(e)

        except FileProcessingError as e:
            self.logger.error(f"✗ File processing error: {e}")
            result['status'] = 'error'
            result['error_message'] = str(e)

        except Exception as e:
            self.logger.error(f"✗ Unexpected error: {e}", exc_info=True)
            result['status'] = 'error'
            result['error_message'] = f"Unexpected error: {e}"

        self.results.append(result)

        # Scheduled mode: write per-file log and append to daily report
        if self.scheduled_mode:
            self._write_file_processing_log(result)
            self._append_daily_report(result)

        return result

    def _acquire_lock(self) -> bool:
        """
        Acquire a file-based lock to prevent overlapping executions.

        Creates a lock file containing the current PID and timestamp.
        If a lock file already exists, checks whether the owning process
        is still alive. Stale locks (from dead processes) are automatically
        removed.

        Returns:
            True if lock was acquired, False if another instance is running.
        """
        lock_file = self.output_dir / '.processor.lock'

        if lock_file.exists():
            try:
                lock_data = json.loads(lock_file.read_text(encoding='utf-8'))
                existing_pid = lock_data['pid']
            except (json.JSONDecodeError, KeyError, ValueError):
                # Corrupt lock file - treat as stale
                self.logger.info(f"Removing corrupt lock file: {lock_file}")
                lock_file.unlink(missing_ok=True)
            else:
                # Check if the process that owns the lock is still alive
                try:
                    os.kill(existing_pid, 0)
                except OSError:
                    # Process is dead - stale lock
                    self.logger.info(f"Removing stale lock from PID {existing_pid}")
                    lock_file.unlink(missing_ok=True)
                else:
                    # Process is still alive
                    self.logger.warning(
                        f"Another instance is running (PID {existing_pid}), exiting"
                    )
                    return False

        # Create the lock file
        lock_data = {
            "pid": os.getpid(),
            "timestamp": datetime.now().isoformat()
        }
        lock_file.write_text(json.dumps(lock_data), encoding='utf-8')
        self.logger.debug(f"Lock acquired (PID {os.getpid()}): {lock_file}")
        return True

    def _release_lock(self) -> None:
        """
        Release the file-based lock by removing the lock file.

        Handles FileNotFoundError gracefully in case another process
        has already cleaned it up.
        """
        lock_file = self.output_dir / '.processor.lock'
        try:
            lock_file.unlink()
            self.logger.debug(f"Lock released: {lock_file}")
        except FileNotFoundError:
            pass

    def process_single_run(self) -> None:
        """Process all pending TSV files once and exit."""
        if not self._acquire_lock():
            self.logger.info("Exiting due to active lock from another instance")
            return

        run_start = time.time()
        files_found = 0
        files_processed = 0
        run_status = 'success'

        try:
            self.logger.info("\n" + "="*80)
            self.logger.info("RESOURCE SHARING FORMS PROCESSOR - SINGLE-RUN MODE")
            self.logger.info("="*80)

            # Find pending files
            pending_files = self.find_pending_tsv_files()
            files_found = len(pending_files)

            if not pending_files:
                # Heartbeat log: empty folder check in single-run mode
                self.heartbeat_logger.info(f"Single-run check: No TSV files found in {self.input_folder}")
                self.logger.info("No TSV files found in input folder")
                return

            self.logger.info(f"Found {len(pending_files)} TSV file(s) to process")

            # Process each file
            for i, file_path in enumerate(pending_files, 1):
                self.logger.info(f"\n[File {i}/{len(pending_files)}]")
                self.process_tsv_file(file_path)
                files_processed += 1

            # Generate report: in scheduled_mode the daily report replaces
            # the per-invocation CSV; in watch/default mode keep existing behavior
            if not self.scheduled_mode:
                self.generate_csv_report()

            # Display summary
            self.display_summary()

        except Exception as e:
            run_status = 'error'
            raise
        finally:
            duration = time.time() - run_start
            self._write_run_log_entry(files_found, files_processed, run_status, duration)
            self._release_lock()

    def process_watch_mode(self) -> None:
        """Continuous monitoring mode with graceful shutdown."""
        self.logger.info("\n" + "="*80)
        self.logger.info("RESOURCE SHARING FORMS PROCESSOR - WATCH MODE")
        self.logger.info("="*80)
        self.logger.info(f"Monitoring folder: {self.input_folder}")
        self.logger.info(f"Poll interval: {self.poll_interval} seconds")
        self.logger.info("Press Ctrl+C to stop gracefully")

        running = True

        def signal_handler(sig, frame):
            nonlocal running
            self.logger.info("\n\nShutdown signal received, completing current file...")
            running = False

        # Register signal handler
        signal.signal(signal.SIGINT, signal_handler)

        # Continuous monitoring loop
        while running:
            pending_files = self.find_pending_tsv_files()
            new_files = [f for f in pending_files if f.name not in self.processed_files]

            if new_files:
                self.logger.info(f"\n{'='*80}")
                self.logger.info(f"Found {len(new_files)} new file(s)")
                self.logger.info(f"{'='*80}")

                for file_path in new_files:
                    if not running:
                        break

                    self.process_tsv_file(file_path)
                    self.processed_files.add(file_path.name)
            else:
                # Heartbeat log: routine poll with no new files
                self.heartbeat_logger.debug(
                    f"Watch mode poll: No new files in {self.input_folder}, "
                    f"sleeping {self.poll_interval}s"
                )

            # Sleep until next check
            for _ in range(self.poll_interval):
                if not running:
                    break
                time.sleep(1)

        # Final report
        self.logger.info("\n" + "="*80)
        self.logger.info("SHUTDOWN SEQUENCE")
        self.logger.info("="*80)

        if self.results:
            self.generate_csv_report()
            self.display_summary()

        self.logger.info("✓ Shutdown complete")

    def generate_csv_report(self) -> None:
        """Generate CSV report of processing results."""
        if not self.results:
            self.logger.info("No results to report")
            return

        # Ensure reports folder exists
        reports_dir = self.output_dir / 'reports'
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Report file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = reports_dir / f'processing_report_{timestamp}.csv'

        # CSV columns
        fieldnames = [
            'Timestamp', 'Filename', 'Partner_Code', 'Full_Name', 'Requestor_ID',
            'IsFaculty', 'Order_Number', 'Identifier_Type', 'Identifier', 'Status',
            'Request_ID', 'External_ID', 'Title', 'Error_Message'
        ]

        # Write CSV
        with open(report_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in self.results:
                writer.writerow({
                    'Timestamp': result.get('timestamp', ''),
                    'Filename': result.get('filename', ''),
                    'Partner_Code': result.get('partner_code', ''),
                    'Full_Name': result.get('user_name', ''),
                    'Requestor_ID': result.get('user_id', ''),
                    'IsFaculty': result.get('is_faculty', ''),
                    'Order_Number': result.get('order_number', ''),
                    'Identifier_Type': result.get('detected_type', ''),
                    'Identifier': result.get('identifier', ''),
                    'Status': result.get('status', ''),
                    'Request_ID': result.get('request_id', ''),
                    'External_ID': result.get('external_id', ''),
                    'Title': result.get('title', ''),
                    'Error_Message': result.get('error_message', '')
                })

        try:
            relative_path = report_file.relative_to(Path.cwd())
            self.logger.info(f"✓ CSV report generated: {relative_path}")
        except ValueError:
            self.logger.info(f"✓ CSV report generated: {report_file}")

    def display_summary(self) -> None:
        """Display processing summary statistics."""
        if not self.results:
            return

        total = len(self.results)
        successful = sum(1 for r in self.results if r['status'] in ['success', 'dry_run_success'])
        errors = sum(1 for r in self.results if r['status'] == 'error')
        skipped = sum(1 for r in self.results if r['status'] == 'skipped')

        self.logger.info("\n" + "="*80)
        self.logger.info("PROCESSING SUMMARY")
        self.logger.info("="*80)
        self.logger.info(f"Total files processed: {total}")
        self.logger.info(f"  ✓ Successful: {successful}")
        self.logger.info(f"  ✗ Errors: {errors}")
        self.logger.info(f"  ⊗ Skipped: {skipped}")
        self.logger.info("="*80)

    def _write_file_processing_log(self, result: Dict[str, Any]) -> None:
        """
        Write a detailed per-file processing log for scheduled mode.

        Creates one log file per TSV file processed containing every step
        performed: identifier detection, metadata fetch, user lookup,
        lending request creation, and move result.

        Only called in scheduled_mode.

        Args:
            result: The result dictionary from process_tsv_file()
        """
        if not self.scheduled_mode:
            return

        file_logs_dir = self.output_dir / 'file_logs'
        file_logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_name = Path(result.get('filename', 'unknown')).stem
        log_file = file_logs_dir / f'{timestamp}_{original_name}.log'

        lines = []
        lines.append(f"Processing Log for: {result.get('filename', 'unknown')}")
        lines.append(f"Timestamp: {result.get('timestamp', datetime.now().isoformat())}")
        lines.append(f"{'=' * 60}")
        lines.append("")

        # Partner / identifier info
        lines.append(f"Partner Code: {result.get('partner_code', 'N/A')}")
        lines.append(f"Identifier: {result.get('identifier', 'N/A')}")
        lines.append(f"Identifier Type (detected): {result.get('detected_type', 'N/A')}")
        lines.append("")

        # Metadata
        lines.append("[Metadata]")
        lines.append(f"Title: {result.get('title', 'N/A')}")
        lines.append(f"User Name: {result.get('user_name', 'N/A')}")
        lines.append(f"User ID: {result.get('user_id', 'N/A')}")
        lines.append(f"Is Faculty: {result.get('is_faculty', 'N/A')}")
        lines.append(f"Order Number: {result.get('order_number', 'N/A')}")
        lines.append("")

        # Lending request result
        lines.append("[Lending Request]")
        lines.append(f"Status: {result.get('status', 'N/A')}")
        lines.append(f"Request ID: {result.get('request_id', 'N/A')}")
        lines.append(f"External ID: {result.get('external_id', 'N/A')}")
        lines.append("")

        # Error info if any
        if result.get('error_message'):
            lines.append("[Error]")
            lines.append(f"Error Message: {result['error_message']}")
            lines.append("")

        # Move result
        move_status = 'moved' if result.get('status') in ['success', 'dry_run_success'] else 'not moved'
        lines.append(f"[File Move]")
        lines.append(f"Move Result: {move_status}")

        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        self.logger.debug(f"File processing log written: {log_file}")

    def _append_daily_report(self, result: Dict[str, Any]) -> None:
        """
        Append a row to the daily processed CSV report for scheduled mode.

        Creates/appends to: output/reports/processed_{YYYYMMDD}.csv
        If the file does not yet exist today, writes the header row first.

        Only called in scheduled_mode.

        Args:
            result: The result dictionary from process_tsv_file()
        """
        if not self.scheduled_mode:
            return

        reports_dir = self.output_dir / 'reports'
        reports_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime('%Y%m%d')
        report_file = reports_dir / f'processed_{today}.csv'

        fieldnames = [
            'Timestamp', 'Filename', 'Partner_Code', 'Identifier_Type',
            'Identifier', 'Title', 'Status', 'Request_ID', 'External_ID',
            'Error_Message'
        ]

        file_exists = report_file.exists()

        with open(report_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow({
                'Timestamp': result.get('timestamp', ''),
                'Filename': result.get('filename', ''),
                'Partner_Code': result.get('partner_code', ''),
                'Identifier_Type': result.get('detected_type', ''),
                'Identifier': result.get('identifier', ''),
                'Title': result.get('title', ''),
                'Status': result.get('status', ''),
                'Request_ID': result.get('request_id', ''),
                'External_ID': result.get('external_id', ''),
                'Error_Message': result.get('error_message', '')
            })

        self.logger.debug(f"Daily report appended: {report_file}")

    def _write_run_log_entry(self, files_found: int, files_processed: int,
                             status: str, duration: float) -> None:
        """
        Write a single-line heartbeat entry to the daily run log.

        Appends to: output/logs/runs_{YYYYMMDD}.log
        Format: {timestamp} | files_found={N} | files_processed={N} | status={success|error} | duration={N.N}s

        Called at the end of process_single_run() in the finally block,
        even when 0 files are found, to record that the run happened.

        Only called in scheduled_mode.

        Args:
            files_found: Number of TSV files found in input folder
            files_processed: Number of files actually processed
            status: Run status ('success' or 'error')
            duration: Total run duration in seconds
        """
        if not self.scheduled_mode:
            return

        logs_dir = self.output_dir / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime('%Y%m%d')
        run_log_file = logs_dir / f'runs_{today}.log'

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = (
            f"{timestamp} | files_found={files_found} | files_processed={files_processed} "
            f"| status={status} | duration={duration:.1f}s\n"
        )

        with open(run_log_file, 'a', encoding='utf-8') as f:
            f.write(entry)

        self.logger.debug(f"Run log entry written: {run_log_file}")

    def run(self, watch_mode: bool = False) -> bool:
        """
        Run the processor.

        Args:
            watch_mode: If True, run in continuous monitoring mode

        Returns:
            True if successful, False otherwise
        """
        try:
            # Display configuration
            self.display_configuration()

            # Run appropriate mode
            if watch_mode:
                self.process_watch_mode()
            else:
                self.process_single_run()

            return True

        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
            return False

    def display_configuration(self) -> None:
        """Display current configuration."""
        self.logger.info("\n" + "="*80)
        self.logger.info("CONFIGURATION")
        self.logger.info("="*80)
        self.logger.info(f"Environment: {self.environment}")
        self.logger.info(f"Owner: {self.owner}")
        self.logger.info(f"Format Type: {self.format_type}")
        self.logger.info(f"Dry Run: {self.dry_run}")
        self.logger.info(f"Input Folder: {self.input_folder}")
        self.logger.info(f"Processed Folder: {self.processed_folder}")
        self.logger.info(f"Output Folder: {self.output_dir}")
        self.logger.info("="*80 + "\n")


def generate_sample_config(output_path: str) -> None:
    """
    Generate sample configuration file.

    Args:
        output_path: Path to output config file
    """
    sample_config = {
        "description": "Resource Sharing Forms Processor Configuration",

        "alma_settings": {
            "environment": "SANDBOX",
            "owner": "MAIN",
            "format_type": "DIGITAL"
        },

        "file_processing": {
            "input_folder": "./input",
            "processed_folder": "./processed",
            "output_dir": "./output"
        },

        "watch_mode": {
            "poll_interval": 60
        },

        "processing_options": {
            "skip_invalid_identifiers": True,
            "continue_on_metadata_failure": True,
            "continue_on_api_error": True
        },

        "notes": [
            "environment: SANDBOX or PRODUCTION",
            "owner: Resource sharing library code (must be valid in Alma)",
            "format_type: DIGITAL or PHYSICAL (default: DIGITAL)",
            "input_folder: Path to SharePoint sync folder with form submissions",
            "processed_folder: Where completed files are moved",
            "output_dir: Where logs and reports are saved",
            "poll_interval: Seconds between checks in watch mode (default: 60)"
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(sample_config, f, indent=2)

    print(f"✓ Sample configuration generated: {output_path}")
    print("  Edit this file and use with: --config <path>")


def load_config_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary

    Raises:
        SystemExit: If config file invalid or missing required fields
    """
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Validate required sections
        required_sections = ['alma_settings', 'file_processing']
        for section in required_sections:
            if section not in config:
                print(f"ERROR: Missing required section '{section}' in config file")
                sys.exit(1)

        # Validate required fields
        if 'environment' not in config['alma_settings']:
            print("ERROR: Missing 'alma_settings.environment' in config")
            sys.exit(1)

        if 'owner' not in config['alma_settings']:
            print("ERROR: Missing 'alma_settings.owner' in config")
            sys.exit(1)

        if 'input_folder' not in config['file_processing']:
            print("ERROR: Missing 'file_processing.input_folder' in config")
            sys.exit(1)

        return config

    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config file: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Process Microsoft Forms submissions to create Alma lending requests',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run (validate only)
  python resource_sharing_forms_processor.py --config config.json

  # Live processing (single-run)
  python resource_sharing_forms_processor.py --config config.json --live

  # Watch mode (continuous monitoring)
  python resource_sharing_forms_processor.py --config config.json --watch --live

  # Generate sample config
  python resource_sharing_forms_processor.py --generate-config sample_config.json
        """
    )

    # Configuration
    parser.add_argument('--config', help='Path to JSON configuration file')
    parser.add_argument('--generate-config', help='Generate sample config file and exit')

    # Environment overrides
    parser.add_argument('--environment', choices=['SANDBOX', 'PRODUCTION'],
                       help='Alma environment (overrides config)')
    parser.add_argument('--owner', help='Owner library code (overrides config)')
    parser.add_argument('--format-type', choices=['DIGITAL', 'PHYSICAL'],
                       help='Request format (overrides config)')

    # Run modes
    parser.add_argument('--watch', action='store_true',
                       help='Enable continuous monitoring mode')
    parser.add_argument('--poll-interval', type=int, default=60,
                       help='Seconds between checks in watch mode (default: 60)')

    # Safety controls
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Validation only, no API calls (default: True)')
    parser.add_argument('--live', action='store_true',
                       help='Execute live API calls (disables dry-run)')

    # Output controls
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    # Generate sample config
    if args.generate_config:
        generate_sample_config(args.generate_config)
        sys.exit(0)

    # Require config file
    if not args.config:
        parser.error("Either --config or --generate-config is required")

    # Load configuration
    config = load_config_file(args.config)

    # Apply CLI overrides
    if args.environment:
        config['alma_settings']['environment'] = args.environment
    if args.owner:
        config['alma_settings']['owner'] = args.owner
    if args.format_type:
        config['alma_settings']['format_type'] = args.format_type
    if args.poll_interval:
        config['watch_mode']['poll_interval'] = args.poll_interval
    if args.verbose:
        config['verbose'] = True

    # Determine dry-run mode
    dry_run = not args.live

    # Determine scheduled mode: active when NOT in watch mode
    scheduled_mode = not args.watch

    # Initialize and run processor
    try:
        processor = ResourceSharingFormsProcessor(
            config, dry_run=dry_run, scheduled_mode=scheduled_mode
        )
        success = processor.run(watch_mode=args.watch)
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
