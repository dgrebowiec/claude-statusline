import datetime
import json
from pathlib import Path

import pytest

from claude_statusline.cache import cache_status, last_cache_io
from claude_statusline.pricing import weighted
from claude_statusline.transcript import tail_lines, usage_record
from claude_statusline.usage import load_index, session_share


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


def test_session_share_window_starts_at_reset_minus_length(tmp_path):
    projects = tmp_path / "projects"
    main = projects / "p" / "main.jsonl"
    _write(main, [_record(NOW - datetime.timedelta(minutes=5), "claude-opus-5",
                          {"input_tokens": 1000}, "a")])
    # 4 h ago: inside the last 5 h, but before the window that resets in 3 h started (2 h ago)
    other = projects / "q" / "other.jsonl"
    _write(other, [_record(NOW - datetime.timedelta(hours=4), "claude-opus-5",
                           {"input_tokens": 3000}, "b")])
    resets_at = NOW.timestamp() + 3 * 3600
    share = session_share(str(main), 5, 40.0, str(projects), tmp_path / "cache",
                          NOW.timestamp(), resets_at)
    assert share == pytest.approx(40.0)
    share = session_share(str(main), 5, 40.0, str(projects), tmp_path / "cache2",
                          NOW.timestamp())
    assert share == pytest.approx(10.0)


def test_index_reads_only_appended_lines(tmp_path):
    projects = tmp_path / "projects"
    cache = tmp_path / "cache"
    main = projects / "p" / "main.jsonl"
    recent = NOW - datetime.timedelta(minutes=5)
    _write(main, [_record(recent, "claude-opus-5", {"input_tokens": 1000}, "a")])
    ts = NOW.timestamp()
    assert len(load_index(str(projects), cache, ts)[str(main)]["calls"]) == 1
    with open(main, "a", encoding="utf-8") as fh:
        fh.write(_record(recent, "claude-opus-5", {"input_tokens": 500}, "b") + "\n")
        fh.write(_record(recent, "claude-opus-5", {"input_tokens": 9}, "c"))  # no newline yet
    entry = load_index(str(projects), cache, ts)[str(main)]
    assert sorted(entry["calls"]) == ["a", "b"]
    with open(main, "a", encoding="utf-8") as fh:
        fh.write("\n")
    assert sorted(load_index(str(projects), cache, ts)[str(main)]["calls"]) == ["a", "b", "c"]
    # a rewritten (shorter) file is read again from the start
    _write(main, [_record(recent, "claude-opus-5", {"input_tokens": 1}, "z")])
    assert sorted(load_index(str(projects), cache, ts)[str(main)]["calls"]) == ["z"]


def test_session_share_none_when_window_empty(tmp_path):
    main = tmp_path / "p" / "main.jsonl"
    _write(main, [])
    assert session_share(str(main), 5, 10.0, str(tmp_path / "none"),
                         tmp_path / "cache", NOW.timestamp()) is None


# --- cache reads and writes of the last call ---

def test_last_cache_io_reads_the_last_call(tmp_path):
    first = {"cache_read_input_tokens": 10, "cache_creation_input_tokens": 900}
    last = {"cache_read_input_tokens": 118_000,
            "cache_creation": {"ephemeral_5m_input_tokens": 0,
                               "ephemeral_1h_input_tokens": 4_000}}
    path = _write(tmp_path / "s.jsonl", [
        _record(NOW, "claude-opus-5", first, "m1"),
        _record(NOW, "claude-opus-5", last, "m2"),
    ])
    assert last_cache_io(path) == (118_000, 4_000)


def test_last_cache_io_none_without_api_calls(tmp_path):
    path = _write(tmp_path / "s.jsonl", ['{"type":"user"}'])
    assert last_cache_io(path) is None


# --- splitting rises of the limit between readings ---

def test_attributed_share_splits_each_rise_by_its_own_calls():
    from claude_statusline.usage import attributed_share
    calls = [(10, 100, True), (20, 100, False),   # 0 -> 10 %: half mine
             (30, 300, False)]                     # 10 -> 40 %: none mine
    points = [(0, 0.0), (25, 10.0), (35, 40.0)]
    assert attributed_share(calls, points) == pytest.approx(5.0)
    # the plain ratio would say 40 % x 100 / 500 = 8 %


def test_attributed_share_splits_rise_without_calls_like_the_span_before():
    from claude_statusline.usage import attributed_share
    calls = [(10, 50, True), (12, 50, False)]
    # 10 -> 25 % came in a span without calls (a late reading): split half and half too
    assert attributed_share(calls, [(0, 0.0), (20, 10.0), (30, 25.0)]) == 12.5


def test_samples_skip_stale_readings_and_start_new_window(tmp_path):
    from claude_statusline.samples import Samples
    samples = Samples(tmp_path, 1000)
    samples.observe(5, 10.0, 5000, 1000)
    samples.observe(5, 8.0, 5000, 1010)    # stale reading of an idle session
    samples.observe(5, 12.5, 5001, 1020)   # same window, resets_at a second off
    assert samples.window(5, 5000) == [(1000, 10.0), (1020, 12.5)]
    samples.observe(5, 0.3, 23000, 6000)   # next window
    reread = Samples(tmp_path, 6000)
    assert reread.window(5, 23000) == [(6000, 0.3)]
    assert len(reread.window(5, 5000)) == 2


def test_session_share_uses_readings(tmp_path):
    from claude_statusline.samples import Samples
    from claude_statusline.usage import share_numbers
    projects = tmp_path / "projects"
    t0 = NOW - datetime.timedelta(hours=1)
    main = projects / "p" / "main.jsonl"
    _write(main, [_record(t0 + datetime.timedelta(minutes=1), "claude-opus-5",
                          {"input_tokens": 1000}, "a")])
    _write(projects / "q" / "other.jsonl",
           [_record(t0 + datetime.timedelta(minutes=30), "claude-opus-5",
                    {"input_tokens": 1000}, "b")])
    resets_at = NOW.timestamp() + 3600
    samples = Samples(tmp_path / "cache", NOW.timestamp())
    samples.observe(5, 30.0, resets_at, (t0 + datetime.timedelta(minutes=10)).timestamp())
    share, mine, window = share_numbers(str(main), 5, 40.0, str(projects), tmp_path / "cache",
                                        NOW.timestamp(), resets_at, samples=samples)
    assert (share, mine, window) == (pytest.approx(30.0), 1000, 2000)
