"""Reading Claude Code transcripts (JSONL) without loading big files whole."""
import datetime
import json
import os
from typing import Any, Dict, List, Optional


def parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def tail_lines(path: str, count: int, max_bytes: int = 4_000_000) -> List[str]:
    """The last `count` lines of a file, reading at most `max_bytes` from its end."""
    chunk = 256_000
    with open(path, "rb") as fh:
        start = size = fh.seek(0, os.SEEK_END)
        data = b""
        # read backwards until there are enough lines, so short tails stay cheap
        while start > 0 and size - start < max_bytes and data.count(b"\n") <= count:
            step = min(chunk, start, max_bytes - (size - start))
            start -= step
            fh.seek(start)
            data = fh.read(step) + data
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # the first line may be cut in the middle
    return lines[-count:]


def usage_record(line: str) -> Optional[Dict[str, Any]]:
    """Assistant record with API usage -> {key, time, model, usage}; None for anything else."""
    if '"usage"' not in line:
        return None
    try:
        rec = json.loads(line)
        msg = rec["message"]
        usage = msg.get("usage")
        if not usage:
            return None
        model = msg.get("model") or "?"
        if model == "<synthetic>":
            return None
        return {
            "key": msg.get("id") or rec.get("requestId") or rec.get("uuid"),
            "time": parse_time(rec["timestamp"]),
            "model": model,
            "usage": usage,
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
