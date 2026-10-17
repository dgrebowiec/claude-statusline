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
    answers = iter(["1", "d1", "l", "w"])  # hide model, move enabled field 1 down, level, save
    out = []
    saved = run(path, ask=lambda prompt: next(answers), out=out.append)
    assert saved == path
    cfg = config_module.load(path)
    assert "model" not in cfg.fields
    assert cfg.fields[0] == "context"  # effort was first; moving it down puts context first
    assert cfg.level == "detailed"


def test_configurator_quit_does_not_save(tmp_path):
    path = tmp_path / "c.json"
    answers = iter(["1", "q"])
    assert run(path, ask=lambda prompt: next(answers), out=lambda s: None) is None
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
