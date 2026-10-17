"""Builds the one-line status from the JSON Claude Code passes on stdin."""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .cache import cache_status
from .usage import session_share

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "claude-statusline"

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

BAR_WIDTH = 20
LIMITS = (("five_hour", "5h", 5), ("seven_day", "7d", 168))  # key, label, window hours


def fmt_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{int(n) // 1000}k"


def _model_name(payload: Dict[str, Any]) -> str:
    model = payload.get("model") or {}
    return model.get("display_name") or model.get("id") or "?"


def _context_part(payload: Dict[str, Any]) -> Optional[str]:
    """Bar, percent and warnings; None when Claude Code sent no context data."""
    context = payload.get("context_window") or {}
    pct = context.get("used_percentage")
    if pct is None:
        return None
    pct_int = int(float(pct))
    filled = min(pct_int * BAR_WIDTH // 100, BAR_WIDTH)
    bar = "#" * filled + "-" * (BAR_WIDTH - filled)
    if pct_int >= 85:
        color, warn = RED, " !! PRZEPEŁNIENIE: użyj /compact lub nowej sesji"
    elif pct_int >= 70:
        color, warn = YELLOW, " ! uwaga"
    else:
        color, warn = GREEN, ""
    size_info = ""
    tokens = context.get("total_input_tokens")
    size = context.get("context_window_size")
    if tokens is not None and size is not None:
        size_info = f" ({fmt_tokens(tokens)}/{fmt_tokens(size)})"
    return f"{color}[{bar}] {pct_int}%{RESET}{size_info}{warn}"


def _cache_part(transcript: Optional[str], now: float) -> str:
    """Absolute local expiry time: the statusline is not redrawn on a timer, so a countdown would freeze."""
    status = cache_status(transcript) if transcript else None
    if status is None:
        return " | cache: brak"
    tier, expires_at = status
    clock = datetime.fromtimestamp(expires_at).strftime("%H:%M:%S")
    if expires_at <= now:
        return f" | cache {tier}: wygasł o {clock}"
    return f" | cache {tier}: do {clock}"


def _limit_parts(payload: Dict[str, Any], transcript: Optional[str], now: float,
                 projects_dir: Path, cache_dir: Path) -> str:
    rate_limits = payload.get("rate_limits") or {}
    out = ""
    for key, label, hours in LIMITS:
        window = rate_limits.get(key) or {}
        used = window.get("used_percentage")
        if used is None:
            continue
        reset = ""
        resets_at = window.get("resets_at")
        if resets_at is not None:
            left = int(resets_at - now)
            if left > 0:
                reset = f" (reset {left // 3600}h{left % 3600 // 60:02d}m)"
        share = ""
        if transcript:
            value = session_share(transcript, hours, float(used), str(projects_dir),
                                  cache_dir, now)
            if value is not None:
                share = f" (sesja ~{value:.1f}%)"
        out += f" | {label}: {int(float(used))}%{reset}{share}"
    return out


def render(payload: Dict[str, Any], now: Optional[float] = None,
           projects_dir: Path = DEFAULT_PROJECTS_DIR,
           cache_dir: Path = DEFAULT_CACHE_DIR) -> str:
    now = time.time() if now is None else now
    transcript = payload.get("transcript_path") or None
    if transcript and not os.path.isfile(transcript):
        transcript = None
    context = _context_part(payload)
    head = f"{_model_name(payload)} | "
    head += context if context is not None else "kontekst: brak danych"
    return head + _cache_part(transcript, now) + _limit_parts(
        payload, transcript, now, projects_dir, cache_dir)
