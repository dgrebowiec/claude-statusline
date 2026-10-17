import datetime
import json
from pathlib import Path

import pytest

from claude_statusline.cache import cache_status
from claude_statusline.pricing import weighted
from claude_statusline.transcript import tail_lines, usage_record
from claude_statusline.usage import session_share


def _record(time: datetime.datetime, model: str, usage: dict, key: str) -> str:
    return json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "message": {"id": key, "model": model, "usage": usage},
    })


def _write(path: Path, lines) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


NOW = datetime.datetime(2026, 10, 17, 12, 0, 0, tzinfo=datetime.timezone.utc)


# --- pricing: same weights as claude-token-report ---

def test_opus_input_is_one_weighted_token_per_token():
    assert weighted({"input_tokens": 1000}, "claude-opus-5") == 1000


def test_sonnet_input_is_weighted_by_model_price_once():
    # regression: model weight used to be applied twice (x0.4 x0.4)
    assert weighted({"input_tokens": 1000}, "claude-sonnet-5-5") == pytest.approx(400)


def test_haiku_output_and_cache_types():
    assert weighted({"output_tokens": 1000}, "claude-haiku-5-5") == pytest.approx(1000)
    assert weighted({"cache_read_input_tokens": 1000}, "claude-opus-5") == pytest.approx(100)
    usage = {"cache_creation": {"ephemeral_1h_input_tokens": 1000}}
    assert weighted(usage, "claude-opus-5") == pytest.approx(2000)
    usage = {"cache_creation": {"ephemeral_5m_input_tokens": 1000}}
    assert weighted(usage, "claude-opus-5") == pytest.approx(1250)


# --- transcript ---

def test_tail_lines_returns_last_lines(tmp_path):
    path = _write(tmp_path / "t.jsonl", [str(i) for i in range(10)])
    assert tail_lines(path, 3) == ["7", "8", "9"]


def test_usage_record_skips_non_usage_lines():
    assert usage_record('{"type":"user","timestamp":"2026-10-17T12:00:00Z"}') is None
    assert usage_record("not json") is None


# --- cache ---

def test_cache_tier_and_expiry(tmp_path):
    touch = NOW - datetime.timedelta(seconds=60)
    usage = {"cache_creation": {"ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 500}}
    path = _write(tmp_path / "s.jsonl", [_record(touch, "claude-opus-5", usage, "m1")])
    tier, expires_at = cache_status(path)
    assert tier == "1h"
    assert expires_at == pytest.approx(touch.timestamp() + 3600)


def test_cache_5m_expires(tmp_path):
    touch = NOW - datetime.timedelta(minutes=10)
    usage = {"cache_creation": {"ephemeral_5m_input_tokens": 500,
                                "ephemeral_1h_input_tokens": 0}}
    path = _write(tmp_path / "s.jsonl", [_record(touch, "claude-opus-5", usage, "m1")])
    tier, expires_at = cache_status(path)
    assert tier == "5m" and expires_at < NOW.timestamp()


def test_cache_none_without_writes(tmp_path):
    path = _write(tmp_path / "s.jsonl", [])
    assert cache_status(path) is None


# --- session share ---

def test_session_share_uses_session_over_window(tmp_path):
    projects = tmp_path / "projects"
    cache = tmp_path / "cache"
    recent = NOW - datetime.timedelta(minutes=5)
    main = projects / "p" / "main.jsonl"
    _write(main, [_record(recent, "claude-sonnet-5-5", {"input_tokens": 1000}, "a")])
    sub = projects / "p" / "main" / "subagents" / "agent.jsonl"
    _write(sub, [_record(recent, "claude-sonnet-5-5", {"input_tokens": 1000}, "b")])
    other = projects / "q" / "other.jsonl"
    _write(other, [_record(recent, "claude-opus-5", {"input_tokens": 1000}, "c")])
    # session = 400 + 400 (subagent), window = 800 + 1000 -> 70% * 800 / 1800
    share = session_share(str(main), 5, 70.0, str(projects), cache, NOW.timestamp())
    assert share == pytest.approx(70 * 800 / 1800)


def test_session_share_none_when_window_empty(tmp_path):
    main = tmp_path / "p" / "main.jsonl"
    _write(main, [])
    assert session_share(str(main), 5, 10.0, str(tmp_path / "none"),
                         tmp_path / "cache", NOW.timestamp()) is None
