"""Lending request builder — behaviour moved unchanged from the processor."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from almaapitk import AlmaAPIError
from almaapitk.utils.citation_metadata import CitationMetadataError

# Cycle-safe: the processor never imports rs_requests at module level (every
# get_builder import is deferred into a method body), so importing its
# exception types here cannot create a circular import.
from resource_sharing_forms_processor import (
    IdentifierDetectionError,
    LendingRequestError,
    MetadataFetchError,
)

from rs_requests.base import BuiltRequest, RequestBuilder


class LendingRequestBuilder(RequestBuilder):
    kind = "lending"
    needs_metadata = False   # the toolkit enriches inside its own call

    def build(self, form_data: Dict[str, Any],
              metadata: Optional[Dict[str, Any]] = None) -> BuiltRequest:
        # Extract fields
        partner_code = form_data['partner_code']
        identifier = form_data['identifier']

        # Auto-detect identifier type
        detected_type = self.processor.detect_identifier_type(identifier)
        if not detected_type:
            raise IdentifierDetectionError(
                f"Could not detect identifier type: '{identifier}'. "
                "Expected PMID (6-9 digits) or DOI (10.xxxx/...)."
            )

        # Validate identifier format
        if not self.processor.validate_identifier(identifier, detected_type):
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
            self.processor.logger.warning(f"Order_Number missing, using partner-timestamp format: {external_id}")

        self.processor.logger.info(f"Creating lending request for {detected_type.upper()}: {identifier}")
        self.processor.logger.info(f"  External ID: {external_id}")
        self.processor.logger.info(f"  Partner: {partner_code}")

        # Prepare parameters
        params = {
            'partner_code': partner_code,
            'external_id': external_id,
            'owner': self.processor.owner,
            'format_type': self.processor.format_type,
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
        alma_user_info = self.processor._lookup_and_verify_user(user_id) if user_id else None

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
        elif user_id and not self.processor.dry_run:
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

        if params.get('note'):
            self.processor._log_pii(
                logging.INFO,
                f"  Note: {params['note'][:100]}...",
                "  Note: (recorded — see file log)",
            )
        else:
            self.processor.logger.info("  Note: (empty)")

        return BuiltRequest(
            kind=self.kind,
            external_id=external_id,
            payload=params,
            summary={
                'detected_type': detected_type,
                # Preserves the pre-refactor dry-run result dict (and the
                # CSV Title column) byte for byte; the live path overrides
                # this with the real title in submit()'s return.
                'title': '[DRY-RUN - Not fetched]',
            },
        )

    def submit(self, built: BuiltRequest) -> Dict[str, Any]:
        params = built.payload
        try:
            request = self.processor.rs.create_lending_request_from_citation(**params)

            self.processor.logger.info(f"✓ Lending request created successfully")
            self.processor.logger.info(f"  Request ID: {request['request_id']}")
            self.processor.logger.info(f"  Title: {request.get('title', 'N/A')[:60]}")

            return {
                'status': 'success',
                'request_id': request['request_id'],
                'external_id': built.external_id,
                'detected_type': built.summary['detected_type'],
                'title': request.get('title', '')
            }
        except CitationMetadataError as e:
            raise MetadataFetchError(f"Metadata fetch failed: {e}")
        except AlmaAPIError as e:
            raise LendingRequestError(f"API error: {e}")
        except Exception as e:
            raise LendingRequestError(f"Unexpected error: {e}")
