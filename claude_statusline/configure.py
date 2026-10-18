"""Interactive configurator with a live preview.

In a terminal it is a full-screen editor driven by keys (arrows, space, enter). When stdin is
not a terminal (pipes, tests) it falls back to one text command per line.
"""
import copy
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

from . import config as config_module
from .config import (AGENT_FIELD_DESCRIPTIONS, AGENT_FIELDS, DEFAULT_SEPARATOR, FIELD_DESCRIPTIONS,
                     FIELDS, LEVELS, Config)
from .render import preview
from .subagent import panel_preview

SEPARATOR_PRESETS = [" | ", " · ", " │ ", " / ", "  "]

KEY_HELP = ("↑↓ select   space show/hide   u/d move   ←→ level   "
            "s separator   S custom separator   c colours   r reset   enter save   q quit")

LINE_HELP = """commands:
  <n>        show or hide field n          u<n> / d<n>  move field n up / down
  a<n>       the same for agent panel field n (ua<n> / da<n> to move it)
  l          cycle detail level            s            set separator
  c          colours on / off              r            reset to defaults
  w          save and exit                 q            quit without saving"""

REVERSE = "\033[7m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def display_order(config: Config, agent: bool = False) -> List[str]:
    """Enabled fields in their order first, then the disabled ones."""
    enabled, every = (config.agent_fields, AGENT_FIELDS) if agent else (config.fields, FIELDS)
    return list(enabled) + [name for name in every if name not in enabled]


class Editor:
    """Editing state shared by the full-screen and the line-based front ends."""

    def __init__(self, config: Config):
        self.config = config
        # Stable order of all fields: toggling only flips the checkbox, u/d is what moves.
        # The cursor runs over the main bar's fields, then over the agent panel's.
        self.order = display_order(config)
        self.agent_order = display_order(config, agent=True)
        self.cursor = 0
        self.dirty = False
        self.message = ""
        self._quit_armed = False

    # --- operations ---

    def _changed(self) -> None:
        self.dirty = True

    def _locate(self, index: Optional[int]):
        """Cursor index -> (order, enabled names, setter of the enabled names, position)."""
        index = self.cursor if index is None else index
        if index < len(self.order):
            return self.order, self.config.fields, self._set_fields, index
        return (self.agent_order, self.config.agent_fields, self._set_agent_fields,
                index - len(self.order))

    def _set_fields(self, names: List[str]) -> None:
        self.config.fields = names

    def _set_agent_fields(self, names: List[str]) -> None:
        self.config.agent_fields = names

    def _total(self) -> int:
        return len(self.order) + len(self.agent_order)

    def _sync(self, order: List[str], enabled: set, setter: Callable[[List[str]], None]) -> None:
        """Enabled fields, in the editor's order, become the config's fields."""
        setter([name for name in order if name in enabled])

    def move_cursor(self, step: int) -> None:
        self.cursor = (self.cursor + step) % self._total()

    def toggle(self, index: Optional[int] = None) -> None:
        order, current, setter, position = self._locate(index)
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
        order, current, setter, i = self._locate(index)
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

    def next_separator(self) -> None:
        current = self.config.separator
        index = SEPARATOR_PRESETS.index(current) if current in SEPARATOR_PRESETS else -1
        self.config.separator = SEPARATOR_PRESETS[(index + 1) % len(SEPARATOR_PRESETS)]
        self._changed()

    def set_separator(self, text: str) -> None:
        self.config.separator = text or DEFAULT_SEPARATOR
        self._changed()

    def toggle_colors(self) -> None:
        self.config.colors = not self.config.colors
        self._changed()

    def reset(self) -> None:
        defaults = Config()
        self.config.level, self.config.fields = defaults.level, defaults.fields
        self.config.separator, self.config.colors = defaults.separator, defaults.colors
        self.config.agent_fields = defaults.agent_fields
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
            "space": self.toggle, "x": self.toggle,
            "u": lambda: self.move(-1), "shift-up": lambda: self.move(-1),
            "d": lambda: self.move(1), "shift-down": lambda: self.move(1),
            "left": lambda: self.cycle_level(-1), "right": lambda: self.cycle_level(1),
            "l": lambda: self.cycle_level(1),
            "s": self.next_separator,
            "S": lambda: self.set_separator(ask("separator (empty = default): ")),
            "c": self.toggle_colors,
            "r": self.reset,
        }
        if key in actions:
            actions[key]()
        elif key.isdigit() and 1 <= int(key) <= len(self._locate(None)[0]):
            start = 0 if self.cursor < len(self.order) else len(self.order)
            self.cursor = start + int(key) - 1
            self.toggle()
        return None

    def _line_index(self, text: str) -> Optional[int]:
        """'3' -> main bar field 3, 'a2' -> agent panel field 2, as cursor indexes."""
        agent = text.startswith("a")
        number = text[1:] if agent else text
        if not number.isdigit():
            return None
        index = int(number) - 1
        size = len(self.agent_order) if agent else len(self.order)
        if not 0 <= index < size:
            return None
        return index + (len(self.order) if agent else 0)

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

    def screen(self, width: int) -> List[str]:
        """Lines of the full-screen editor."""
        cfg = self.config
        title = f"{BOLD}claude-statusline configure{RESET}"
        if self.dirty:
            title += f"  {DIM}(unsaved changes){RESET}"
        lines = [title, "", f"{BOLD}Fields{RESET}  {DIM}space: show/hide   u/d: move{RESET}"]
        for index, name in enumerate(self.order):
            mark = "x" if name in cfg.fields else " "
            row = f" {index + 1}. [{mark}] {name:<8} {FIELD_DESCRIPTIONS[name]}"
            row = row.ljust(min(width - 2, 60))
            lines.append(f" {REVERSE}{row}{RESET}" if index == self.cursor else f" {row}")
        lines += ["", f"{BOLD}Agent panel{RESET}  {DIM}rows of running subagents below the prompt"
                      f" (claude-statusline config --agent-panel on){RESET}"]
        for index, name in enumerate(self.agent_order):
            mark = "x" if name in cfg.agent_fields else " "
            row = f" {index + 1}. [{mark}] {name:<8} {AGENT_FIELD_DESCRIPTIONS[name]}"
            row = row.ljust(min(width - 2, 60))
            at = len(self.order) + index == self.cursor
            lines.append(f" {REVERSE}{row}{RESET}" if at else f" {row}")
        lines += [
            "",
            f"{BOLD}Level{RESET}      ◀ {cfg.level} ▶   {DIM}{' / '.join(LEVELS)}{RESET}",
            f"{BOLD}Separator{RESET}  {cfg.separator!r}",
            f"{BOLD}Colours{RESET}    {'on' if cfg.colors else 'off'}",
            "",
            f"{BOLD}Preview{RESET}",
            "  " + preview(cfg),
            "",
            f"{BOLD}Agent panel preview{RESET}",
            "  " + panel_preview(cfg, min(width - 4, 100)),
            "",
            f"{DIM}{KEY_HELP}{RESET}",
        ]
        if self.message:
            lines.append(f"{BOLD}{self.message}{RESET}")
        return lines


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


def run_tui(path: Optional[Path] = None) -> Optional[Path]:
    """Full-screen editor. Returns the path it saved to, or None when the user quit."""
    import shutil
    path = path or config_module.config_path()
    editor = Editor(copy.deepcopy(config_module.load(path)))
    result = None
    with Terminal() as term:
        try:
            while result is None:
                term.draw(editor.screen(shutil.get_terminal_size().columns))
                result = editor.handle_key(term.read_key(), term.ask)
        except KeyboardInterrupt:
            result = "quit"
    if result == "save":
        saved = config_module.save(editor.config, path)
        print(f"saved to {saved}")
        return saved
    print("not saved")
    return None


# --- line-based fallback ---

def show(editor: Editor, out: Callable[[str], None]) -> None:
    config = editor.config
    out("")
    out("preview:")
    out("  " + preview(config))
    out("")
    out(f"level: {config.level}   colours: {'on' if config.colors else 'off'}"
        f"   separator: {config.separator!r}")
    for index, name in enumerate(editor.order, start=1):
        mark = "x" if name in config.fields else " "
        out(f"  {index}. [{mark}] {name:<8} {FIELD_DESCRIPTIONS[name]}")
    out("agent panel:  " + panel_preview(config))
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
        out: Callable[[str], None] = print) -> Optional[Path]:
    """Line-based editor. Returns the path it saved to, or None when the user quit."""
    path = path or config_module.config_path()
    editor = Editor(copy.deepcopy(config_module.load(path)))
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
            saved = config_module.save(editor.config, path)
            out(f"saved to {saved}")
            return saved
        if result == "quit":
            out("not saved")
            return None


def main(path: Optional[Path] = None) -> Optional[Path]:
    """Full-screen editor in a terminal, line-based otherwise."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        return run_tui(path)
    return run(path)
