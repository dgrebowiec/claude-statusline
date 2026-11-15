# Changelog

## 1.3.0
- New installs get the `slant` theme, two rows, progress bars on context, `5h` and `7d`, and the `cacheio` field; settings saved by 1.2.0 keep their theme and fields, and take the new rows and bars defaults.
- README: screenshots of the status line and the configurator.
- New `agents` field (off by default): each running subagent on a row of its own below the status line, with its task, model, effort, last skill and run time. Claude Code 2.1.325 deprecated `subagentStatusLine` (it no longer has any effect), so the agent panel works only on older versions; turn on `agents` to see each agent's details instead.
- New `skill` field (on by default): the skill invoked last in this session, read from the transcript; hidden until one is used. The agent panel shows each subagent's last skill too.
- Progress bars on the `5h` and `7d` limits too, each switched on or off on its own (`config --bars`, Progress bar section of `configure`); by default only context has one.
- Two-row layout (`config --rows 2`): the session on the first row, the plan limits on the second.
- Fill colours are now an option, on by default (`config --level-colors`, key `f`), with five levels: 0 / 25 / 50 / 75 / 90%; the configurator shows them as a coloured legend.
- Filled themes: with fill colours off, context, `5h` and `7d` each get a colour of their own; neighbours of the same colour get a thin line between them.

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
