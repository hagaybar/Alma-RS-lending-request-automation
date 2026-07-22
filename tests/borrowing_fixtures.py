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
