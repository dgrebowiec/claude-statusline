"""Command line entry point: `claude-statusline` renders, `install` / `uninstall` edit settings."""
import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .render import render
from .settings import default_settings_path, install, uninstall

USAGE = """usage: claude-statusline [command]

  (no command)   read Claude Code's status JSON from stdin and print the status line
  install        set statusLine in ~/.claude/settings.json (keeps a backup)
  uninstall      remove statusLine, if it points to claude-statusline
  --version      print the version
"""


def _render_stdin() -> str:
    raw = sys.stdin.read()
    try:
        payload: Dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    return render(payload)


def main(argv: Optional[List[str]] = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(_render_stdin())
        return
    command = args[0]
    if command in ("-h", "--help", "help"):
        print(USAGE, end="")
    elif command in ("-V", "--version"):
        print(__version__)
    elif command == "install":
        path = default_settings_path()
        backup = install(path)
        print(f"statusLine ustawiony w {path}")
        if backup:
            print(f"kopia poprzedniej wersji: {backup}")
    elif command == "uninstall":
        path = default_settings_path()
        if uninstall(path):
            print(f"statusLine usunięty z {path}")
        else:
            print("nic do usunięcia (statusLine nie wskazuje na claude-statusline)")
    else:
        sys.stderr.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    main()
