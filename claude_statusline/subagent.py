"""Lines for Claude Code's subagentStatusLine: each subagent's share of the 5 h limit.

Claude Code runs the command every 5 s while subagents are listed in the agent panel and passes
the session (transcript_path) and its tasks on stdin. A task's id names its transcript,
<session>/subagents/agent-<id>.jsonl. The payload has no rate limits, so the used % comes from
the last reading the main status line logged (samples.py).
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .samples import Samples
from .usage import load_index, share_numbers


def subagent_lines(payload: Dict[str, Any], projects_dir: Path, cache_dir: Path,
                   now: Optional[float] = None) -> List[str]:
    """One JSON line {"id", "content"} per task whose share can be computed."""
    now = time.time() if now is None else now
    transcript = payload.get("transcript_path") or ""
    tasks = [t for t in payload.get("tasks") or [] if isinstance(t, dict) and t.get("id")]
    if not transcript.endswith(".jsonl") or not tasks:
        return []
    samples = Samples(cache_dir, now)
    latest = samples.latest(5, now)
    if latest is None:
        return []
    used, resets_at = latest
    index = load_index(str(projects_dir), cache_dir, now)
    folder = os.path.join(transcript[: -len(".jsonl")], "subagents")
    lines = []
    for task in tasks:
        path = os.path.join(folder, f"agent-{task['id']}.jsonl")
        if path not in index:
            continue
        numbers = share_numbers(transcript, 5, used, str(projects_dir), cache_dir, now,
                                resets_at, index, samples, [path])
        if numbers is not None:
            lines.append(json.dumps({"id": task["id"], "content": f"5h ~{numbers[0]:.1f}%"}))
    return lines
