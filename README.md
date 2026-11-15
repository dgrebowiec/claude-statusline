# claude-statusline

A status line for Claude Code that shows what you need to decide between `/compact`,
`/clear` and carrying on:

```
Haiku 5.5 | [##------------------] 12% (118k/1.0M) | cache 1h: until 16:30:26 | 5h: 17% (reset 17:03) (session ~4.6%) | 7d: 96% (reset 21.10 02:53) (session ~0.5%)
```

- **Model and effort:** model name and the effort level (`effort: high` etc.) when Claude Code reports it.
- **Skill:** the skill invoked last in this session (`skill: plan-tracker`), by Claude or as a
  `/command`; read from the transcript, hidden until one is used.
- **Context:** share of the window used, tokens used / window size, warnings at 50% and 75%.
- **Prompt cache:** tier of the last cache write (`5m` or `1h`) and time until it expires.
- **Cache reads and writes (optional `cacheio` field):** tokens read from and written to the
  prompt cache by the last API call, e.g. `cache read 118k, write 4k`.
- **Agents (optional `agents` field):** each subagent still at work on a row of its own below
  the status line: its type and task, model and effort, last skill and run time. Off by default.
- **Plan limits:** 5-hour and 7-day usage with time until reset, from Claude Code's own data.
- **Session share:** estimate of how much of each limit this session used.
- **Agent panel (optional, Claude Code before 2.1.325 only):** each running subagent's model, effort, last skill, prompt cache and share of the
  5-hour limit at the end of its row in Claude Code's own list of agents (below the prompt),
  through the `subagentStatusLine` setting. Shares, like the session's, are points of the whole
  limit: at `5h: 50%`, `~20.7%` means 20.7 of those 50 points.

It uses 0 tokens: it only reads local data and never calls the model.

Colours: model bold cyan, effort bold bright magenta, skill lilac; context and limit percentages by how full
they are: green below 25%, yellow-green below 50%, yellow below 75%, orange below 90%, red above
(fill colours, on by default; off: `config --level-colors off` or key `f`, and each of context,
`5h`, `7d` gets a fixed colour of its own); cache tier blue for `1h`, magenta for `5m`; session share italic cyan; the rest dim.
Set `NO_COLOR=1` to turn colours off.

## Configure

Run the interactive editor. It shows a live preview at the top after every change; below it are
sections for fields, [themes](#themes), appearance (level, separator, colours) and the agent panel:

```bash
claude-statusline configure   # or just: claude-statusline
```

Typed in a terminal with no input piped in, plain `claude-statusline` opens the editor too (Claude Code
always pipes its JSON in, so the status line itself is unaffected).

| Key | Action |
| --- | --- |
| `↑` `↓` (or `k` `j`) | select a row |
| `space` (or a digit `1`-`9`) | show / hide the field, pick the theme, change the setting |
| `u` `d` (or `Shift+↑` `Shift+↓`) | move the field up / down (hidden fields too; space never moves a row) |
| `←` `→` | previous / next value of the selected theme or setting; on field rows the detail level (`minimal`, `normal`, `detailed`) |
| `t` | next theme |
| `l` | next detail level |
| `s` / `S` | next separator preset / type your own |
| `c` | colours on / off |
| `f` | fill colours (green / yellow / red by how full) on / off |
| `a` (or `space` on its on/off row) | [agent panel](#agent-panel) on / off; its fields show only while it is on |
| `r` | reset to defaults |
| `enter` | save and exit |
| `q` / `Esc` | quit (asks again if there are unsaved changes) |

When the input is not a terminal (for example piped), it falls back to text commands, one per
line: a number toggles a field, `u<n>` / `d<n>` moves one, `a` agent panel on / off, `a<n>` toggles
agent panel field n, `t` next theme, `t<n>` theme n, `b<n>` bar style n, `p<n>` bar on / off
for field n (1 context, 2 5h, 3 7d), `l` level, `s` separator, `c` colours, `f` fill colours, `r` reset, `w` save, `q` quit.

Or set options directly:

```bash
claude-statusline config --level minimal --fields model,context,5h,7d --separator " · "
claude-statusline config --colors off
claude-statusline config --theme slant   # see Themes below
claude-statusline config --bars context,5h,7d   # progress bars on these fields; none: no bars
claude-statusline config --level-colors off     # one colour instead of green / yellow / red
claude-statusline config --rows 2   # session on row 1, plan limits (5h, 7d, share) on row 2
claude-statusline config --refresh 5  # re-run every 5 s (at least 3); 0 or off: events only
claude-statusline config --agent-panel on   # agent rows in Claude Code < 2.1.325; off: remove
claude-statusline config --show       # print current settings
claude-statusline config --reset      # back to defaults
claude-statusline preview             # print a sample line with the current settings
```

Settings are stored in `~/.claude/claude-statusline.json` (override with the
`CLAUDE_STATUSLINE_CONFIG` environment variable). Fields: `model`, `effort`, `skill`, `context`, `cache`,
`5h`, `7d`, `share`, `cacheio` and `agents` (both off by default; turn it on with
`claude-statusline configure` or `--fields`). The agent panel has its own `agent_fields` (`time`,
`tokens`, `model`, `effort`, `skill`, `cache`, `share`), set in its own section of `configure`; as in the
main line, `effort` sits next to the model, and on its own only when `model` is off. The order in `fields` is the order on the line.

Rows (`--rows`, the Rows setting of `configure`): `1` (default) puts every field on one row; `2`
splits them, the session (`model`, `effort`, `skill`, `context`, `cache`, `cacheio`) on the first row and the
plan limits (`5h`, `7d`, `share`) on the second, each row in the configured order and theme.

Detail levels:

- `minimal`: percentages only, no reset times or session share details.
- `normal`: the default shown at the top of this page.
- `detailed`: adds tokens left in the context, the cache TTL, weekday of the reset, and the
  session's weighted tokens next to its share. The `cacheio` field shows exact token counts.

### Themes

A theme sets how the fields are drawn (`--theme` or the Theme section of `configure`, which shows
a sample of each):

| Theme | Look |
| --- | --- |
| `plain` (default) | coloured text, fields split by the separator |
| `blocks` | each field a filled block, gaps between them |
| `slant` | filled blocks joined by slanted edges ◤ |
| `fade` | filled blocks fading into each other ▓▒░ |
| `boxes` | coloured frame `╭─╮ │ │ ╰─╯` around each field: three rows |

Filled themes colour the block by state: context and limits at the same five fill levels as the
text (with fill colours off each in its own colour, so neighbouring blocks never merge; two
neighbours of the same colour get a thin `│` between them), cache blue (`1h`), magenta (`5m`) or grey (expired). The shapes are
standard Unicode characters, so no Nerd Font is needed.
Context and the `5h` / `7d` limits fill up towards a limit, so each can show a progress bar
(`--bars`, or the "show a bar on" rows of the Progress bar section of `configure`); by default
only context has one, and the `minimal` level shows none. All bars share one style (`--bar`, key `b`):

| Bar | Look |
| --- | --- |
| `auto` (default) | `ascii` on `plain` / `boxes`, `bricks` on the filled themes |
| `ascii` | `[########------------]` |
| `bricks` | `▮▮▮▮▮▮▮▮▯▯▯▯▯▯▯▯▯▯▯▯` |
| `dots` | `●●●●●●●●○○○○○○○○○○○○` |
| `blocks` | `████████░░░░░░░░░░░░` |
| `line` | `━━━━━━━━╌╌╌╌╌╌╌╌╌╌╌╌` |

The separator is used by `plain` only. With colours off the filled themes fall back to `plain`.
The agent panel keeps its own plain rows.

### Agent panel

> **Claude Code 2.1.325 and later no longer support custom agent rows:** the
> `subagentStatusLine` setting is deprecated and has no effect, the rows below the prompt always
> look the default way. To see each running agent (type, task, model, effort, last skill, run
> time) turn on the `agents` field instead: `claude-statusline configure`, or add `agents` to
> `--fields`, e.g. `claude-statusline config --fields model,effort,skill,context,cache,5h,7d,share,agents`.
> Each agent then gets a row of its own below the status line.

Optional, off by default: `claude-statusline config --agent-panel on` (or `a` in
`claude-statusline configure`) sets Claude Code's
`subagentStatusLine` to `claude-statusline subagent` (`off` removes it; a `subagentStatusLine`
of another tool is never touched). While subagents are listed below the prompt, the row of each
running subagent then ends with its share of the 5-hour limit so far, in points of the whole
limit:

```
◯ wykonawca  Compiling main, unit, androidTest sources     6m 13s · ↓ 82.3k tokens · 5h ~20.7%
```

Claude Code replaces the whole row with what the command returns, so the command redraws the
name, description, run time and tokens the way Claude Code does and adds the share; finished
subagents keep Claude Code's own row. The cost: Claude Code runs the command every 5 s (fixed,
not configurable), so those rows, run time included, update every 5 s instead of every second. That command gets no limit data from Claude Code, so it uses the last reading the
status line logged; it shows nothing until the status line has run once in the current window.

### Refresh interval

Claude Code re-runs the status line after its own updates (a response of the main thread and
similar events). While a subagent works, the main thread waits, so without a timer the line
stands still. `install` therefore sets `refreshInterval` to 10 s in the `statusLine` block of
`~/.claude/settings.json`; change it with `claude-statusline config --refresh SECONDS`
(at least 3 s; `0` or `off` turns the timer off).

What a timed refresh updates while a subagent works:

| Field | Changes? | Why |
|---|---|---|
| `5h`, `7d` | yes | Claude Code takes them from the last API response, subagent calls included |
| `share` | yes | it reads the subagent transcripts from disk |
| `context`, `cache`, `cacheio` | no | they describe the main thread only |

Each run also logs the current limit reading (see
[How the session share is estimated](#how-the-session-share-is-estimated)): the more often it
runs, the shorter the spans each rise is split over. A run takes about 0.1 s, so 10 s costs
about 1% of one CPU core per open session.

`cacheio` shows what the last API call did with the prompt cache: `read` is tokens served from
(a cache hit), `write` is tokens newly stored in it. `minimal` shows `r 118k w 4k`; `detailed`
shows exact counts. It reads the same transcript as `cache`, so it shows `cache i/o: none` until
the first call of the session.

It shows only the last call, not the whole session. Each call re-reads the context from the cache,
so summing all calls would count the same context many times over. For the whole session's cache
reads and writes, see the report of [claude-token-report](https://github.com/dgrebowiec/claude-token-report).

## Install

Works on Linux, macOS and Windows. Requires Python 3.9+ and no other packages.

**As a command** (recommended), with [pipx](https://pipx.pypa.io) or [uv](https://docs.astral.sh/uv/):

```bash
pipx install git+https://github.com/dgrebowiec/claude-statusline
# or: uv tool install git+https://github.com/dgrebowiec/claude-statusline
claude-statusline install
```

`install` sets `statusLine` in `~/.claude/settings.json` (with a 10 s
[refresh interval](#refresh-interval), or the one you already had) and keeps a backup of the
file. The [agent panel](#agent-panel) is turned on separately.
Restart Claude Code or send a message to see it.

Try it once without installing: `uvx --from git+https://github.com/dgrebowiec/claude-statusline claude-statusline preview`

**Or just clone it**, and run it from the clone:

```bash
git clone https://github.com/dgrebowiec/claude-statusline.git
cd claude-statusline
python3 -m claude_statusline preview
```

With a clone, set `statusLine.command` in `~/.claude/settings.json` to
`python3 -m claude_statusline` by hand, because `install` writes the command name only.

## Update

With pipx or uv:

```bash
pipx upgrade claude-statusline        # or: uv tool upgrade claude-statusline
claude-statusline --version           # shows the installed version
```

The `statusLine` entry in `settings.json` does not change on upgrade, so there is no need to run
`install` again. Restart Claude Code or send a message to see the new version.

With a clone, update it with `git pull` in the clone's directory.

## Uninstall

1. Remove the status line from Claude Code's settings:

   ```bash
   claude-statusline uninstall
   ```

   This deletes only the `statusLine` entry when it points to this tool, and keeps a backup of
   `settings.json`. If you want the previous status line back, copy the most recent
   `~/.claude/settings.json.bak-*` over `settings.json`.

2. Remove the program:

   ```bash
   pipx uninstall claude-statusline
   # or: uv tool uninstall claude-statusline
   ```

3. Optional: delete the cache of window totals:

   ```bash
   rm -rf ~/.cache/claude-statusline
   ```

Restart Claude Code (or send a message) after uninstalling so the change takes effect.

Without installing, you can also clone the repo and run `python -m claude_statusline`
from it (set `statusLine.command` to that command by hand).

## How the session share is estimated

Anthropic does not publish how subscription limits are counted. The estimate uses the same
relative weights as [claude-token-report](https://github.com/dgrebowiec/claude-token-report):

- input 1, cache read 0.1, cache write 1.25 (5 min) or 2 (1 h), output 5,
- multiplied by the model's price relative to Opus 5 (e.g. Sonnet 5.5 is 0.4).

A fixed ratio of weighted tokens to limit percent does not hold: in one 5-hour window, 1M
weighted tokens took 14 points early on and 18 points an hour later. So the statusline splits
each rise of the limit separately:

- Every run logs Claude Code's reading of the limit (`used_percentage`, 0.1% steps) to
  `~/.cache/claude-statusline/samples.jsonl`, shared by all sessions; only rises and new windows
  are logged, so stale readings of an idle session are skipped.
- Between two readings the limit rose by Δ%. Each session gets
  `Δ% * its weighted tokens in that span / all weighted tokens in that span`.
- The session share is the sum over the window. Weights now only decide how one short rise is
  split between sessions working at the same time, and the shares of all sessions add up to
  the limit.
- Before the first reading of a window (e.g. right after installing), the share is
  `used% * session_weighted_tokens / window_weighted_tokens` over that part.
- A rise in a span without local calls is split like the span before it: usually a reading
  arrived late (an idle session logged an old value first). Usage on another machine or in the
  web app is therefore counted to the local sessions working at that time.

Both totals count usage since the window started (`reset time - 5 h` or `- 7 d`), not the last
5 h or 7 d: usage of the previous window would otherwise inflate the window total.
Only local transcripts in `~/.claude/projects` are counted, including subagents of the session.
Calls of the last 7 days are kept in an index
(`~/.cache/claude-statusline/index.json`); each run reads only lines added to transcripts since
the previous run, so the totals are always current and a run takes well under 0.1 s.

## Limits

- Without a [refresh interval](#refresh-interval) the line updates only on Claude Code's own
  events, so it stands still while subagents work.
- Cache expiry is estimated from the last cache write or read in the transcript; the server may
  differ slightly.
- `cacheio` counts only the last call of the main transcript; subagent calls are not included.
- Reset times and limit percentages come from Claude Code; they are not shown when Claude Code
  does not send them (e.g. with an API key).

## Development

```bash
pip install -e .[test]
pytest
```

## License

[MIT](LICENSE)
