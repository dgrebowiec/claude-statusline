import datetime
import json
from pathlib import Path

import pytest

from claude_statusline import __version__, cli
from claude_statusline.config import FIELDS, Config
from claude_statusline.render import render
from claude_statusline.settings import get_refresh, install, set_refresh, uninstall

NOW = datetime.datetime(2026, 10, 17, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Text assertions run without ANSI codes and never read the user's own config."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("CLAUDE_STATUSLINE_CONFIG", str(tmp_path / "absent.json"))


def _payload(pct=42, **extra):
    data = {
        "model": {"display_name": "Opus"},
        "context_window": {"used_percentage": pct, "total_input_tokens": 42000,
                           "context_window_size": 1000000},
    }
    data.update(extra)
    return data


def _render(tmp_path, payload):
    return render(payload, now=NOW, projects_dir=tmp_path / "projects",
                  cache_dir=tmp_path / "cache")


def test_render_context_and_no_transcript(tmp_path):
    line = _render(tmp_path, _payload())
    assert line.startswith("Opus | ")
    assert "42%" in line
    assert "(42k/1.0M)" in line
    assert line.endswith(" | cache: none")


def test_render_thresholds(tmp_path):
    assert "! high" in _render(tmp_path, _payload(pct=75))
    assert "FULL" in _render(tmp_path, _payload(pct=90))
    assert "high" not in _render(tmp_path, _payload(pct=10))


def test_render_shows_effort_next_to_model(tmp_path):
    line = _render(tmp_path, _payload(effort={"level": "high"}))
    assert line.startswith("Opus (effort: high) | ")
    assert _render(tmp_path, _payload()).startswith("Opus | ")


def test_render_no_context_data(tmp_path):
    line = _render(tmp_path, {"model": {"id": "x"}})
    assert line.startswith("x | context: no data")


def test_render_limits_show_reset_clock(tmp_path):
    five_h = datetime.datetime.fromtimestamp(NOW + 9000).strftime("%H:%M")
    seven_d = datetime.datetime.fromtimestamp(NOW + 300000)
    payload = _payload(rate_limits={
        "five_hour": {"used_percentage": 63.4, "resets_at": NOW + 9000},
        "seven_day": {"used_percentage": 18.2, "resets_at": NOW + 300000},
    })
    line = _render(tmp_path, payload)
    assert f"5h: 63% (reset {five_h})" in line
    assert f"7d: 18% (reset {seven_d.strftime('%d.%m %H:%M')})" in line


def test_render_cache_shows_absolute_expiry(tmp_path):
    touch = datetime.datetime.fromtimestamp(NOW - 60)
    usage = {"cache_creation": {"ephemeral_1h_input_tokens": 500}}
    record = {"timestamp": touch.astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"), "message": {"id": "m1", "model": "claude-opus-5",
                                                "usage": usage}}
    transcript = tmp_path / "s.jsonl"
    transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")
    expected = datetime.datetime.fromtimestamp(NOW - 60 + 3600).strftime("%H:%M:%S")
    line = _render(tmp_path, _payload(transcript_path=str(transcript)))
    assert f"cache 1h: until {expected}" in line


def test_render_survives_missing_transcript(tmp_path):
    payload = _payload(transcript_path=str(tmp_path / "missing.jsonl"))
    assert _render(tmp_path, payload).endswith(" | cache: none")


def test_colours_follow_levels_and_no_color(tmp_path, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    coloured = _render(tmp_path, _payload(pct=90))
    assert "\033[1;36mOpus\033[0m" in coloured  # model: bold cyan
    assert "\033[31m[" in coloured                  # 90% -> red bar
    monkeypatch.setenv("NO_COLOR", "1")
    assert "\033[" not in _render(tmp_path, _payload(pct=90))


def test_stdin_garbage_does_not_crash(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("{broken"))
    cli.main([])
    assert capsys.readouterr().out.startswith("? | context: no data")


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == __version__


def test_install_keeps_other_keys_and_backs_up(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"language": "polski", "statusLine": {
        "type": "command", "command": "/usr/bin/other"}}), encoding="utf-8")
    backup = install(path, command="claude-statusline")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["language"] == "polski"
    assert data["statusLine"]["command"] == "claude-statusline"
    assert backup is not None and backup.exists()


def test_install_sets_default_refresh_and_keeps_own(tmp_path):
    path = tmp_path / "settings.json"
    install(path, command="claude-statusline")
    assert get_refresh(path) == 10
    path.write_text(json.dumps({"statusLine": {"type": "command", "command": "x",
                                               "refreshInterval": 4}}), encoding="utf-8")
    install(path, command="claude-statusline")
    assert get_refresh(path) == 4


def test_set_refresh_checks_minimum_and_owner(tmp_path):
    path = tmp_path / "settings.json"
    install(path, command="claude-statusline")
    set_refresh(path, 3)
    assert get_refresh(path) == 3
    set_refresh(path, None)
    assert get_refresh(path) is None
    with pytest.raises(ValueError):
        set_refresh(path, 2)
    path.write_text(json.dumps({"statusLine": {"command": "/usr/bin/other"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        set_refresh(path, 10)


def test_config_refresh_option_validates(capsys):
    with pytest.raises(SystemExit):
        cli.main(["config", "--refresh", "2"])
    assert "at least 3" in capsys.readouterr().err
    assert cli._parse_refresh("off") == 0 and cli._parse_refresh("5") == 5


def test_install_creates_missing_file(tmp_path):
    path = tmp_path / "new" / "settings.json"
    assert install(path, command="claude-statusline") is None
    assert json.loads(path.read_text(encoding="utf-8"))["statusLine"]["command"] == \
        "claude-statusline"


def test_uninstall_only_removes_own_entry(tmp_path):
    path = tmp_path / "settings.json"
    install(path, command="/x/bin/claude-statusline")
    assert uninstall(path) is True
    assert "statusLine" not in json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({"statusLine": {"command": "/usr/bin/other"}}),
                    encoding="utf-8")
    assert uninstall(path) is False
    assert uninstall(tmp_path / "absent.json") is False


def test_render_respects_fields_order_and_separator(tmp_path):
    config = Config(level="normal", fields=["5h", "model"], separator=" · ")
    line = render(_payload(rate_limits={"five_hour": {"used_percentage": 10}}), now=NOW,
                  projects_dir=tmp_path / "p", cache_dir=tmp_path / "c", config=config)
    assert line.startswith("5h: 10%")
    assert line.endswith("Opus")
    assert " · " in line and " | " not in line


def test_minimal_is_shorter_than_detailed(tmp_path):
    from claude_statusline.render import render as render_fn
    payload = _payload(rate_limits={"five_hour": {"used_percentage": 63.4,
                                                  "resets_at": NOW + 9000}})
    common = dict(now=NOW, projects_dir=tmp_path / "p", cache_dir=tmp_path / "c")
    minimal = render_fn(payload, config=Config(level="minimal"), **common)
    detailed = render_fn(payload, config=Config(level="detailed"), **common)
    assert len(minimal) < len(detailed)
    assert "5h: 63%" in minimal and "(reset" not in minimal
    assert "left)" in detailed  # detailed shows tokens left in the context


def test_effort_field_can_be_turned_off_or_shown_alone(tmp_path):
    payload = _payload(effort={"level": "high"})
    common = dict(now=NOW, projects_dir=tmp_path / "p", cache_dir=tmp_path / "c")
    without = render(payload, config=Config(fields=["model", "context"]), **common)
    assert "effort" not in without
    alone = render(payload, config=Config(fields=["effort", "context"]), **common)
    assert alone.startswith("effort: high | ")


def test_render_shows_the_window_size_claude_code_reports(tmp_path):
    payload = _payload()
    payload["context_window"] = {"used_percentage": 50, "total_input_tokens": 100_000,
                                 "context_window_size": 200_000}
    assert "(100k/200k)" in _render(tmp_path, payload)


def test_cacheio_shows_reads_and_writes_of_last_call(tmp_path):
    usage = {"cache_read_input_tokens": 118_432,
             "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 4_120}}
    record = {"timestamp": "2026-10-17T11:59:00.000Z",
              "message": {"id": "m1", "model": "claude-opus-5", "usage": usage}}
    transcript = tmp_path / "s.jsonl"
    transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")
    payload = _payload(transcript_path=str(transcript))
    common = dict(now=NOW, projects_dir=tmp_path / "p", cache_dir=tmp_path / "c")
    fields = ["cacheio"]
    normal = render(payload, config=Config(fields=fields), **common)
    assert normal == "cache read 118k, write 4k"
    minimal = render(payload, config=Config(level="minimal", fields=fields), **common)
    assert minimal == "r 118k w 4k"
    detailed = render(payload, config=Config(level="detailed", fields=fields), **common)
    assert detailed == "cache read 118,432, write 4,120 tokens in the last call"


def test_cacheio_none_without_transcript(tmp_path):
    config = Config(fields=["cacheio"])
    line = render(_payload(), now=NOW, projects_dir=tmp_path / "p",
                  cache_dir=tmp_path / "c", config=config)
    assert line == "cache i/o: none"


def test_cacheio_is_off_by_default():
    assert "cacheio" not in Config().fields
    assert "cacheio" in FIELDS


def test_render_shows_working_subagents(tmp_path):
    import os

    def call(key, usage, stop, minutes_ago, tool=None):
        stamp = datetime.datetime.fromtimestamp(NOW - minutes_ago * 60, datetime.timezone.utc)
        content = [{"type": "tool_use", "name": tool}] if tool else [{"type": "text"}]
        return json.dumps({"type": "assistant",
                           "timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                           "message": {"id": key, "model": "claude-opus-5", "usage": usage,
                                       "stop_reason": stop, "content": content}})

    main = tmp_path / "projects" / "p" / "s.jsonl"
    main.parent.mkdir(parents=True)
    main.write_text(call("m", {"input_tokens": 1000}, "tool_use", 9, "Agent") + "\n")
    agents = tmp_path / "projects" / "p" / "s" / "subagents"
    agents.mkdir(parents=True)
    # waits 8 minutes for a build: nothing written meanwhile, but it is working
    busy = agents / "agent-a.jsonl"
    busy.write_text(call("a", {"input_tokens": 10, "cache_read_input_tokens": 82_000},
                         "tool_use", 8, "Bash") + "\n")
    (agents / "agent-a.meta.json").write_text('{"agentType": "wykonawca"}')
    done = agents / "agent-b.jsonl"
    done.write_text(call("b", {"input_tokens": 5}, "end_turn", 1) + "\n")
    killed = agents / "agent-c.jsonl"
    killed.write_text(call("c", {"input_tokens": 5}, "tool_use", 120, "Bash") + "\n")
    os.utime(busy, (NOW - 480, NOW - 480))
    os.utime(killed, (NOW - 7200, NOW - 7200))
    payload = _payload(transcript_path=str(main), rate_limits={
        "five_hour": {"used_percentage": 50.0, "resets_at": NOW + 3600}})
    line = _render(tmp_path, payload)
    # 50 % x 8_210 / 9_220 wt (main 1000, busy 8_210, done 5, killed 5)
    assert line.endswith("wykonawca: Bash 8m00s · ctx 82k · 5h ~44.5%")
    assert "agent:" not in line and "agent " not in line  # finished and stale ones are hidden

def test_duration_shows_seconds():
    from claude_statusline.render import _duration
    assert [_duration(s) for s in (45, 485, 3725)] == ["45s", "8m05s", "1h02m"]
