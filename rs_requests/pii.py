"""PII masking helpers shared by the processor and rs_requests builders.

Import-free — see rs_requests/errors.py for why shared code must not live in
the processor.
"""
import re
from typing import Optional


def mask_lcc_number(value: Optional[str]) -> str:
    """Mask the patron-name tail of an lcc_number, keeping its structure.

    The observed conventions are '<HOSP>-TAU-<n> <patron name>',
    '<HOSP><n>; <n>' and '<HOSP><n>'. Only the first carries a name, as the
    segment following the first space after a digit run.

    order_number is optional in the borrowing flow, so the third segment can
    render empty (e.g. 'SHEB-TAU- Some Patron'); that case is masked too, not
    returned raw.

    The prefix assumes a single-token (unhyphenated) hospital code —
    currently guaranteed by allowed_hospitals in the borrowing config.
    """
    if not value:
        return ""
    # The prefix segment is NOT digits-only: this repo's order numbers look
    # like 'Order_Num_24586' (GH #16), so the rendered template can be
    # 'SHEB-TAU-Order_9 <patron name>'. Match any word-ish final segment
    # (which may be empty — order_number is optional).
    match = re.match(r"^([A-Za-z]+-[A-Za-z]+-[A-Za-z0-9_]*)\s+\S.*$",
                     value.strip())
    if match:
        return f"{match.group(1)} ***"
    return value.strip()
