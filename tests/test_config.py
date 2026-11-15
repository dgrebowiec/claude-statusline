import io

from claude_statusline import cli
from claude_statusline import config as config_module
from claude_statusline.config import Config, from_dict
from claude_statusline.configure import apply, display_order, run


def test_from_dict_falls_back_per_key():
    cfg = from_dict({"level": "huge", "fields": ["model", "bogus", "model", "5h"],
                     "separator": 5, "colors": "yes"})
    assert cfg.level == "normal"
    assert cfg.fields == ["model", "5h"]
    assert cfg.separator == " | " and cfg.colors is True


def test_from_dict_non_dict_is_default():
    assert from_dict(["not", "a", "dict"]) == Config()


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "c.json"
    original = Config(level="minimal", fields=["context", "7d"], separator=" · ", colors=False)
    config_module.save(original, path)
    assert config_module.load(path) == original


def test_load_missing_file_gives_defaults(tmp_path):
    assert config_module.load(tmp_path / "none.json") == Config()


def test_configurator_toggle_move_level_and_save(tmp_path):
    path = tmp_path / "c.json"
    answers = iter(["1", "d1", "l", "w"])  # hide model, move it down, level, save
    out = []
    saved = run(path, ask=lambda prompt: next(answers), out=out.append,
                settings_path=tmp_path / "settings.json")
    assert saved == path
    cfg = config_module.load(path)
    assert "model" not in cfg.fields
    assert cfg.fields[0] == "effort"  # model (hidden) moved below effort
    assert cfg.level == "detailed"


def test_configurator_quit_does_not_save(tmp_path):
    path = tmp_path / "c.json"
    answers = iter(["1", "q"])
    assert run(path, ask=lambda prompt: next(answers), out=lambda s: None,
               settings_path=tmp_path / "settings.json") is None
    assert not path.exists()


def test_configurator_keeps_at_least_one_field():
    cfg = Config(fields=["model"])
    apply(cfg, "1", ask=input, out=lambda s: None)
    assert cfg.fields == ["model"]


def test_configurator_separator_and_reset():
    cfg = Config()
    apply(cfg, "s", ask=lambda prompt: " · ", out=lambda s: None)
    assert cfg.separator == " · "
    apply(cfg, "r", ask=input, out=lambda s: None)
    assert cfg == Config()


def test_display_order_lists_disabled_fields_last():
    cfg = Config(fields=["7d", "model"])
    assert display_order(cfg)[:2] == ["7d", "model"]
    assert set(display_order(cfg)) == set(config_module.FIELDS)


def test_cli_config_sets_and_validates(tmp_path, monkeypatch, capsys):
    path = tmp_path / "c.json"
    monkeypatch.setenv("CLAUDE_STATUSLINE_CONFIG", str(path))
    cli.main(["config", "--level", "minimal", "--fields", "model,5h", "--separator", " · "])
    assert config_module.load(path) == Config(level="minimal", fields=["model", "5h"],
                                              separator=" · ")
    cli.main(["config", "--reset"])
    assert config_module.load(path) == Config()


def test_cli_config_rejects_unknown_field(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_STATUSLINE_CONFIG", str(tmp_path / "c.json"))
    try:
        cli.main(["config", "--fields", "model,nope"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("unknown field accepted")


def test_cli_preview_prints_a_line(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CLAUDE_STATUSLINE_CONFIG", str(tmp_path / "c.json"))
    cli.main(["preview"])
    assert "Opus 5.5" in capsys.readouterr().out


# --- full-screen editor: key handling ---

from claude_statusline.configure import Editor, decode_key  # noqa: E402


def _press(editor, *keys, ask=lambda prompt: ""):
    result = None
    for key in keys:
        result = editor.handle_key(key, ask)
    return result


def test_decode_key_arrows_and_specials():
    assert decode_key("\x1b[A") == "up"
    assert decode_key("\x1bOB") == "down"
    assert decode_key("\x1b[1;2A") == "shift-up"
    assert decode_key(" ") == "space"
    assert decode_key("\n") == "enter"
    assert decode_key("q") == "q"
    assert decode_key("\x1b[99~") == ""


def test_editor_toggle_keeps_row_and_cursor_in_place():
    editor = Editor(Config())
    order_before = list(editor.order)
    _press(editor, "down", "space")  # hide "effort"
    assert "effort" not in editor.config.fields
    assert editor.order == order_before and editor.cursor == 1
    _press(editor, "space")  # show it again: back in the same place
    assert editor.config.fields == Config().fields
    assert editor.order == order_before and editor.cursor == 1


def test_editor_can_move_a_hidden_field_and_it_keeps_its_place():
    editor = Editor(Config())
    _press(editor, "space")  # hide "model" (row 1)
    _press(editor, "d", "d")  # move it below "skill" while hidden
    assert editor.order[:3] == ["effort", "skill", "model"] and editor.cursor == 2
    _press(editor, "space")  # turn it back on
    assert editor.config.fields[:3] == ["effort", "skill", "model"]


def test_editor_move_and_level_with_arrows():
    editor = Editor(Config())
    _press(editor, "d")  # move "model" down
    assert editor.config.fields[:2] == ["effort", "model"]
    assert editor.cursor == 1
    _press(editor, "right")
    assert editor.config.level == "detailed"
    _press(editor, "left", "left")
    assert editor.config.level == "minimal"


def test_editor_separator_presets_and_custom():
    editor = Editor(Config())
    _press(editor, "s")
    assert editor.config.separator == " · "
    _press(editor, "S", ask=lambda prompt: " >> ")
    assert editor.config.separator == " >> "


def test_editor_quit_asks_twice_when_dirty():
    editor = Editor(Config())
    assert _press(editor, "q") == "quit"  # nothing changed: quits at once
    editor = Editor(Config())
    _press(editor, "c")
    assert _press(editor, "q") is None and "unsaved" in editor.message
    assert _press(editor, "q") == "quit"


def test_editor_enter_saves_and_digits_toggle():
    editor = Editor(Config())
    assert _press(editor, "8") is None  # toggle field 8 ("share")
    assert "share" not in editor.config.fields
    assert _press(editor, "enter") == "save"


def test_editor_screen_shows_preview_and_cursor():
    editor = Editor(Config())
    lines = editor.screen(100)
    assert any("Opus 5.5" in line for line in lines)
    assert any("\033[7m" in line for line in lines)  # highlighted row


# --- themes ---

from claude_statusline.render import preview  # noqa: E402
from claude_statusline.themes import THEME_NAMES, visible_len  # noqa: E402


def test_unknown_theme_falls_back_to_plain():
    assert from_dict({"theme": "neon"}).theme == "plain"
    assert from_dict({"theme": "arrows"}).theme == "plain"  # a removed theme
    assert from_dict({"theme": "slant"}).theme == "slant"


def test_every_theme_renders_and_keeps_the_text():
    for name in THEME_NAMES:
        line = preview(Config(theme=name))
        assert "Opus 5.5" in line and "5h" in line, name


def test_filled_themes_colour_the_background_by_state():
    line = preview(Config(theme="blocks"))
    assert "\033[48;5;178" in line  # 5h at 72%: yellow block
    assert "\033[48;5;106" in line  # context at 42%: yellow-green block
    assert "\033[48;5;160" in line  # 7d at 96%: red block
    assert "\033[32m" not in line   # text inside the blocks is not coloured on its own


def test_filled_themes_fall_back_to_plain_without_colours():
    line = preview(Config(theme="slant", colors=False))
    assert "\033[" not in line and " | " in line and "" not in line


def test_boxes_draw_three_rows_of_equal_width():
    rows = preview(Config(theme="boxes", colors=False)).split("\n")
    assert len(rows) == 3 and rows[0].startswith("╭") and rows[2].startswith("╰")
    assert len({visible_len(row) for row in rows}) == 1


def test_editor_picks_themes_with_space_arrows_and_t():
    editor = Editor(Config())
    editor.cursor = editor.row_index("theme", "slant")
    _press(editor, "space")
    assert editor.config.theme == "slant"
    _press(editor, "right")
    assert editor.config.theme == "fade" and editor.current() == ("theme", "fade")
    _press(editor, "t")
    assert editor.config.theme == "boxes"
    assert editor.handle_line("t1", input) is None and editor.config.theme == "plain"
    assert editor.handle_line("t99", input) is None and editor.message == "no theme 99"


def test_separator_row_only_in_plain_theme():
    editor = Editor(Config())
    assert ("separator", None) in editor.rows()
    editor.cursor = editor.row_index("colors")
    editor.set_theme("slant")
    assert ("separator", None) not in editor.rows() and editor.current() == ("colors", None)
    assert "Separator" not in "\n".join(editor.screen(100))


def test_progress_bar_styles():
    line = preview(Config(theme="blocks", fields=["context"], colors=True))
    assert "▮" in line and "▯" in line and "[" not in line.replace("\033[", "")
    line = preview(Config(theme="blocks", fields=["context"], colors=True, bar="dots"))
    assert "●" in line and "○" in line
    line = preview(Config(theme="plain", fields=["context"], colors=False))
    assert "[" in line and "#" in line
    line = preview(Config(theme="plain", fields=["context"], colors=False, bar="line"))
    assert "━" in line and "[" not in line
    assert from_dict({"bar": "nope"}).bar == "auto" and from_dict({"bar": "dots"}).bar == "dots"
    editor = Editor(Config())
    editor.cursor = editor.row_index("bar", "line")
    _press(editor, "space")
    assert editor.config.bar == "line"
    _press(editor, "b")
    assert editor.config.bar == "auto"
    assert editor.handle_line("b3", input) is None and editor.config.bar == "bricks"


def test_editor_appearance_rows_change_with_arrows():
    editor = Editor(Config())
    editor.cursor = editor.row_index("separator")
    _press(editor, "right")
    assert editor.config.separator == " · "
    editor.cursor = editor.row_index("colors")
    _press(editor, "space")
    assert editor.config.colors is False


def test_editor_screen_scrolls_to_keep_the_cursor_in_view():
    editor = Editor(Config(), agent_panel=True)
    editor.cursor = editor._total() - 1
    lines = editor.screen(100, 30)
    assert len(lines) <= 30
    assert any("▲ more" in line for line in lines)
    assert any("▸" in line for line in lines)


# --- progress bars on the limits, fill colours ---

def test_bars_and_level_colors_defaults_and_parsing():
    assert Config().bars == ["context"] and Config().level_colors is True
    assert from_dict({"bars": []}).bars == []  # no bars at all is a valid choice
    assert from_dict({"bars": ["7d", "nope", "context"]}).bars == ["context", "7d"]
    assert from_dict({"bars": "x", "level_colors": "x"}) == Config()


def test_limit_bars_follow_the_config():
    plain = preview(Config(colors=False))
    assert "] 42%" in plain and "5h: 72%" in plain
    both = preview(Config(colors=False, bars=["5h", "7d"]))
    assert "5h: [" in both and "7d: [" in both and "] 42%" not in both
    assert "[" not in preview(Config(colors=False, level="minimal", bars=["context", "5h"]))


def test_level_colors_off_paints_percentages_in_one_colour():
    on, off = preview(Config()), preview(Config(level_colors=False))
    assert "\033[31m" in on and "\033[33m72%" in on
    assert "\033[36m72%" in off and "\033[31m96%" not in off


def test_cli_and_editor_set_bars_and_level_colors(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("CLAUDE_STATUSLINE_CONFIG", str(path))
    cli.main(["config", "--bars", "5h,context", "--level-colors", "off"])
    assert config_module.load(path).bars == ["context", "5h"]
    assert config_module.load(path).level_colors is False
    cli.main(["config", "--bars", "none"])
    assert config_module.load(path).bars == []
    editor = Editor(Config())
    editor.cursor = editor.row_index("bar_field", "7d")
    _press(editor, "space")
    assert editor.config.bars == ["context", "7d"]
    _press(editor, "f")
    assert editor.config.level_colors is False
    _press(editor, "r")
    assert editor.config.bars == ["context"] and editor.config.level_colors is True


def test_two_rows_put_the_plan_limits_on_the_second_row(tmp_path, monkeypatch):
    assert "\n" not in preview(Config(colors=False))
    first, second = preview(Config(colors=False, rows=2)).split("\n")
    assert "Opus 5.5" in first and "42%" in first and "cache" in first and "5h" not in first
    assert second.startswith("5h: 72%") and "7d" in second and "session" in second
    only_limits = preview(Config(colors=False, rows=2, fields=["5h", "7d"]))
    assert "\n" not in only_limits  # an empty row is left out
    assert from_dict({"rows": 3}).rows == 1
    monkeypatch.setenv("CLAUDE_STATUSLINE_CONFIG", str(tmp_path / "c.json"))
    cli.main(["config", "--rows", "2"])
    assert config_module.load(tmp_path / "c.json").rows == 2
    editor = Editor(Config())
    editor.cursor = editor.row_index("rows")
    _press(editor, "right")
    assert editor.config.rows == 2


def test_five_fill_levels_and_distinct_blocks_without_them():
    from claude_statusline.render import level
    assert [level(p) for p in (0, 25, 50, 75, 90)] == ["ok", "fair", "warn", "high", "bad"]
    line = preview(Config(theme="slant", level_colors=False, bars=["context", "5h", "7d"]))
    for bg in (66, 30, 94):  # context, 5h, 7d: a colour of their own each
        assert f"\033[48;5;{bg};" in line
    from claude_statusline.themes import join
    same = join([("a", "usage"), ("b", "usage_context")], "slant", True, " | ")
    assert "\u2502" in same  # the same background on both sides: a thin line between


def test_skill_field_shows_the_last_invoked_skill(tmp_path):
    from claude_statusline.transcript import last_skill
    path = tmp_path / "t.jsonl"
    lines = [
        '{"type":"user","message":{"content":[{"type":"text","text":"Base directory for this skill: /h/.claude/skills/plan-tracker\\n\\n# x"}]}}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Base directory for this skill: fake"}]}}',
        '{"type":"user","message":{"content":[{"type":"text","text":"Base directory for this skill: /p/skills/pdf\\n"}]}}',
        '{"type":"user","message":{"content":"hello"}}',
    ]
    path.write_text("\n".join(lines) + "\n")
    assert last_skill(str(path)) == "pdf"
    path.write_text('{"type":"user","message":{"content":"hello"}}\n')
    assert last_skill(str(path)) is None


def test_skill_field_in_preview_and_hidden_without_one():
    from claude_statusline.render import preview
    assert "skill: plan-tracker" in preview(Config(colors=False))
    assert "plan-tracker" not in preview(Config(fields=["model", "context"]))


def test_running_agents_reads_meta_and_skips_finished(tmp_path):
    import json as _json, os as _os
    from claude_statusline.agents import running_agents
    transcript = tmp_path / "s.jsonl"
    transcript.write_text("")
    folder = tmp_path / "s" / "subagents"
    folder.mkdir(parents=True)
    rec = {"type": "user", "timestamp": "2026-11-15T12:00:00Z", "message": {"content": "go"}}
    skill = ('{"type":"user","message":{"content":[{"type":"text","text":'
             '"Base directory for this skill: /x/skills/pdf\\n"}]}}')
    for agent_id, finished in (("a1", False), ("a2", True)):
        (folder / f"agent-{agent_id}.jsonl").write_text(_json.dumps(rec) + "\n" + skill + "\n")
        (folder / f"agent-{agent_id}.meta.json").write_text(_json.dumps(
            {"agentType": "wykonawca", "description": "Task " + agent_id, "finished": finished}))
    now = _os.path.getmtime(folder / "agent-a1.jsonl") + 5
    agents = running_agents(str(transcript), now)
    assert [(a.name, a.description, a.skill) for a in agents] == [("wykonawca", "Task a1", "pdf")]
    assert running_agents(str(transcript), now + 3600) == []  # idle too long: gone


def test_agents_field_adds_a_row_per_agent_and_is_off_by_default():
    from claude_statusline.config import DEFAULT_FIELDS
    from claude_statusline.render import preview
    assert "agents" not in DEFAULT_FIELDS
    assert "wykonawca" not in preview(Config(colors=False))
    lines = preview(Config(fields=DEFAULT_FIELDS + ["agents"], colors=False)).splitlines()
    assert lines[1].startswith("\u25b8 wykonawca | Implement") and "skill: kotlin-android" in lines[1]
    assert lines[2].startswith("\u25b8 Explore")
