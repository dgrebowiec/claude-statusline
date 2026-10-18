"""Readings of the plan limits, shared by all sessions, to split each rise between sessions.

Every run sees the used % of the 5 h and 7 d limits that Claude Code got with its last API
response. A reading is logged (`samples.jsonl` in the cache dir) only when the value went up
within the same window or a new window started: stale readings of an idle session are lower
and are skipped, and the log stays small (0.1% steps, at most ~1000 lines per window).
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SAME_WINDOW_SECONDS = 600  # resets_at of one window may differ slightly between readings
KEEP_SECONDS = 8 * 86400   # older readings are dropped when the log is rewritten
REWRITE_BYTES = 512_000

Reading = Tuple[float, float, float]  # (Unix time, used %, resets_at)


def same_window(a: float, b: float) -> bool:
    return abs(a - b) < SAME_WINDOW_SECONDS


class Samples:
    """The log of one cache dir, read once per run."""

    def __init__(self, cache_dir: Path, now: float):
        self.path = cache_dir / "samples.jsonl"
        self.readings: Dict[int, List[Reading]] = {}
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in text.splitlines():
            try:
                rec = json.loads(line)
                reading = (float(rec["t"]), float(rec["u"]), float(rec["r"]))
                self.readings.setdefault(int(rec["h"]), []).append(reading)
            except (ValueError, KeyError, TypeError):
                continue
        for readings in self.readings.values():
            readings.sort()
        if len(text) > REWRITE_BYTES:
            self._rewrite(now - KEEP_SECONDS)

    def _rewrite(self, since: float) -> None:
        lines = [json.dumps({"h": h, "t": t, "u": u, "r": r})
                 for h, readings in self.readings.items()
                 for t, u, r in readings if t >= since]
        try:
            tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def observe(self, hours: int, used: float, resets_at: float, now: float) -> None:
        """Log the reading when it is higher than the last one of its window, or a new window."""
        readings = self.readings.setdefault(hours, [])
        if readings:
            _, last_used, last_reset = readings[-1]
            if same_window(last_reset, resets_at) and used <= last_used:
                return
        readings.append((now, used, resets_at))
        line = json.dumps({"h": hours, "t": now, "u": used, "r": resets_at}) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:  # O_APPEND: safe side by side
                fh.write(line)
        except OSError:
            pass

    def window(self, hours: int, resets_at: float) -> List[Tuple[float, float]]:
        """(time, used %) readings of the window that resets at resets_at, rising."""
        points: List[Tuple[float, float]] = []
        for t, u, r in self.readings.get(hours, []):
            if same_window(r, resets_at) and (not points or u > points[-1][1]):
                points.append((t, u))
        return points
