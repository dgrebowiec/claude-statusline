"""How much of the plan limit this session used: weighted tokens of the session vs. the window."""
import datetime
import glob
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .pricing import weighted
from .transcript import usage_record

WINDOW_CACHE_TTL = {5: 60, 168: 300}  # seconds; short window is refreshed more often


def _collect(paths, since: datetime.datetime, calls: Dict) -> None:
    """Keep one usage record per message id (the last one wins, as claude-token-report does)."""
    for path in paths:
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                rec = usage_record(line)
                if rec is None or rec["time"] < since or rec["key"] is None:
                    continue
                calls[rec["key"]] = (rec["model"], rec["usage"])


def _total(calls: Dict) -> float:
    return sum(weighted(usage, model) for model, usage in calls.values())


def window_start(hours: int, now: float, resets_at: Optional[float] = None) -> float:
    """Start of the limit window: resets_at - window length, or the last `hours` when unknown.

    The window starts with the first message after the previous reset, not `hours` ago, so
    counting the last `hours` would add usage of the previous window and shrink the share.
    """
    if resets_at is not None and resets_at > now:
        return min(now, resets_at - hours * 3600)
    return now - hours * 3600


def window_total(projects_dir: str, since_ts: float) -> float:
    since = datetime.datetime.fromtimestamp(since_ts, datetime.timezone.utc)
    paths = []
    for path in glob.glob(os.path.join(projects_dir, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(path) >= since_ts:
                paths.append(path)
        except OSError:
            continue
    calls: Dict = {}
    _collect(paths, since, calls)
    return _total(calls)


def cached_window_total(hours: int, projects_dir: str, cache_dir: Path, now: float,
                        since_ts: float) -> float:
    cache_file = cache_dir / f"window_{hours}h.json"
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if now - data["at"] < WINDOW_CACHE_TTL[hours] and data["since"] == since_ts:
            return float(data["total"])
    except (OSError, ValueError, KeyError):
        pass
    total = window_total(projects_dir, since_ts)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"at": now, "since": since_ts, "total": total}),
                              encoding="utf-8")
    except OSError:
        pass
    return total


def session_total(transcript: str, since_ts: float) -> float:
    """Main transcript plus its subagent transcripts."""
    since = datetime.datetime.fromtimestamp(since_ts, datetime.timezone.utc)
    base = transcript[: -len(".jsonl")]
    paths = [transcript] + sorted(glob.glob(os.path.join(base, "subagents", "*.jsonl")))
    calls: Dict = {}
    _collect(paths, since, calls)
    return _total(calls)


def share_numbers(transcript: str, hours: int, limit_used_pct: float, projects_dir: str,
                  cache_dir: Path, now: Optional[float] = None,
                  resets_at: Optional[float] = None) -> Optional[Tuple[float, float, float]]:
    """(share %, session weighted tokens, window weighted tokens); None when the window is empty.

    The share is used% x (session / window): an estimate, see README.
    """
    now = time.time() if now is None else now
    since_ts = window_start(hours, now, resets_at)
    window = cached_window_total(hours, projects_dir, cache_dir, now, since_ts)
    if window <= 0:
        return None
    session = session_total(transcript, since_ts)
    return limit_used_pct * session / window, session, window


def session_share(transcript: str, hours: int, limit_used_pct: float, projects_dir: str,
                  cache_dir: Path, now: Optional[float] = None,
                  resets_at: Optional[float] = None) -> Optional[float]:
    numbers = share_numbers(transcript, hours, limit_used_pct, projects_dir, cache_dir, now,
                            resets_at)
    return None if numbers is None else numbers[0]
