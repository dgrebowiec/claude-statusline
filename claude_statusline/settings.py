"""Adds and removes the statusLine entry in Claude Code's settings.json."""
import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

MARKERS = ("claude-statusline", "claude_statusline")  # how we recognise our own entry
MIN_REFRESH = 3       # seconds; each run takes ~0.1 s, so shorter gains little and costs CPU
DEFAULT_REFRESH = 10  # seconds; set on install so subagent work shows up while it happens


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def default_command() -> str:
    exe = shutil.which("claude-statusline")
    if exe:
        return exe
    return f'"{sys.executable}" -m claude_statusline'


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return backup


def _save(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _is_ours(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    command = str(entry.get("command", ""))
    return any(marker in command for marker in MARKERS)


def install(path: Path, command: Optional[str] = None) -> Optional[Path]:
    """Points statusLine at this tool. Returns the backup path, if a file existed.

    A refresh interval already set is kept; otherwise DEFAULT_REFRESH is set.
    """
    data = _load(path)
    backup = _backup(path)
    old = data.get("statusLine")
    refresh = old.get("refreshInterval") if isinstance(old, dict) else None
    data["statusLine"] = {"type": "command", "command": command or default_command(),
                          "refreshInterval": refresh or DEFAULT_REFRESH}
    _save(path, data)
    return backup


def get_agent_panel(path: Path) -> bool:
    """True when Claude Code's subagentStatusLine runs this tool."""
    try:
        return _is_ours(_load(path).get("subagentStatusLine"))
    except (OSError, ValueError):
        return False


def set_agent_panel(path: Path, on: bool, command: Optional[str] = None) -> bool:
    """Points subagentStatusLine at `claude-statusline subagent`, or removes it again.

    Never touches a subagentStatusLine of another tool (raises ValueError when turning on).
    Returns True when the file changed.
    """
    data = _load(path)
    entry = data.get("subagentStatusLine")
    if entry is not None and not _is_ours(entry):
        if on:
            raise ValueError("subagentStatusLine already points to another command")
        return False
    if on == (entry is not None):
        return False
    _backup(path)
    if on:
        data["subagentStatusLine"] = {"type": "command",
                                      "command": f"{command or default_command()} subagent"}
    else:
        del data["subagentStatusLine"]
    _save(path, data)
    return True


def get_refresh(path: Path) -> Optional[int]:
    """Seconds between timed re-runs of the status line, or None when it runs on events only."""
    try:
        entry = _load(path).get("statusLine")
    except (OSError, ValueError):
        return None
    return entry.get("refreshInterval") if isinstance(entry, dict) else None


def set_refresh(path: Path, seconds: Optional[int]) -> None:
    """Sets refreshInterval of our statusLine entry; None removes it (events only).

    Raises ValueError when statusLine is missing or points to another tool, or seconds is
    below MIN_REFRESH.
    """
    if seconds is not None and seconds < MIN_REFRESH:
        raise ValueError(f"refresh interval must be at least {MIN_REFRESH} s")
    data = _load(path)
    entry = data.get("statusLine")
    if not _is_ours(entry):
        raise ValueError("statusLine does not point to claude-statusline; "
                         "run `claude-statusline install` first")
    _backup(path)
    if seconds is None:
        entry.pop("refreshInterval", None)
    else:
        entry["refreshInterval"] = seconds
    _save(path, data)


def uninstall(path: Path) -> bool:
    """Removes statusLine and subagentStatusLine where they point to this tool.

    Returns True if anything was removed.
    """
    if not path.exists():
        return False
    data = _load(path)
    ours = [key for key in ("statusLine", "subagentStatusLine") if _is_ours(data.get(key))]
    if not ours:
        return False
    _backup(path)
    for key in ours:
        del data[key]
    _save(path, data)
    return True
