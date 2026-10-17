import datetime
import json
from pathlib import Path

import pytest

from claude_statusline import __version__, cli
from claude_statusline.render import render
from claude_statusline.settings import install, uninstall

NOW = datetime.datetime(2026, 10, 17, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def plain_output(monkeypatch):
    """Text assertions run without ANSI codes; colour is tested separately."""
    monkeypatch.setenv("NO_COLOR", "1")


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
