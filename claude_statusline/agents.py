"""Subagents of a session that are still working, for the `agents` field of the main status line.

Claude Code keeps each subagent's transcript in <session>/subagents/agent-<id>.jsonl, next to
agent-<id>.meta.json (agentType, description, "finished" once it is done). Claude Code no
longer lets a command draw the rows of its own agent panel, so the main line shows them instead.
"""
import json
import os
from dataclasses import dataclass
from typing import List, Optional

from .transcript import last_model, last_skill, parse_time, tail_lines

# An agent whose transcript has not changed for this long is taken as gone (killed, crashed).
MAX_IDLE = 30 * 60


@dataclass
class Agent:
    name: str
    description: str
    started: Optional[float]
    model_id: Optional[str]
    effort: Optional[str]
    skill: Optional[str]


def _first_time(path: str) -> Optional[float]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return parse_time(json.loads(fh.readline())["timestamp"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _last_effort(path: str, lines: int = 100) -> Optional[str]:
    try:
        for line in reversed(tail_lines(path, lines)):
            if '"effort"' not in line or '"type":"assistant"' not in line:
                continue
            effort = json.loads(line).get("effort")
            if isinstance(effort, str) and effort:
                return effort
    except (OSError, ValueError, AttributeError):
        pass
    return None


def running_agents(transcript: str, now: float) -> List[Agent]:
    """Unfinished subagents of the session, the longest-running first."""
    folder = os.path.join(transcript[: -len(".jsonl")], "subagents")
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    agents = []
    for name in names:
        if not (name.startswith("agent-") and name.endswith(".meta.json")):
            continue
        meta_path = os.path.join(folder, name)
        path = meta_path[: -len(".meta.json")] + ".jsonl"
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
            if not isinstance(meta, dict) or meta.get("finished"):
                continue
            if now - os.path.getmtime(path) > MAX_IDLE:
                continue
        except (OSError, ValueError):
            continue
        agents.append(Agent(
            name=str(meta.get("agentType") or "agent"),
            description=str(meta.get("description") or ""),
            started=_first_time(path),
            model_id=last_model(path),
            effort=_last_effort(path),
            skill=last_skill(path),
        ))
    agents.sort(key=lambda a: a.started or now)
    return agents
