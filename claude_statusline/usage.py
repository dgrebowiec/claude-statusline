"""How much of the plan limit this session used: weighted tokens of the session vs. the window.

Every API call of the last 7 days is kept in an index (cache dir, `index.json`) as
key -> (time, weighted tokens). Transcripts are append-only, so each run reads only the bytes
added since the last run; the window and session totals are sums over the index.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .pricing import weighted
from .transcript import usage_record

INDEX_VERSION = 1  # bump when the weights change: the index stores weighted tokens
MAX_HOURS = 168    # the longest window; older files are dropped from the index

Calls = Dict[str, List[float]]  # message key -> [Unix time, weighted tokens]


def window_start(hours: int, now: float, resets_at: Optional[float] = None) -> float:
    """Start of the limit window: resets_at - window length, or the last `hours` when unknown.

    The window starts with the first message after the previous reset, not `hours` ago, so
    counting the last `hours` would add usage of the previous window and shrink the share.
    """
    if resets_at is not None and resets_at > now:
        return min(now, resets_at - hours * 3600)
    return now - hours * 3600


def _recent_transcripts(projects_dir: str, since_ts: float) -> Iterator[Tuple[str, int]]:
    """(path, size) of every *.jsonl under projects_dir modified since since_ts."""
    stack = [projects_dir]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif entry.name.endswith(".jsonl"):
                    st = entry.stat()
                    if st.st_mtime >= since_ts:
                        yield entry.path, st.st_size
            except OSError:
                continue


def _read_new(path: str, entry: Dict) -> bool:
    """Add calls written after entry["offset"] to entry["calls"]; True when anything was read.

    The last record of a message wins, as in claude-token-report. A line still being written
    (no newline yet) is left for the next run.
    """
    try:
        with open(path, "rb") as fh:
            fh.seek(entry["offset"])
            data = fh.read()
    except OSError:
        return False
    end = data.rfind(b"\n") + 1
    if end == 0:
        return False
    calls = entry["calls"]
    for line in data[:end].decode("utf-8", errors="replace").splitlines():
        rec = usage_record(line)
        if rec is None or rec["key"] is None:
            continue
        calls[rec["key"]] = [rec["time"].timestamp(), weighted(rec["usage"], rec["model"])]
    entry["offset"] += end
    return True


def load_index(projects_dir: str, cache_dir: Path, now: float) -> Dict[str, Dict]:
    """path -> {"offset", "size", "calls"} for transcripts of the last MAX_HOURS, brought up to date."""
    index_file = cache_dir / "index.json"
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
        files = data["files"] if data.get("version") == INDEX_VERSION else {}
    except (OSError, ValueError, KeyError, TypeError):
        files = {}
    fresh: Dict[str, Dict] = {}
    changed = False
    for path, size in _recent_transcripts(projects_dir, now - MAX_HOURS * 3600):
        entry = files.get(path)
        if entry is None or size < entry["offset"]:  # new, or rewritten from scratch
            entry = {"offset": 0, "size": -1, "calls": {}}
        if entry["size"] != size:
            changed |= _read_new(path, entry)
            entry["size"] = size
        fresh[path] = entry
    if changed or fresh.keys() != files.keys():
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = index_file.with_suffix(f".{os.getpid()}.tmp")  # sessions run side by side
            tmp.write_text(json.dumps({"version": INDEX_VERSION, "files": fresh}),
                           encoding="utf-8")
            os.replace(tmp, index_file)
        except OSError:
            pass
    return fresh


def _total(entries, since_ts: float) -> float:
    calls: Calls = {}
    for entry in entries:
        calls.update(entry["calls"])
    return sum(w for t, w in calls.values() if t >= since_ts)


def session_paths(transcript: str, index: Dict[str, Dict]) -> List[str]:
    """Main transcript plus its subagent transcripts."""
    prefix = os.path.join(transcript[: -len(".jsonl")], "subagents") + os.sep
    return [p for p in index if p == transcript or p.startswith(prefix)]


def share_numbers(transcript: str, hours: int, limit_used_pct: float, projects_dir: str,
                  cache_dir: Path, now: Optional[float] = None,
                  resets_at: Optional[float] = None,
                  index: Optional[Dict[str, Dict]] = None
                  ) -> Optional[Tuple[float, float, float]]:
    """(share %, session weighted tokens, window weighted tokens); None when the window is empty.

    The share is used% x (session / window): an estimate, see README.
    """
    now = time.time() if now is None else now
    if index is None:
        index = load_index(projects_dir, cache_dir, now)
    since_ts = window_start(hours, now, resets_at)
    window = _total(index.values(), since_ts)
    if window <= 0:
        return None
    session = _total((index[p] for p in session_paths(transcript, index)), since_ts)
    return limit_used_pct * session / window, session, window


def session_share(transcript: str, hours: int, limit_used_pct: float, projects_dir: str,
                  cache_dir: Path, now: Optional[float] = None,
                  resets_at: Optional[float] = None) -> Optional[float]:
    numbers = share_numbers(transcript, hours, limit_used_pct, projects_dir, cache_dir, now,
                            resets_at)
    return None if numbers is None else numbers[0]
