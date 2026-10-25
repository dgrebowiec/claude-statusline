"""Themes: how the fields of the status line are drawn and joined.

Every field comes as a segment (its text and a tone, e.g. "model" or "bad"); a theme decides
what a segment looks like. Filled themes paint each segment's background in its tone and draw
their text plainly, so the background carries the state (green / orange / red for the limits);
the outline themes keep the text colours and draw a border in the segment's tone.
The shapes are standard Unicode characters (no Nerd Font needed).
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

RESET = "\033[0m"

Segment = Tuple[str, str]  # (text, tone)


@dataclass(frozen=True)
class Theme:
    description: str
    filled: bool = False     # segments get a background colour
    lead: str = ""           # glyph before the first segment (filled themes)
    join: str = ""           # glyph between two touching segments (filled themes)
    tail: str = ""           # glyph after the last segment (filled themes)
    gap: str = ""            # text between separate segments; "" means they touch
    open: str = ""           # glyphs around each segment: filled caps or outline brackets
    close: str = ""
    box: bool = False        # three rows: a frame around every segment


THEMES: Dict[str, Theme] = {
    "plain": Theme("coloured text, fields split by the separator"),
    "blocks": Theme("filled blocks with a gap between them", filled=True, gap=" "),
    "slant": Theme("filled blocks joined by slanted edges", filled=True, join="\u25e4",
                   tail="\u25e4"),
    "fade": Theme("filled blocks fading into each other", filled=True, join="\u2593\u2592\u2591",
                  tail="\u2593\u2592\u2591"),
    "boxes": Theme("coloured frame around each field (three rows)", gap=" ", box=True),
}
THEME_NAMES = tuple(THEMES)

# Progress bar styles: (filled cell, empty cell, text before, text after).
BARS: Dict[str, Tuple[str, str, str, str]] = {
    "auto": ("", "", "", ""),  # ascii on plain / boxes, bricks on the filled themes
    "ascii": ("#", "-", "[", "]"),
    "bricks": ("\u25ae", "\u25af", "", ""),
    "dots": ("\u25cf", "\u25cb", "", ""),
    "blocks": ("\u2588", "\u2591", "", ""),
    "line": ("\u2501", "\u254c", "", ""),
}
BAR_NAMES = tuple(BARS)
DEFAULT_BAR = "auto"
DEFAULT_THEME = "plain"

# Tone -> (background, text on it, border) in the 256-colour palette.
PALETTE: Dict[str, Tuple[int, int, int]] = {
    "model": (25, 231, 39),
    "effort": (97, 231, 171),
    "ok": (29, 231, 42),
    "warn": (214, 16, 214),
    "bad": (160, 231, 196),
    "tier_1h": (31, 231, 38),
    "tier_5m": (133, 231, 170),
    "expired": (240, 252, 244),
    "none": (238, 250, 244),
    "share": (61, 231, 105),
    "cacheio": (238, 252, 246),
}


def visible_len(text: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def _colours(tone: str) -> Tuple[int, int, int]:
    return PALETTE.get(tone, PALETTE["none"])


def _fill(text: str, tone: str) -> str:
    bg, fg, _ = _colours(tone)
    return f"\033[48;5;{bg};38;5;{fg}m {text} "


def _glyph(glyph: str, fg_tone: str, bg_tone: str = "") -> str:
    """A shape in fg_tone's background colour, over bg_tone's background (or none)."""
    code = f"\033[0;38;5;{_colours(fg_tone)[0]}"
    if bg_tone:
        code += f";48;5;{_colours(bg_tone)[0]}"
    return f"{code}m{glyph}"


def _line(text: str, tone: str, on: bool) -> str:
    return f"\033[38;5;{_colours(tone)[2]}m{text}{RESET}" if on else text


def _filled(segments: List[Segment], theme: Theme) -> str:
    if theme.gap:  # separate blocks
        parts = []
        for text, tone in segments:
            block = _fill(text, tone)
            if theme.open:
                block = _glyph(theme.open, tone) + block + _glyph(theme.close, tone)
            parts.append(block + RESET)
        return theme.gap.join(parts)
    out = _glyph(theme.lead, segments[0][1]) if theme.lead else ""
    for i, (text, tone) in enumerate(segments):
        if i:
            out += _glyph(theme.join, segments[i - 1][1], tone)
        out += _fill(text, tone)
    return out + _glyph(theme.tail, segments[-1][1]) + RESET


def _boxes(segments: List[Segment], theme: Theme, on: bool) -> str:
    rows = ["", "", ""]
    for i, (text, tone) in enumerate(segments):
        if i:
            rows = [row + theme.gap for row in rows]
        bar = "─" * (visible_len(text) + 2)
        rows[0] += _line(f"╭{bar}╮", tone, on)
        rows[1] += _line("│", tone, on) + f" {text} " + _line("│", tone, on)
        rows[2] += _line(f"╰{bar}╯", tone, on)
    return "\n".join(rows)


def join(segments: List[Segment], name: str, on: bool, separator: str) -> str:
    """The status line of `segments` in theme `name`.

    `separator` (already painted) is used by the plain theme only. Without colours the filled
    themes fall back to plain: their shapes are made of colour.
    """
    theme = THEMES.get(name, THEMES[DEFAULT_THEME])
    if not segments:
        return ""
    if theme.filled and on:
        return _filled(segments, theme)
    if theme.box:
        return _boxes(segments, theme, on)
    if theme.open:
        return theme.gap.join(_line(theme.open, tone, on) + text + _line(theme.close, tone, on)
                              for text, tone in segments)
    return separator.join(text for text, _ in segments)
