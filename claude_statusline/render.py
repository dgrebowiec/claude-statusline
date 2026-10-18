"""Builds the one-line status from the JSON Claude Code passes on stdin."""
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import config as config_module
from .cache import cache_status, last_cache_io
from .config import Config
from .usage import share_numbers

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "claude-statusline"

RESET = "\033[0m"
# Style name -> SGR parameters. Colours are chosen so each kind of data reads as its own group.
STYLES = {
    "model": "1;36",       # bold cyan
    "effort": "1;95",      # bold bright magenta
    "sep": "2",            # dim
    "warn": "33",          # yellow
    "bad": "31",           # red
    "ok": "32",            # green
    "dim": "2",
    "label": "1",          # bold
    "share": "3;36",       # italic cyan
    "tier_1h": "34",       # blue
    "tier_5m": "35",       # magenta
    "expired": "2;31",     # dim red
    "cache_read": "32",    # green: a read is a cache hit
    "cache_write": "33",   # yellow: a write costs more than a plain input
}

BAR_WIDTH = 20
LIMITS = {"5h": ("five_hour", 5), "7d": ("seven_day", 168)}  # field -> (payload key, hours)


def colours_enabled(config: Config) -> bool:
    """Colours need the config setting on and no NO_COLOR (https://no-color.org)."""
    return config.colors and "NO_COLOR" not in os.environ


def paint(text: str, style: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{STYLES[style]}m{text}{RESET}"


def level(pct: float) -> str:
    """Traffic-light style for usage: green below 70%, yellow below 85%, red above."""
    if pct >= 85:
        return "bad"
    if pct >= 70:
        return "warn"
    return "ok"


def fmt_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{int(n) // 1000}k"


class Sources:
    """Where cache state and session share come from. The preview swaps in fixed values."""

    def __init__(self, projects_dir: Path = DEFAULT_PROJECTS_DIR,
                 cache_dir: Path = DEFAULT_CACHE_DIR):
        self.projects_dir = projects_dir
        self.cache_dir = cache_dir

    def has_transcript(self, path: str) -> bool:
        return os.path.isfile(path)

    def cache(self, transcript: str) -> Optional[Tuple[str, float]]:
        return cache_status(transcript)

    def cache_io(self, transcript: str) -> Optional[Tuple[int, int]]:
        return last_cache_io(transcript)

    def share(self, transcript: str, hours: int, used: float, now: float,
              resets_at: Optional[float] = None) -> Optional[Tuple[float, float, float]]:
        return share_numbers(transcript, hours, used, str(self.projects_dir),
                             self.cache_dir, now, resets_at)


@dataclass
class Frame:
    """Everything one render needs; each field builder reads from here."""
    payload: Dict[str, Any]
    now: float
    config: Config
    sources: Sources
    transcript: Optional[str]
    on: bool


def _model(f: Frame) -> str:
    model = f.payload.get("model") or {}
    name = model.get("display_name") or model.get("id") or "?"
    text = paint(name, "model", f.on)
    if "effort" in f.config.fields:
        effort = _effort_text(f)
        if effort:
            text += " " + paint(f"({effort})", "effort", f.on)
    return text


def _effort_text(f: Frame) -> Optional[str]:
    level_name = (f.payload.get("effort") or {}).get("level")
    return f"effort: {level_name}" if level_name else None


def _effort(f: Frame) -> Optional[str]:
    """Effort sits next to the model; on its own only when the model field is off."""
    if "model" in f.config.fields:
        return None
    text = _effort_text(f)
    return paint(text, "effort", f.on) if text else None


def _context(f: Frame) -> str:
    context = f.payload.get("context_window") or {}
    pct = context.get("used_percentage")
    if pct is None:
        return "context: " + paint("no data", "dim", f.on)
    pct_int = int(float(pct))
    style = level(pct_int)
    if f.config.level == "minimal":
        return paint(f"{pct_int}%", style, f.on)
    filled = min(pct_int * BAR_WIDTH // 100, BAR_WIDTH)
    bar = "#" * filled + "-" * (BAR_WIDTH - filled)
    out = paint(f"[{bar}] {pct_int}%", style, f.on)
    tokens = context.get("total_input_tokens")
    size = context.get("context_window_size")
    if tokens is not None and size is not None:
        detail = f"({fmt_tokens(tokens)}/{fmt_tokens(size)}"
        if f.config.level == "detailed":
            detail += f", {fmt_tokens(size - tokens)} left"
        out += " " + paint(detail + ")", "dim", f.on)
    if style == "bad":
        out += " " + paint("!! FULL: run /compact or start a new session", "bad", f.on)
    elif style == "warn":
        out += " " + paint("! high", "warn", f.on)
    return out


def _cache(f: Frame) -> str:
    status = f.sources.cache(f.transcript) if f.transcript else None
    if status is None:
        return "cache: " + paint("none", "dim", f.on)
    tier, expires_at = status
    style = f"tier_{tier}"
    clock = datetime.fromtimestamp(expires_at).strftime("%H:%M:%S")
    head = "cache " + paint(tier, style, f.on)
    if expires_at <= f.now:
        return head + ": " + paint(f"expired at {clock}", "expired", f.on)
    text = head + ": until " + paint(clock, style, f.on)
    if f.config.level == "detailed":
        text += " " + paint(f"(ttl {'60m' if tier == '1h' else '5m'})", "dim", f.on)
    return text


def _cacheio(f: Frame) -> str:
    io = f.sources.cache_io(f.transcript) if f.transcript else None
    if io is None:
        return "cache i/o: " + paint("none", "dim", f.on)
    read, write = io
    if f.config.level == "minimal":
        return paint(f"r {fmt_tokens(read)} w {fmt_tokens(write)}", "dim", f.on)
    if f.config.level == "detailed":
        return ("cache read " + paint(f"{read:,}", "cache_read", f.on) + ", write "
                + paint(f"{write:,}", "cache_write", f.on) + " tokens in the last call")
    return ("cache read " + paint(fmt_tokens(read), "cache_read", f.on) + ", write "
            + paint(fmt_tokens(write), "cache_write", f.on))


def _reset_clock(resets_at: float, now: float, detailed: bool) -> str:
    """Local time of a limit reset: HH:MM today, DD.MM HH:MM on later days."""
    reset = datetime.fromtimestamp(resets_at)
    if reset.date() == datetime.fromtimestamp(now).date():
        text = reset.strftime("%H:%M")
    else:
        text = reset.strftime("%d.%m %H:%M")
    if detailed:
        text += reset.strftime(" (%a)")
    return text


def _limit(name: str) -> Callable[[Frame], Optional[str]]:
    key = LIMITS[name][0]

    def build(f: Frame) -> Optional[str]:
        window = (f.payload.get("rate_limits") or {}).get(key) or {}
        used = window.get("used_percentage")
        if used is None:
            return None
        pct = int(float(used))
        text = paint(name, "label", f.on) + ": " + paint(f"{pct}%", level(pct), f.on)
        if f.config.level == "minimal":
            return text
        resets_at = window.get("resets_at")
        if resets_at is not None and resets_at > f.now:
            clock = _reset_clock(resets_at, f.now, f.config.level == "detailed")
            text += " " + paint(f"(reset {clock})", "dim", f.on)
        return text

    return build


def _share(f: Frame) -> Optional[str]:
    if not f.transcript:
        return None
    parts = []
    for name, (key, hours) in LIMITS.items():
        window = (f.payload.get("rate_limits") or {}).get(key) or {}
        used = window.get("used_percentage")
        if used is None:
            continue
        numbers = f.sources.share(f.transcript, hours, float(used), f.now,
                                  window.get("resets_at"))
        if numbers is None:
            continue
        share, session, window = numbers
        text = f"{name} ~{share:.1f}%"
        if f.config.level == "detailed":
            text += f" ({fmt_tokens(session)} of {fmt_tokens(window)} wt)"
        parts.append(text)
    if not parts:
        return None
    prefix = "session " if f.config.level == "minimal" else "session: "
    return paint(prefix + " · ".join(parts), "share", f.on)


BUILDERS: Dict[str, Callable[[Frame], Optional[str]]] = {
    "model": _model,
    "effort": _effort,
    "context": _context,
    "cache": _cache,
    "5h": _limit("5h"),
    "7d": _limit("7d"),
    "share": _share,
    "cacheio": _cacheio,
}


def build(payload: Dict[str, Any], now: float, config: Config, sources: Sources) -> str:
    on = colours_enabled(config)
    transcript = payload.get("transcript_path") or None
    if transcript and not sources.has_transcript(transcript):
        transcript = None
    frame = Frame(payload, now, config, sources, transcript, on)
    parts: List[str] = [text for text in (BUILDERS[name](frame) for name in config.fields)
                        if text]
    return paint(config.separator, "sep", on).join(parts)


def render(payload: Dict[str, Any], now: Optional[float] = None,
           projects_dir: Path = DEFAULT_PROJECTS_DIR,
           cache_dir: Path = DEFAULT_CACHE_DIR,
           config: Optional[Config] = None, sources: Optional[Sources] = None) -> str:
    now = time.time() if now is None else now
    config = config if config is not None else config_module.load()
    sources = sources or Sources(projects_dir, cache_dir)
    return build(payload, now, config, sources)


DEMO_NOW = 1_800_000_000.0
DEMO_PAYLOAD: Dict[str, Any] = {
    "model": {"display_name": "Opus 5.5"},
    "effort": {"level": "high"},
    "context_window": {"used_percentage": 42, "total_input_tokens": 420_000,
                       "context_window_size": 1_000_000},
    "transcript_path": "demo",
    "rate_limits": {
        "five_hour": {"used_percentage": 72, "resets_at": DEMO_NOW + 5400},
        "seven_day": {"used_percentage": 96, "resets_at": DEMO_NOW + 300_000},
    },
}


class DemoSources(Sources):
    """Fixed numbers for the preview: nothing is read from disk."""

    def has_transcript(self, path: str) -> bool:
        return True

    def cache(self, transcript: str) -> Optional[Tuple[str, float]]:
        return "1h", DEMO_NOW + 2400

    def cache_io(self, transcript: str) -> Optional[Tuple[int, int]]:
        return 118_432, 4_120

    def share(self, transcript, hours, used, now, resets_at=None):
        if hours == 5:
            return 23.2, 1_180_000, 5_100_000
        return 0.6, 1_180_000, 196_000_000


def preview(config: Config) -> str:
    return build(DEMO_PAYLOAD, DEMO_NOW, config, DemoSources())
