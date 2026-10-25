# Changelog

## 1.2.0
- Plain `claude-statusline` typed in a terminal opens the configurator (Claude Code pipes its JSON in, so the status line is unaffected).
- Themes (`plain`, `blocks`, `slant`, `fade`, `boxes`) and progress bar styles (`--theme`, `--bar`).
- Redesigned configurator with sections for fields, themes, appearance and the agent panel.

## 1.1.1
- Configurator: agent panel on/off switch and an effort field.

## 1.1.0
- Agent panel: each subagent's model, effort, cache and 5 h share, with its own section in `configure`.
- The agent panel is opt-in: `config --agent-panel on|off`.

## 1.0.1
- Session share is counted from the start of the limit window.

## 1.0.0
- First release: model, effort, context, prompt cache, 5 h / 7 d limits, session share, `cacheio` field, detail levels, interactive configurator.
