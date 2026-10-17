"""Builds the one-line status from the JSON Claude Code passes on stdin."""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cache import cache_status
from .usage import session_share

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "claude-statusline"

RESET = "\033[0m"
# Style name -> SGR parameters. Colours are chosen so each kind of data reads as its own group.
STYLES = {
    "model": "1;36",       # bold cyan
    "sep": "2",            # dim
    "ok": "32",            # green
    "warn": "33",          # yellow
    "bad": "31",           # red
    "dim": "2",
    "label": "1",          # bold
    "share": "3;36",       # italic cyan
    "tier_1h": "34",       # blue
    "tier_5m": "35",       # magenta
    "expired": "2;31",     # dim red
}

BAR_WIDTH = 20
LIMITS = (("five_hour", "5h", 5), ("seven_day", "7d", 168))  # key, label, window hours


def colours_enabled() -> bool:
    """Respects NO_COLOR (https://no-color.org)."""
    return "NO_COLOR" not in os.environ


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


def _model_name(payload: Dict[str, Any]) -> str:
    model = payload.get("model") or {}
    return model.get("display_name") or model.get("id") or "?"


def _context_part(payload: Dict[str, Any], on: bool) -> Optional[str]:
    """Bar, percent, size and warnings; None when Claude Code sent no context data."""
    context = payload.get("context_window") or {}
    pct = context.get("used_percentage")
    if pct is None:
        return None
    pct_int = int(float(pct))
    style = level(pct_int)
    filled = min(pct_int * BAR_WIDTH // 100, BAR_WIDTH)
    bar = "#" * filled + "-" * (BAR_WIDTH - filled)
    out = paint(f"[{bar}] {pct_int}%", style, on)
    tokens = context.get("total_input_tokens")
    size = context.get("context_window_size")
    if tokens is not None and size is not None:
        out += " " + paint(f"({fmt_tokens(tokens)}/{fmt_tokens(size)})", "dim", on)
    if style == "bad":
        out += " " + paint("!! FULL: run /compact or start a new session", "bad", on)
    elif style == "warn":
        out += " " + paint("! high", "warn", on)
    return out


def _cache_part(transcript: Optional[str], now: float, on: bool) -> str:
    """Absolute local expiry time: the statusline is not redrawn on a timer, so a countdown would freeze."""
    status = cache_status(transcript) if transcript else None
    if status is None:
        return "cache: " + paint("none", "dim", on)
    tier, expires_at = status
    tier_style = f"tier_{tier}"
    clock = datetime.fromtimestamp(expires_at).strftime("%H:%M:%S")
    head = "cache " + paint(tier, tier_style, on) + ": "
    if expires_at <= now:
        return head + paint(f"expired at {clock}", "expired", on)
    return head + "until " + paint(clock, tier_style, on)


def _reset_clock(resets_at: float, now: float) -> str:
    """Local time of a limit reset: HH:MM today, with the date (DD.MM HH:MM) on later days."""
    reset = datetime.fromtimestamp(resets_at)
    if reset.date() == datetime.fromtimestamp(now).date():
        return reset.strftime("%H:%M")
    return reset.strftime("%d.%m %H:%M")


def _limit_parts(payload: Dict[str, Any], transcript: Optional[str], now: float,
                 projects_dir: Path, cache_dir: Path, on: bool) -> List[str]:
    rate_limits = payload.get("rate_limits") or {}
    parts = []
    for key, label, hours in LIMITS:
        window = rate_limits.get(key) or {}
        used = window.get("used_percentage")
        if used is None:
            continue
        pct = int(float(used))
        text = paint(label, "label", on) + ": " + paint(f"{pct}%", level(pct), on)
        resets_at = window.get("resets_at")
        if resets_at is not None and resets_at > now:
            text += " " + paint(f"(reset {_reset_clock(resets_at, now)})", "dim", on)
        if transcript:
            value = session_share(transcript, hours, float(used), str(projects_dir),
                                  cache_dir, now)
            if value is not None:
                text += " " + paint(f"(session ~{value:.1f}%)", "share", on)
        parts.append(text)
    return parts


def render(payload: Dict[str, Any], now: Optional[float] = None,
           projects_dir: Path = DEFAULT_PROJECTS_DIR,
           cache_dir: Path = DEFAULT_CACHE_DIR) -> str:
    now = time.time() if now is None else now
    on = colours_enabled()
    transcript = payload.get("transcript_path") or None
    if transcript and not os.path.isfile(transcript):
        transcript = None
    context = _context_part(payload, on)
    if context is None:
        context = "context: " + paint("no data", "dim", on)
    parts = [paint(_model_name(payload), "model", on), context,
             _cache_part(transcript, now, on)]
    parts += _limit_parts(payload, transcript, now, projects_dir, cache_dir, on)
    separator = " " + paint("|", "sep", on) + " "
    return separator.join(parts)
