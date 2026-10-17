"""State of the prompt cache, from the last API calls in the transcript."""
from typing import Optional, Tuple

from .transcript import tail_lines, usage_record

TTL_SECONDS = {"5m": 300, "1h": 3600}


def cache_status(transcript: str, lines: int = 400) -> Optional[Tuple[str, float]]:
    """(tier, expiry as a Unix timestamp) of the last cache write, or None when none is found.

    The tier is the one of the last write. Each read refreshes the entry for its own tier,
    so the expiry is the last cache touch plus that tier's TTL.
    """
    last_touch = None
    last_write = None
    for line in tail_lines(transcript, lines):
        if '"cache_creation"' not in line:
            continue
        rec = usage_record(line)
        if rec is None:
            continue
        cache_creation = rec["usage"].get("cache_creation")
        if not cache_creation:
            continue
        last_touch = rec["time"]
        write_1h = cache_creation.get("ephemeral_1h_input_tokens", 0) or 0
        write_5m = cache_creation.get("ephemeral_5m_input_tokens", 0) or 0
        if write_1h or write_5m:
            last_write = "1h" if write_1h else "5m"
    if last_touch is None or last_write is None:
        return None
    return last_write, last_touch.timestamp() + TTL_SECONDS[last_write]
