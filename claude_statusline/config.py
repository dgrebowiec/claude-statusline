"""User settings: detail level, which fields to show and in what order, theme, separator, colours."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .themes import BAR_NAMES, DEFAULT_BAR, DEFAULT_THEME, THEME_NAMES

FIELDS = ("model", "effort", "skill", "context", "cache", "5h", "7d", "share", "cacheio", "agents")
FIELD_DESCRIPTIONS = {
    "model": "model name",
    "effort": "effort level",
    "skill": "the skill invoked last in this session",
    "context": "context window: bar, percent, size",
    "cache": "prompt cache tier and expiry time",
    "5h": "5-hour plan limit",
    "7d": "7-day plan limit",
    "share": "this session's share of the limits",
    "cacheio": "tokens read from and written to the cache by the last call",
    "agents": "subagents at work, each on a row of its own",
}
AGENT_FIELDS = ("time", "tokens", "model", "effort", "skill", "cache", "share")
AGENT_FIELD_DESCRIPTIONS = {
    "time": "how long the subagent has been working",
    "tokens": "tokens the subagent has used",
    "model": "model name",
    "effort": "effort level",
    "skill": "the skill it invoked last",
    "cache": "prompt cache tier and expiry time",
    "share": "its share of the 5-hour limit",
}
# Fields that fill up towards a limit: each can show a progress bar.
BAR_FIELDS = ("context", "5h", "7d")
DEFAULT_BARS = ["context", "5h", "7d"]
# With two rows: the session on the first one, the plan limits on the second.
SECOND_ROW_FIELDS = ("5h", "7d", "share")
ROW_COUNTS = (1, 2)
LEVELS = ("minimal", "normal", "detailed")
DEFAULT_FIELDS = ["model", "effort", "skill", "context", "cache", "5h", "7d", "share", "cacheio"]
DEFAULT_SEPARATOR = " | "


@dataclass
class Config:
    level: str = "normal"
    fields: List[str] = field(default_factory=lambda: list(DEFAULT_FIELDS))
    separator: str = DEFAULT_SEPARATOR
    colors: bool = True
    agent_fields: List[str] = field(default_factory=lambda: list(AGENT_FIELDS))
    theme: str = DEFAULT_THEME
    bar: str = DEFAULT_BAR
    bars: List[str] = field(default_factory=lambda: list(DEFAULT_BARS))  # fields with a bar
    level_colors: bool = True  # green / yellow / red by how full a field is
    rows: int = 2  # 2: session on the first row, plan limits on the second

    def has_bar(self, name: str) -> bool:
        return name in self.bars and self.level != "minimal"

    def to_dict(self) -> Dict[str, Any]:
        return {"level": self.level, "fields": list(self.fields), "theme": self.theme, "bar": self.bar,
                "bars": list(self.bars), "level_colors": self.level_colors,
                "rows": self.rows,
                "separator": self.separator, "colors": self.colors,
                "agent_fields": list(self.agent_fields)}


def config_path() -> Path:
    override = os.environ.get("CLAUDE_STATUSLINE_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "claude-statusline.json"


def from_dict(data: Any) -> Config:
    """Tolerant parsing: anything wrong falls back to the default for that key."""
    if not isinstance(data, dict):
        return Config()
    level = data.get("level")
    fields: List[str] = []
    for name in data.get("fields") or []:
        if name in FIELDS and name not in fields:
            fields.append(name)
    agent_fields: List[str] = []
    for name in data.get("agent_fields") or []:
        if name in AGENT_FIELDS and name not in agent_fields:
            agent_fields.append(name)
    bars = data.get("bars")
    if isinstance(bars, list):  # an empty list is valid: no bars at all
        bars = [name for name in BAR_FIELDS if name in bars]
    else:
        bars = list(DEFAULT_BARS)
    level_colors = data.get("level_colors")
    separator = data.get("separator")
    colors = data.get("colors")
    theme = data.get("theme")
    return Config(
        level=level if level in LEVELS else "normal",
        fields=fields or list(DEFAULT_FIELDS),
        separator=separator if isinstance(separator, str) else DEFAULT_SEPARATOR,
        colors=colors if isinstance(colors, bool) else True,
        agent_fields=agent_fields or list(AGENT_FIELDS),
        theme=theme if theme in THEME_NAMES else DEFAULT_THEME,
        bar=data.get("bar") if data.get("bar") in BAR_NAMES else DEFAULT_BAR,
        bars=bars,
        level_colors=level_colors if isinstance(level_colors, bool) else True,
        rows=data.get("rows") if data.get("rows") in ROW_COUNTS else 2,
    )


def load(path: Optional[Path] = None) -> Config:
    path = path or config_path()
    try:
        return from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Config()


def save(config: Config, path: Optional[Path] = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path
