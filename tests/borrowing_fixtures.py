"""Shared fixtures for the borrowing-requests feature branch (GH #22).

file_processing paths here are placeholders — every consumer MUST override them with tmp_path-based paths before constructing a processor (tests must never write into the repo's live input/, processed/ or output/ folders).
"""

CONFIG = {
    "alma_settings": {"environment": "SANDBOX", "owner": "AM1", "format_type": "DIGITAL"},
    "file_processing": {"input_folder": "./input", "processed_folder": "./processed",
                        "output_dir": "./output"},
    "watch_mode": {"poll_interval": 60},
    "processing_options": {"skip_invalid_identifiers": True,
                           "continue_on_metadata_failure": True,
                           "continue_on_api_error": True},
}

# --- canonical borrowing metadata (GH #12) ---------------------------------

META = {
    "title": "A distinctive article title", "author": "Testerson, A.",
    "journal": "Journal of Diagnostics", "year": "2024", "volume": "12",
    "issue": "3", "pages": "101-115", "start_page": "101", "end_page": "115",
    "issn": "0000-0000", "isbn": "", "doi": "10.9999/x", "pmid": "33219451",
    "publisher": "Sandbox Press",
}

FORM = {"requestor": "SHEB", "identifier": "33219451", "notes": "",
        "material_type": "", "order_number": "Order_9", "filename": "r",
        "file_token": "20072026143205"}
