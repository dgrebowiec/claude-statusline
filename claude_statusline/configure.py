"""Interactive configurator with a live preview.

In a terminal it is a full-screen editor driven by keys (arrows, space, enter). When stdin is
not a terminal (pipes, tests) it falls back to one text command per line.
"""
import copy
import os
import sys
import textwrap
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import config as config_module
from .config import (AGENT_FIELD_DESCRIPTIONS, AGENT_FIELDS, DEFAULT_SEPARATOR, FIELD_DESCRIPTIONS,
                     FIELDS, LEVELS, Config)
from .render import preview
from .settings import default_settings_path, get_agent_panel, set_agent_panel
from .subagent import panel_preview
from .themes import BAR_NAMES, THEME_NAMES, THEMES

SEPARATOR_PRESETS = [" | ", " · ", " │ ", " / ", "  "]

KEY_HELP = [
    "↑↓ select   space show/hide, pick or switch   ←→ change value   u/d move field",
    "t next theme   b next bar   l level   s/S separator   c colours   a agent panel   r reset",
    "enter save   q quit",
]

# Why the agent panel costs smoothness; shown next to its on/off switch.
AGENT_PANEL_NOTE = ("Claude Code runs this command on a fixed 5 s timer (not configurable) and the "
                    "row it returns replaces Claude Code's own, so while it is on the agent rows, "
                    "run time included, update every 5 s instead of every second.")

LINE_HELP = """commands:
  <n>        show or hide field n          u<n> / d<n>  move field n up / down
  t          next theme                    t<n>         pick theme n
  b          next bar style                b<n>         pick bar style n
  a          agent panel on / off       a<n>         the same as <n> for agent panel
                                          field n (ua<n> / da<n> to move it)
  l          cycle detail level            s            set separator
  c          colours on / off              r            reset to defaults
  w          save and exit                 q            quit without saving"""

REVERSE = "\033[7m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
HEADING = "\033[1;36m"
ON = "\033[32m"

# Fields of the small sample shown next to every theme.
THEME_SAMPLE_FIELDS = ["model", "context", "5h", "7d"]

Row = Tuple[str, object]  # (kind, key): field / theme / bar / level / separator / colors / agent / agent_field


def display_order(config: Config, agent: bool = False) -> List[str]:
    """Enabled fields in their order first, then the disabled ones."""
    enabled, every = (config.agent_fields, AGENT_FIELDS) if agent else (config.fields, FIELDS)
    return list(enabled) + [name for name in every if name not in enabled]


def highlight(text: str) -> str:
    """Reverse video that survives the colour resets inside `text`."""
    return REVERSE + text.replace(RESET, RESET + REVERSE) + RESET


def heading(title: str, hint: str, width: int) -> str:
    rule = "─" * max(2, min(width, 72) - len(title) - len(hint) - 6)
    return f"{HEADING}── {title} {rule}{RESET} {DIM}{hint}{RESET}"


def theme_sample(config: Config, name: str) -> str:
    """One row of the theme `name`, for its entry in the theme list."""
    sample = Config(level="minimal", fields=list(THEME_SAMPLE_FIELDS), theme=name,
                    separator=config.separator, colors=config.colors)
    lines = preview(sample).split("\n")
    return lines[len(lines) // 2]


def bar_sample(config: Config, name: str) -> str:
    """The context field drawn with bar style `name` in the current theme."""
    sample = Config(level="normal", fields=["context"], theme=config.theme, bar=name,
                    separator=config.separator, colors=config.colors)
    lines = preview(sample).split("\n")
    return lines[len(lines) // 2].split(" (")[0] + RESET  # the cut-off tail held the reset


class Editor:
    """Editing state shared by the full-screen and the line-based front ends."""

    def __init__(self, config: Config, agent_panel: bool = False):
        self.config = config
        self.agent_panel = agent_panel  # subagentStatusLine in settings.json, not in config
        # Stable order of all fields: toggling only flips the checkbox, u/d is what moves.
        self.order = display_order(config)
        self.agent_order = display_order(config, agent=True)
        self.cursor = 0  # index into rows()
        self.dirty = False
        self.message = ""
        self._quit_armed = False

    # --- rows the cursor runs over ---

    def rows(self) -> List[Row]:
        """Fields, themes, appearance settings, the agent panel switch and, while it is on,
        the agent panel's fields."""
        rows: List[Row] = [("field", i) for i in range(len(self.order))]
        rows += [("theme", name) for name in THEME_NAMES]
        rows += [("bar", name) for name in BAR_NAMES]
        rows += [("level", None)]
        if self.config.theme == "plain":  # the other themes draw their own joints
            rows.append(("separator", None))
        rows += [("colors", None), ("agent", None)]
        if self.agent_panel:
            rows += [("agent_field", i) for i in range(len(self.agent_order))]
        return rows

    def row_index(self, kind: str, key: object = None) -> int:
        return self.rows().index((kind, key))

    def current(self) -> Row:
        return self.rows()[self.cursor]

    # --- operations ---

    def _changed(self) -> None:
        self.dirty = True

    def _locate(self, index: Optional[int]):
        """Row index of a field -> (order, enabled names, setter of the enabled names, position)."""
        kind, position = self.rows()[self.cursor if index is None else index]
        if kind == "field":
            return self.order, self.config.fields, self._set_fields, position
        if kind == "agent_field":
            return self.agent_order, self.config.agent_fields, self._set_agent_fields, position
        return None

    def _set_fields(self, names: List[str]) -> None:
        self.config.fields = names

    def _set_agent_fields(self, names: List[str]) -> None:
        self.config.agent_fields = names

    def _total(self) -> int:
        return len(self.rows())

    def _sync(self, order: List[str], enabled: set, setter: Callable[[List[str]], None]) -> None:
        """Enabled fields, in the editor's order, become the config's fields."""
        setter([name for name in order if name in enabled])

    def move_cursor(self, step: int) -> None:
        self.cursor = (self.cursor + step) % self._total()

    def activate(self) -> None:
        """Space on the current row: show/hide a field, pick a theme, change a setting."""
        kind, key = self.current()
        if kind in ("field", "agent_field"):
            self.toggle()
        elif kind == "theme":
            self.set_theme(str(key))
        elif kind == "bar":
            self.set_bar(str(key))
        elif kind == "level":
            self.cycle_level(1)
        elif kind == "separator":
            self.next_separator()
        elif kind == "colors":
            self.toggle_colors()
        elif kind == "agent":
            self.toggle_agent_panel()

    def change(self, step: int) -> None:
        """←→ on the current row: the previous / next value of a setting or theme.

        On field rows it changes the detail level, the setting that matters most there.
        """
        kind, _ = self.current()
        if kind == "theme":
            self.cycle_theme(step)
            self.cursor = self.row_index("theme", self.config.theme)
        elif kind == "bar":
            self.cycle_bar(step)
            self.cursor = self.row_index("bar", self.config.bar)
        elif kind == "separator":
            self.next_separator(step)
        elif kind == "colors":
            self.toggle_colors()
        elif kind == "agent":
            self.toggle_agent_panel()
        else:
            self.cycle_level(step)

    def toggle(self, index: Optional[int] = None) -> None:
        located = self._locate(index)
        if located is None:
            if index is None:
                self.activate()
            return
        order, current, setter, position = located
        name = order[position]
        enabled = set(current)
        if name in enabled:
            if len(enabled) == 1:
                self.message = "at least one field must stay on"
                return
            enabled.remove(name)
        else:
            enabled.add(name)
        self._sync(order, enabled, setter)
        self._changed()

    def move(self, step: int, index: Optional[int] = None) -> None:
        located = self._locate(index)
        if located is None:
            return
        order, current, setter, i = located
        name = order[i]
        j = i + step
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            self._sync(order, set(current), setter)
            self._changed()
        if index is None:
            self.cursor += order.index(name) - i

    def cycle_level(self, step: int = 1) -> None:
        self.config.level = LEVELS[(LEVELS.index(self.config.level) + step) % len(LEVELS)]
        self._changed()

    def set_theme(self, name: str) -> None:
        if name != self.config.theme:
            here = self.current()
            self.config.theme = name
            rows = self.rows()  # the separator row exists for the plain theme only
            self.cursor = rows.index(here) if here in rows else min(self.cursor, len(rows) - 1)
            self._changed()

    def set_bar(self, name: str) -> None:
        if name != self.config.bar:
            self.config.bar = name
            self._changed()

    def cycle_bar(self, step: int = 1) -> None:
        index = BAR_NAMES.index(self.config.bar) if self.config.bar in BAR_NAMES else 0
        self.set_bar(BAR_NAMES[(index + step) % len(BAR_NAMES)])

    def cycle_theme(self, step: int = 1) -> None:
        index = THEME_NAMES.index(self.config.theme) if self.config.theme in THEME_NAMES else 0
        self.set_theme(THEME_NAMES[(index + step) % len(THEME_NAMES)])

    def next_separator(self, step: int = 1) -> None:
        current = self.config.separator
        index = SEPARATOR_PRESETS.index(current) if current in SEPARATOR_PRESETS else -1
        self.config.separator = SEPARATOR_PRESETS[(index + step) % len(SEPARATOR_PRESETS)]
        self._changed()

    def set_separator(self, text: str) -> None:
        self.config.separator = text or DEFAULT_SEPARATOR
        self._changed()

    def toggle_colors(self) -> None:
        self.config.colors = not self.config.colors
        self._changed()

    def toggle_agent_panel(self) -> None:
        self.agent_panel = not self.agent_panel
        if self.cursor >= self._total():  # its rows are hidden now
            self.cursor = self.row_index("agent")
        self._changed()

    def reset(self) -> None:
        defaults = Config()
        self.config.level, self.config.fields = defaults.level, defaults.fields
        self.config.separator, self.config.colors = defaults.separator, defaults.colors
        self.config.agent_fields, self.config.theme = defaults.agent_fields, defaults.theme
        self.config.bar = defaults.bar
        self.order = display_order(self.config)
        self.agent_order = display_order(self.config, agent=True)
        self.cursor = 0
        self._changed()

    # --- input ---

    def handle_key(self, key: str, ask: Callable[[str], str]) -> Optional[str]:
        """One key of the full-screen editor. Returns 'save', 'quit' or None."""
        self.message = ""
        if key in ("q", "esc", "ctrl-c"):
            if self.dirty and not self._quit_armed and key != "ctrl-c":
                self._quit_armed = True
                self.message = "unsaved changes: press q again to quit, enter to save"
                return None
            return "quit"
        self._quit_armed = False
        if key in ("enter", "w"):
            return "save"
        actions = {
            "up": lambda: self.move_cursor(-1), "k": lambda: self.move_cursor(-1),
            "down": lambda: self.move_cursor(1), "j": lambda: self.move_cursor(1),
            "space": self.activate, "x": self.activate,
            "u": lambda: self.move(-1), "shift-up": lambda: self.move(-1),
            "d": lambda: self.move(1), "shift-down": lambda: self.move(1),
            "left": lambda: self.change(-1), "right": lambda: self.change(1),
            "l": lambda: self.cycle_level(1),
            "t": lambda: self.cycle_theme(1),
            "b": lambda: self.cycle_bar(1),
            "s": self.next_separator,
            "S": lambda: self.set_separator(ask("separator (empty = default): ")),
            "c": self.toggle_colors,
            "a": self.toggle_agent_panel,
            "r": self.reset,
        }
        if key in actions:
            actions[key]()
        elif key.isdigit():
            agent = self.current()[0] == "agent_field"
            size = len(self.agent_order) if agent else len(self.order)
            if 1 <= int(key) <= size:
                self.cursor = self.row_index("agent_field" if agent else "field", int(key) - 1)
                self.toggle()
        return None

    def _line_index(self, text: str) -> Optional[int]:
        """'3' -> main bar field 3, 'a2' -> agent panel field 2, as row indexes."""
        agent = text.startswith("a")
        number = text[1:] if agent else text
        if not number.isdigit() or (agent and not self.agent_panel):
            return None
        index = int(number) - 1
        size = len(self.agent_order) if agent else len(self.order)
        if not 0 <= index < size:
            return None
        return self.row_index("agent_field" if agent else "field", index)

    def handle_line(self, command: str, ask: Callable[[str], str]) -> Optional[str]:
        """One text command of the line-based editor. Returns 'save', 'quit' or None."""
        self.message = ""
        if command == "w":
            return "save"
        if command == "q":
            return "quit"
        if command == "l":
            self.cycle_level(1)
        elif command == "c":
            self.toggle_colors()
        elif command == "s":
            self.set_separator(ask("separator (empty = default): "))
        elif command == "r":
            self.reset()
        elif command == "a":
            self.toggle_agent_panel()
        elif command == "t":
            self.cycle_theme(1)
        elif command == "b":
            self.cycle_bar(1)
        elif command[:1] == "b" and command[1:].isdigit():
            number = int(command[1:])
            if 1 <= number <= len(BAR_NAMES):
                self.set_bar(BAR_NAMES[number - 1])
            else:
                self.message = f"no bar style {number}"
        elif command[:1] == "t" and command[1:].isdigit():
            number = int(command[1:])
            if 1 <= number <= len(THEME_NAMES):
                self.set_theme(THEME_NAMES[number - 1])
            else:
                self.message = f"no theme {number}"
        elif command[:1] in ("u", "d") and self._line_index(command[1:]) is not None:
            self.move(-1 if command[0] == "u" else 1, self._line_index(command[1:]))
        elif self._line_index(command) is not None:
            self.toggle(self._line_index(command))
        elif command.lstrip("uda").isdigit():
            self.message = f"no field {command.lstrip('uda')}"
        else:
            self.message = f"unknown command: {command!r}"
        return None

    # --- output ---

    def _row(self, index: int, label: str, extra: str = "") -> str:
        """A selectable row: ▸ and reverse video under the cursor; `extra` stays unmarked."""
        if index == self.cursor:
            return f" {BOLD}▸{RESET} " + highlight(label) + extra
        return "   " + label + extra

    def _field_row(self, index: int, number: int, name: str, on: bool, description: str,
                   width: int) -> str:
        mark = f"{ON}●{RESET}" if on else f"{DIM}○{RESET}"
        text = f"{name:<8} {description}"
        text = text[: max(width - 12, 20)]
        body = f"{BOLD}{text[:8]}{RESET}{text[8:]}" if on else f"{DIM}{text}{RESET}"
        return self._row(index, f"{number:>2} {mark} {body}")

    def layout(self, width: int) -> Tuple[List[str], List[str], List[str], int]:
        """(header, body, footer, line of the cursor in body) of the full-screen editor."""
        cfg = self.config
        title = f"{BOLD}claude-statusline configure{RESET}"
        if self.dirty:
            title += f"  {DIM}(unsaved changes){RESET}"
        header = [title, "", f"{BOLD}Preview{RESET}"]
        header += ["  " + line for line in preview(cfg).split("\n")]
        if self.agent_panel:
            header += [f"{BOLD}Agent panel preview{RESET}",
                       "  " + panel_preview(cfg, min(width - 4, 100))]
        header.append("")

        body: List[str] = []
        cursor_line = 0
        rows = self.rows()

        def add(index: int, line: str) -> None:
            nonlocal cursor_line
            if index == self.cursor:
                cursor_line = len(body)
            body.append(line)

        body.append(heading("Fields", "space show/hide · u/d move", width))
        for i, name in enumerate(self.order):
            add(rows.index(("field", i)), self._field_row(
                rows.index(("field", i)), i + 1, name, name in cfg.fields,
                FIELD_DESCRIPTIONS[name], width))

        body += ["", heading("Theme", "space pick · ←→ / t next", width)]
        for name in THEME_NAMES:
            index = rows.index(("theme", name))
            mark = f"{ON}◉{RESET}" if name == cfg.theme else f"{DIM}○{RESET}"
            label = f"{mark} {BOLD if name == cfg.theme else ''}{name:<10}{RESET}"
            add(index, self._row(index, label, "  " + theme_sample(cfg, name)))
        shown = self.current()[1] if self.current()[0] == "theme" else cfg.theme
        theme = THEMES[str(shown)]
        note = theme.description
        body.append(f"     {DIM}{shown}: {note}{RESET}")

        body += ["", heading("Progress bar", "space pick · ←→ / b next", width)]
        for name in BAR_NAMES:
            index = rows.index(("bar", name))
            mark = f"{ON}◉{RESET}" if name == cfg.bar else f"{DIM}○{RESET}"
            label = f"{mark} {BOLD if name == cfg.bar else ''}{name:<10}{RESET}"
            add(index, self._row(index, label, "  " + bar_sample(cfg, name)))

        body += ["", heading("Appearance", "space or ←→ change", width)]
        level = f"◀ {cfg.level} ▶   {DIM}{' / '.join(LEVELS)}{RESET}"
        separator = f"{cfg.separator!r}   {DIM}S: type your own{RESET}"
        colours = f"{ON}● on{RESET}" if cfg.colors else f"{DIM}○ off{RESET}"
        for kind, label, value in (("level", "Level", level), ("separator", "Separator", separator),
                                   ("colors", "Colours", colours)):
            if (kind, None) not in rows:
                continue
            index = rows.index((kind, None))
            add(index, self._row(index, f"{label:<10}", " " + value))

        body += ["", heading("Agent panel", "rows of running subagents · space or a on/off", width)]
        index = rows.index(("agent", None))
        switch = f"{ON}● on{RESET}" if self.agent_panel else f"{DIM}○ off{RESET}"
        add(index, self._row(index, switch))
        body += [f"     {DIM}{part}{RESET}" for part in wrap(AGENT_PANEL_NOTE, min(width - 6, 90))]
        for i, name in enumerate(self.agent_order if self.agent_panel else []):
            index = rows.index(("agent_field", i))
            add(index, self._field_row(index, i + 1, name, name in cfg.agent_fields,
                                       AGENT_FIELD_DESCRIPTIONS[name], width))

        footer = [""] + [f"{DIM}{line}{RESET}" for line in KEY_HELP]
        if self.message:
            footer.append(f"{BOLD}{self.message}{RESET}")
        return header, body, footer, cursor_line

    def screen(self, width: int, height: Optional[int] = None) -> List[str]:
        """Lines of the full-screen editor; the list scrolls to keep the cursor in view."""
        header, body, footer, cursor_line = self.layout(width)
        if height is None or len(header) + len(body) + len(footer) <= height:
            return header + body + footer
        room = max(3, height - len(header) - len(footer))
        top = min(max(0, cursor_line - room // 2), len(body) - room)
        visible = body[top:top + room]
        if top > 0:
            visible[0] = f"   {DIM}▲ more{RESET}"
        if top + room < len(body):
            visible[-1] = f"   {DIM}▼ more{RESET}"
        return header + visible + footer


def wrap(text: str, width: int) -> List[str]:
    return textwrap.wrap(text, max(width, 20))


def save(editor: Editor, path: Path, settings_path: Path, out: Callable[[str], None]) -> Path:
    """Writes the config, and the agent panel switch to settings.json when it changed."""
    saved = config_module.save(editor.config, path)
    out(f"saved to {saved}")
    if editor.agent_panel != get_agent_panel(settings_path):
        try:
            set_agent_panel(settings_path, editor.agent_panel)
            out(f"agent panel: {'on' if editor.agent_panel else 'off'} (saved to {settings_path})")
        except ValueError as err:
            out(f"agent panel not changed: {err}")
    return saved


# --- terminal handling ---

KEYS = {
    "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
    "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left",
    "\x1b[1;2A": "shift-up", "\x1b[1;2B": "shift-down",
    "\x1b": "esc", " ": "space", "\r": "enter", "\n": "enter", "\x03": "ctrl-c",
}
WINDOWS_ARROWS = {"H": "up", "P": "down", "K": "left", "M": "right"}


def decode_key(sequence: str) -> str:
    """Raw characters of one key press -> key name (or the character itself)."""
    if sequence in KEYS:
        return KEYS[sequence]
    return sequence if len(sequence) == 1 else ""


class Terminal:
    """Single-key input and full-screen drawing: termios on POSIX, msvcrt on Windows."""

    def __enter__(self) -> "Terminal":
        if os.name == "nt":
            os.system("")  # turns on ANSI escape handling in the Windows console
        else:
            import termios
            import tty
            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        sys.stdout.write("\033[?1049h\033[?25l")  # alternate screen, hide cursor
        sys.stdout.flush()
        return self

    def __exit__(self, *exc) -> None:
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
        if os.name != "nt":
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)

    def read_key(self) -> str:
        if os.name == "nt":
            import msvcrt
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                return WINDOWS_ARROWS.get(msvcrt.getwch(), "")
            return decode_key(char)
        import select
        data = os.read(self._fd, 1)
        if data == b"\x1b":
            while len(data) < 8 and select.select([self._fd], [], [], 0.03)[0]:
                data += os.read(self._fd, 1)
        elif data and data[0] >= 0xC0:  # first byte of a multi-byte UTF-8 character
            while select.select([self._fd], [], [], 0)[0] and len(data) < 4:
                data += os.read(self._fd, 1)
        return decode_key(data.decode("utf-8", errors="ignore"))

    def draw(self, lines: List[str]) -> None:
        sys.stdout.write("\033[H\033[2J" + "\n".join(lines) + "\n")
        sys.stdout.flush()

    def ask(self, prompt: str) -> str:
        """Reads a line of text with normal echo, then returns to key mode."""
        if os.name != "nt":
            import termios
            import tty
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        try:
            return input(prompt)
        except EOFError:
            return ""
        finally:
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
            if os.name != "nt":
                tty.setcbreak(self._fd)


def _editor(path: Path, settings_path: Path) -> Editor:
    return Editor(copy.deepcopy(config_module.load(path)), get_agent_panel(settings_path))


def run_tui(path: Optional[Path] = None,
            settings_path: Optional[Path] = None) -> Optional[Path]:
    """Full-screen editor. Returns the path it saved to, or None when the user quit."""
    import shutil
    path = path or config_module.config_path()
    settings_path = settings_path or default_settings_path()
    editor = _editor(path, settings_path)
    result = None
    with Terminal() as term:
        try:
            while result is None:
                size = shutil.get_terminal_size()
                term.draw(editor.screen(size.columns, size.lines - 1))
                result = editor.handle_key(term.read_key(), term.ask)
        except KeyboardInterrupt:
            result = "quit"
    if result == "save":
        return save(editor, path, settings_path, print)
    print("not saved")
    return None


# --- line-based fallback ---

def show(editor: Editor, out: Callable[[str], None]) -> None:
    config = editor.config
    out("")
    out("preview:")
    for line in preview(config).split("\n"):
        out("  " + line)
    out("")
    out(f"level: {config.level}   colours: {'on' if config.colors else 'off'}"
        f"   separator: {config.separator!r}")
    out(f"bar: {config.bar}")
    out("bar styles (b<n> to pick): " + "  ".join(f"b{i}={n}" for i, n in enumerate(BAR_NAMES, 1)))
    out("themes (t<n> to pick):")
    for index, name in enumerate(THEME_NAMES, start=1):
        mark = "o" if name == config.theme else " "
        theme = THEMES[name]
        out(f"  t{index}. ({mark}) {name:<10} {theme.description}")
    out("fields:")
    for index, name in enumerate(editor.order, start=1):
        mark = "x" if name in config.fields else " "
        out(f"  {index}. [{mark}] {name:<8} {FIELD_DESCRIPTIONS[name]}")
    out(f"agent panel: {'on' if editor.agent_panel else 'off'} (a: on/off)")
    for part in wrap(AGENT_PANEL_NOTE, 96):
        out("  " + part)
    if not editor.agent_panel:
        out("")
        out(LINE_HELP)
        return
    out("  " + panel_preview(config))
    for index, name in enumerate(editor.agent_order, start=1):
        mark = "x" if name in config.agent_fields else " "
        out(f"  a{index}. [{mark}] {name:<8} {AGENT_FIELD_DESCRIPTIONS[name]}")
    out("")
    out(LINE_HELP)


def apply(config: Config, command: str, ask: Callable[[str], str],
          out: Callable[[str], None]) -> Optional[str]:
    """Applies one text command to `config`. Returns 'save', 'quit' or None."""
    editor = Editor(config)
    result = editor.handle_line(command, ask)
    if editor.message:
        out(editor.message)
    return result


def run(path: Optional[Path] = None, ask: Callable[[str], str] = input,
        out: Callable[[str], None] = print,
        settings_path: Optional[Path] = None) -> Optional[Path]:
    """Line-based editor. Returns the path it saved to, or None when the user quit."""
    path = path or config_module.config_path()
    settings_path = settings_path or default_settings_path()
    editor = _editor(path, settings_path)
    while True:
        show(editor, out)
        try:
            command = ask("> ").strip()
        except EOFError:
            command = "q"
        result = editor.handle_line(command, ask)
        if editor.message:
            out(editor.message)
        if result == "save":
            return save(editor, path, settings_path, out)
        if result == "quit":
            out("not saved")
            return None


def main(path: Optional[Path] = None) -> Optional[Path]:
    """Full-screen editor in a terminal, line-based otherwise."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        return run_tui(path)
    return run(path)
