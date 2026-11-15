"""The look most tests were written against: plain text, one row, a bar on context only.

The shipped defaults (slant theme, two rows, bars on every limit) are tested on their own.
"""
from dataclasses import dataclass, field
from typing import List

from claude_statusline import config as config_module


@dataclass
class Config(config_module.Config):
    fields: List[str] = field(default_factory=lambda: ["model", "effort", "skill", "context",
                                                       "cache", "5h", "7d", "share"])
    theme: str = "plain"
    bars: List[str] = field(default_factory=lambda: ["context"])
    rows: int = 1
