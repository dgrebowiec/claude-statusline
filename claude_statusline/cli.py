"""Command line entry point.

    claude-statusline                 read Claude Code's JSON on stdin, print the status line
    claude-statusline configure       interactive editor with a live preview
    claude-statusline config ...      set options directly (see --help)
    claude-statusline preview         print a sample line with the current settings
    claude-statusline subagent        lines for Claude Code's subagentStatusLine (JSON on stdin)
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
from .render import colours_enabled, DEFAULT_CACHE_DIR, DEFAULT_PROJECTS_DIR, preview, render
from .subagent import subagent_lines
from .themes import BAR_NAMES, THEME_NAMES
from .settings import (MIN_REFRESH, default_settings_path, get_agent_panel, get_refresh, install,
                       set_agent_panel, set_refresh, uninstall)


def _parse_fields(value: str) -> List[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in FIELDS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown field(s): {', '.join(unknown)} (choose from {', '.join(FIELDS)})")
    return names


def _parse_refresh(value: str) -> int:
    """Seconds (at least MIN_REFRESH), or 0 / "off" for event-driven updates only."""
    if value.strip().lower() in ("0", "off"):
        return 0
    try:
        seconds = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {value!r}")
    if seconds < MIN_REFRESH:
        raise argparse.ArgumentTypeError(f"at least {MIN_REFRESH} s, or 0/off to turn it off")
    return seconds


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude-statusline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("configure", help="interactive editor with a live preview")
    sub.add_parser("preview", help="print a sample line with the current settings")
    sub.add_parser("subagent", help="share of the 5 h limit per subagent, for "
                                    "subagentStatusLine (JSON on stdin)")
    sub.add_parser("install", help="set statusLine in settings.json (keeps a backup)")
    sub.add_parser("uninstall", help="remove the statusLine entry if it is ours")

    cfg = sub.add_parser("config", help="change options without the editor")
    cfg.add_argument("--level", choices=LEVELS, help="detail level")
    cfg.add_argument("--fields", type=_parse_fields,
                     help="comma-separated fields in display order, e.g. model,context,5h,7d; "
                          f"available: {', '.join(FIELDS)}")
    cfg.add_argument("--theme", choices=THEME_NAMES,
                     help="how fields are drawn: plain text, filled blocks (blocks, slant, fade) "
                          "or coloured borders (boxes)")
    cfg.add_argument("--bar", choices=BAR_NAMES,
                     help="style of the context progress bar (auto: ascii on plain, bricks on "
                          "the filled themes)")
    cfg.add_argument("--separator", help='text between fields (plain theme), e.g. " · "')
    cfg.add_argument("--colors", choices=["on", "off"])
    cfg.add_argument("--refresh", type=_parse_refresh, metavar="SECONDS",
                     help=f"re-run the status line every SECONDS (at least {MIN_REFRESH}) besides "
                          "Claude Code's own updates, so subagent work shows up while it "
                          "happens; 0 or off: only on Claude Code's updates. Stored as "
                          "statusLine.refreshInterval in ~/.claude/settings.json")
    cfg.add_argument("--agent-panel", choices=["on", "off"],
                     help="add each running subagent's 5 h share to its row in Claude Code's "
                          "agent panel (subagentStatusLine). Claude Code then redraws those "
                          "rows every 5 s instead of every second")
    cfg.add_argument("--show", action="store_true", help="print the current settings as JSON")
    cfg.add_argument("--reset", action="store_true", help="restore the defaults")
    return parser


def _refresh_command(seconds: int) -> None:
    path = default_settings_path()
    try:
        set_refresh(path, seconds or None)
    except ValueError as err:
        sys.exit(f"claude-statusline: {err}")
    state = f"every {seconds} s" if seconds else "only on Claude Code's updates"
    print(f"status line refresh: {state} (saved to {path})")


def _agent_panel_command(on: bool) -> None:
    path = default_settings_path()
    try:
        set_agent_panel(path, on)
    except ValueError as err:
        sys.exit(f"claude-statusline: {err}")
    print(f"agent panel: {'on' if on else 'off'} (saved to {path})")


def _config_command(args: argparse.Namespace) -> None:
    if args.refresh is not None:
        _refresh_command(args.refresh)
    if args.agent_panel:
        _agent_panel_command(args.agent_panel == "on")
    if args.refresh is not None or args.agent_panel:
        if not any((args.level, args.fields, args.theme, args.bar, args.separator is not None, args.colors,
                    args.reset, args.show)):
            return
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
    if args.theme:
        config.theme, changed = args.theme, True
    if args.bar:
        config.bar, changed = args.bar, True
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
        refresh = get_refresh(default_settings_path())
        print(f"refresh: every {refresh} s" if refresh else "refresh: only on Claude Code's updates")
        print(f"agent panel: {'on' if get_agent_panel(default_settings_path()) else 'off'}")


def _read_stdin() -> Dict[str, Any]:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _render_stdin() -> str:
    return render(_read_stdin())


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command is None:
        print(_render_stdin())
    elif args.command == "configure":
        run_configure()
    elif args.command == "subagent":
        settings = config_module.load()
        for line in subagent_lines(_read_stdin(), DEFAULT_PROJECTS_DIR, DEFAULT_CACHE_DIR,
                                   colors=colours_enabled(settings), config=settings):
            print(line)
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
