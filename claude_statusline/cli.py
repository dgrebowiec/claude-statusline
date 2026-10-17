"""Command line entry point.

    claude-statusline                 read Claude Code's JSON on stdin, print the status line
    claude-statusline configure       interactive editor with a live preview
    claude-statusline config ...      set options directly (see --help)
    claude-statusline preview         print a sample line with the current settings
    claude-statusline install         set statusLine in ~/.claude/settings.json
    claude-statusline uninstall       remove that statusLine entry again
"""
import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from . import config as config_module
from .config import FIELDS, LEVELS, Config
from .configure import main as run_configure
from .render import preview, render
from .settings import default_settings_path, install, uninstall


def _parse_fields(value: str) -> List[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in FIELDS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown field(s): {', '.join(unknown)} (choose from {', '.join(FIELDS)})")
    return names


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude-statusline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("configure", help="interactive editor with a live preview")
    sub.add_parser("preview", help="print a sample line with the current settings")
    sub.add_parser("install", help="set statusLine in settings.json (keeps a backup)")
    sub.add_parser("uninstall", help="remove the statusLine entry if it is ours")

    cfg = sub.add_parser("config", help="change options without the editor")
    cfg.add_argument("--level", choices=LEVELS, help="detail level")
    cfg.add_argument("--fields", type=_parse_fields,
                     help="comma-separated fields in display order, e.g. model,context,5h,7d")
    cfg.add_argument("--separator", help='text between fields, e.g. " · "')
    cfg.add_argument("--colors", choices=["on", "off"])
    cfg.add_argument("--show", action="store_true", help="print the current settings as JSON")
    cfg.add_argument("--reset", action="store_true", help="restore the defaults")
    return parser


def _config_command(args: argparse.Namespace) -> None:
    path = config_module.config_path()
    if args.reset:
        config = Config()
    else:
        config = config_module.load(path)
    changed = False
    if args.level:
        config.level, changed = args.level, True
    if args.fields:
        config.fields, changed = args.fields, True
    if args.separator is not None:
        config.separator, changed = args.separator, True
    if args.colors:
        config.colors, changed = args.colors == "on", True
    if args.reset:
        changed = True
    if changed:
        saved = config_module.save(config, path)
        print(f"saved to {saved}")
    if args.show or not changed:
        print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))


def _render_stdin() -> str:
    raw = sys.stdin.read()
    try:
        payload: Dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    return render(payload)


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command is None:
        print(_render_stdin())
    elif args.command == "configure":
        run_configure()
    elif args.command == "preview":
        print(preview(config_module.load()))
    elif args.command == "config":
        _config_command(args)
    elif args.command == "install":
        path = default_settings_path()
        backup = install(path)
        print(f"statusLine set in {path}")
        if backup:
            print(f"previous settings backed up to {backup}")
    elif args.command == "uninstall":
        path = default_settings_path()
        if uninstall(path):
            print(f"statusLine removed from {path}")
        else:
            print("nothing to remove (statusLine does not point to claude-statusline)")


if __name__ == "__main__":
    main()
