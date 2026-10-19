"""Rows for Claude Code's agent panel (subagentStatusLine): each subagent's share of the 5 h limit.

Claude Code runs the command every 5 s while subagents are listed below the prompt and passes
the session (transcript_path) and its tasks on stdin. A task's id names its transcript,
<session>/subagents/agent-<id>.jsonl. The payload has no rate limits, so the used % comes from
the last reading the main status line logged (samples.py).

Content returned for a task replaces its whole row after the status circle, the right part
(run time, tokens) included, so the row is rebuilt as Claude Code draws it, with the share
added on the right. Tasks that are not running get no content and keep Claude Code's own row.
"""
import json
import re
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cache import cache_status
from .config import Config
from .render import DEMO_NOW, cache_short, colours_enabled, model_text, paint
from .samples import Samples
from .transcript import last_model
from .usage import load_index, share_numbers

NAME_GAP = 2  # spaces between the agent name and its description, as in Claude Code


def fmt_elapsed(seconds: float) -> str:
    """12s, 6m 13s, 1h 15m 59s: Claude Code's run time format."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def fmt_count(tokens: float) -> str:
    """59.3k, 1.2M: Claude Code's token count format."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1000:
        return f"{tokens / 1000:.1f}k"
    return str(int(tokens))


def visible_len(text: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def row(name: str, name_width: int, label: str, right: str, columns: int) -> str:
    """name, description, and right part flush right; the description is cut to fit.

    The right part may carry colour codes; they take no room.
    """
    left = name.ljust(name_width) + " " * NAME_GAP
    room = columns - len(left) - visible_len(right) - 1
    if room < len(label):
        label = label[: room - 1] + "…" if room > 1 else ""
    return left + label + " " * max(1, columns - len(left) - len(label) - visible_len(right)) + right


def right_part(fields: List[str], now: float, started: Optional[float], tokens: Optional[float],
               model_id: Optional[str], effort: Optional[str],
               cache: Optional[Tuple[str, float]], share: float, colors: bool) -> str:
    """The chosen pieces of a row's right part, in the configured order."""
    # Effort sits next to the model, as in the main status line; on its own only without it.
    with_model = "model" in fields and model_id
    pieces = {
        "time": fmt_elapsed(now - started) if started else None,
        "tokens": f"↓ {fmt_count(tokens)} tokens" if tokens else None,
        "model": model_text(model_id, effort if "effort" in fields else None, colors),
        "effort": (paint(f"effort: {effort}", "effort", colors)
                   if effort and not with_model else None),
        "cache": cache_short(cache, now, colors) if cache else None,
        "share": paint(f"5h ~{share:.1f}%", "share", colors),
    }
    return " · ".join(pieces[name] for name in fields if pieces.get(name))


def panel_preview(config: Config, columns: int = 100) -> str:
    """One demo row of the agent panel, for the configurator."""
    now = DEMO_NOW
    right = right_part(config.agent_fields, now, now - 375, 59_300, "claude-sonnet-5-5", "medium",
                       ("5m", now + 200), 4.8, colours_enabled(config))
    return row("explorer", len("explorer"), "Mapping the config module", right, columns)


def subagent_lines(payload: Dict[str, Any], projects_dir: Path, cache_dir: Path,
                   now: Optional[float] = None, colors: bool = False,
                   config: Optional[Config] = None) -> List[str]:
    """One JSON line {"id", "content"} per running task whose share can be computed."""
    now = time.time() if now is None else now
    config = config or Config()
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
    names = {t["id"]: t.get("name") or t.get("agentType") or "agent" for t in tasks}
    name_width = max(len(name) for name in names.values())
    columns = int(payload.get("columns") or 120)
    lines = []
    for task in tasks:
        path = os.path.join(folder, f"agent-{task['id']}.jsonl")
        if task.get("status") != "running" or path not in index:
            continue
        numbers = share_numbers(transcript, 5, used, str(projects_dir), cache_dir, now,
                                resets_at, index, samples, [path])
        if numbers is None:
            continue
        started = task["startTime"] / 1000 if task.get("startTime") else None
        right = right_part(config.agent_fields, now, started, task.get("tokenCount"),
                           last_model(path), task.get("effort") or None, cache_status(path),
                           numbers[0], colors)
        label = task.get("label") or task.get("description") or ""
        content = row(names[task["id"]], name_width, label, right, columns)
        lines.append(json.dumps({"id": task["id"], "content": content}, ensure_ascii=False))
    return lines
