"""How much of the plan limit this session used: weighted tokens of the session vs. the window.

Every API call of the last 7 days is kept in an index (cache dir, `index.json`) as
key -> (time, weighted tokens). Transcripts are append-only, so each run reads only the bytes
added since the last run; the window and session totals are sums over the index. Each rise of
the limit between two readings (see samples.py) is split by the calls made in that span.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .pricing import weighted
from .samples import Samples
from .transcript import usage_record

INDEX_VERSION = 2  # bump when the weights change: the index stores weighted tokens
MAX_HOURS = 168    # the longest window; older files are dropped from the index

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


def _window_calls(index: Dict[str, Dict], session: Set[str],
                  since_ts: float) -> List[Tuple[float, float, bool]]:
    """(time, weighted tokens, part of the session) of every call since since_ts, by time."""
    calls: Dict[str, Tuple[float, float, bool]] = {}
    for path, entry in index.items():
        mine = path in session
        for key, (t, w) in entry["calls"].items():
            calls[key] = (t, w, mine)
    return sorted(c for c in calls.values() if c[0] >= since_ts)


def session_paths(transcript: str, index: Dict[str, Dict]) -> List[str]:
    """Main transcript plus its subagent transcripts."""
    prefix = os.path.join(transcript[: -len(".jsonl")], "subagents") + os.sep
    return [p for p in index if p == transcript or p.startswith(prefix)]


def attributed_share(calls: List[Tuple[float, float, bool]],
                     points: List[Tuple[float, float]]) -> float:
    """Each rise of the limit between two readings, split by weighted tokens in that span.

    points are (time, used %) from the window start (0 %) up; calls after the last reading
    are not in any reading yet. A rise in a span without calls is split like the last span
    with calls: it is usually a reading that came late (an idle session logged an old value
    first), and only rarely usage from another machine.
    """
    share = 0.0
    ratio = None  # mine / total of the last span with calls
    i = 0
    for (_, used_a), (t_b, used_b) in zip(points, points[1:]):
        mine = total = 0.0
        while i < len(calls) and calls[i][0] <= t_b:
            _, w, is_mine = calls[i]
            total += w
            mine += w if is_mine else 0.0
            i += 1
        if total > 0:
            ratio = mine / total
        if ratio is not None:
            share += (used_b - used_a) * ratio
    return share


def share_numbers(transcript: str, hours: int, limit_used_pct: float, projects_dir: str,
                  cache_dir: Path, now: Optional[float] = None,
                  resets_at: Optional[float] = None,
                  index: Optional[Dict[str, Dict]] = None,
                  samples: Optional[Samples] = None,
                  paths: Optional[List[str]] = None) -> Optional[Tuple[float, float, float]]:
    """(share %, session weighted tokens, window weighted tokens); None when the window is empty.

    `paths` are the transcripts counted as "the session"; by default the main transcript and
    its subagents. Without readings of the limit (`samples`), the share is
    used% x (session / window); with them, each rise is split separately (see README).
    """
    now = time.time() if now is None else now
    if index is None:
        index = load_index(projects_dir, cache_dir, now)
    since_ts = window_start(hours, now, resets_at)
    session = set(paths if paths is not None else session_paths(transcript, index))
    calls = _window_calls(index, session, since_ts)
    window_wt = sum(w for _, w, _ in calls)
    if window_wt <= 0:
        return None
    session_wt = sum(w for _, w, mine in calls if mine)
    points = [(since_ts, 0.0)]
    if samples is not None and resets_at is not None:
        points += [p for p in samples.window(hours, resets_at) if p[0] > since_ts]
    if limit_used_pct > points[-1][1]:
        points.append((now, limit_used_pct))
    return attributed_share(calls, points), session_wt, window_wt


def session_share(transcript: str, hours: int, limit_used_pct: float, projects_dir: str,
                  cache_dir: Path, now: Optional[float] = None,
                  resets_at: Optional[float] = None) -> Optional[float]:
    numbers = share_numbers(transcript, hours, limit_used_pct, projects_dir, cache_dir, now,
                            resets_at)
    return None if numbers is None else numbers[0]
