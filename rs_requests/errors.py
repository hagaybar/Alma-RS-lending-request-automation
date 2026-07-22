"""Processing-error hierarchy shared by the processor and rs_requests builders.

Defined here — in a module that is never run as a script — so there is
exactly one identity for each class. If they lived in
resource_sharing_forms_processor, running it as a script (__main__, as
production does) while rs_requests imports it by name would create a second
module object and split exception identity, silently breaking the
processor's typed except clauses.
"""


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
