"""Interactive configurator: toggle and reorder fields, pick a level, and see the result live."""
import copy
from pathlib import Path
from typing import Callable, List, Optional

from . import config as config_module
from .config import FIELD_DESCRIPTIONS, FIELDS, LEVELS, Config
from .render import preview

HELP = """commands:
  <n>        show or hide field n          u<n> / d<n>  move enabled field n up / down
  l          cycle detail level            s            set separator
  c          colours on / off              r            reset to defaults
  w          save and exit                 q            quit without saving"""


def display_order(config: Config) -> List[str]:
    """Enabled fields in their order first, then the disabled ones."""
    return list(config.fields) + [name for name in FIELDS if name not in config.fields]


def show(config: Config, out: Callable[[str], None]) -> None:
    out("")
    out("preview:")
    out("  " + preview(config))
    out("")
    out(f"level: {config.level}   colours: {'on' if config.colors else 'off'}"
        f"   separator: {config.separator!r}")
    for index, name in enumerate(display_order(config), start=1):
        mark = "x" if name in config.fields else " "
        out(f"  {index}. [{mark}] {name:<8} {FIELD_DESCRIPTIONS[name]}")
    out("")
    out(HELP)


def apply(config: Config, command: str, ask: Callable[[str], str],
          out: Callable[[str], None]) -> Optional[str]:
    """Applies one command. Returns 'save', 'quit' or None to keep going."""
    if command == "w":
        return "save"
    if command == "q":
        return "quit"
    if command == "l":
        config.level = LEVELS[(LEVELS.index(config.level) + 1) % len(LEVELS)]
    elif command == "c":
        config.colors = not config.colors
    elif command == "s":
        config.separator = ask("separator (empty = default): ") or config_module.DEFAULT_SEPARATOR
    elif command == "r":
        defaults = Config()
        config.level, config.fields = defaults.level, defaults.fields
        config.separator, config.colors = defaults.separator, defaults.colors
    elif command[:1] in ("u", "d") and command[1:].isdigit():
        index = int(command[1:]) - 1
        if not 0 <= index < len(config.fields):
            out("only enabled fields can be moved")
            return None
        target = index - 1 if command[0] == "u" else index + 1
        if 0 <= target < len(config.fields):
            config.fields[index], config.fields[target] = config.fields[target], config.fields[index]
    elif command.isdigit():
        index = int(command) - 1
        order = display_order(config)
        if not 0 <= index < len(order):
            out(f"no field {command}")
            return None
        name = order[index]
        if name in config.fields:
            if len(config.fields) == 1:
                out("at least one field must stay on")
                return None
            config.fields.remove(name)
        else:
            config.fields.append(name)
    else:
        out(f"unknown command: {command!r}")
    return None


def run(path: Optional[Path] = None, ask: Callable[[str], str] = input,
        out: Callable[[str], None] = print) -> Optional[Path]:
    """Runs the editor. Returns the path it saved to, or None when the user quit."""
    path = path or config_module.config_path()
    config = copy.deepcopy(config_module.load(path))
    while True:
        show(config, out)
        result = apply(config, ask("> ").strip(), ask, out)
        if result == "save":
            saved = config_module.save(config, path)
            out(f"saved to {saved}")
            return saved
        if result == "quit":
            out("not saved")
            return None
