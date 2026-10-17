"""Adds and removes the statusLine entry in Claude Code's settings.json."""
import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

MARKERS = ("claude-statusline", "claude_statusline")  # how we recognise our own entry


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
    """Points statusLine at this tool. Returns the backup path, if a file existed."""
    data = _load(path)
    backup = _backup(path)
    data["statusLine"] = {"type": "command", "command": command or default_command()}
    _save(path, data)
    return backup


def uninstall(path: Path) -> bool:
    """Removes statusLine only when it points to this tool. Returns True if removed."""
    if not path.exists():
        return False
    data = _load(path)
    if not _is_ours(data.get("statusLine")):
        return False
    _backup(path)
    del data["statusLine"]
    _save(path, data)
    return True
