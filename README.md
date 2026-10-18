# claude-statusline

A status line for Claude Code that shows what you need to decide between `/compact`,
`/clear` and carrying on:

```
Haiku 5.5 | [##------------------] 12% (118k/1.0M) | cache 1h: until 16:30:26 | 5h: 17% (reset 17:03) (session ~4.6%) | 7d: 96% (reset 21.10 02:53) (session ~0.5%)
```

- **Model and effort:** model name and the effort level (`effort: high` etc.) when Claude Code reports it.
- **Context:** share of the window used, tokens used / window size, warnings at 70% and 85%.
- **Prompt cache:** tier of the last cache write (`5m` or `1h`) and time until it expires.
- **Cache reads and writes (optional `cacheio` field):** tokens read from and written to the
  prompt cache by the last API call, e.g. `cache read 118k, write 4k`.
- **Plan limits:** 5-hour and 7-day usage with time until reset, from Claude Code's own data.
- **Session share:** estimate of how much of each limit this session used.

It uses 0 tokens: it only reads local data and never calls the model.

Colours: model bold cyan, effort bold bright magenta; context and limit percentages green below 70%, yellow below 85%,
red above; cache tier blue for `1h`, magenta for `5m`; session share italic cyan; the rest dim.
Set `NO_COLOR=1` to turn colours off.

## Configure

Run the interactive editor. It shows a live preview at the bottom after every change:

```bash
claude-statusline configure
```

| Key | Action |
| --- | --- |
| `↑` `↓` (or `k` `j`) | select a field |
| `space` (or a digit `1`-`8`) | show / hide the field |
| `u` `d` (or `Shift+↑` `Shift+↓`) | move the field up / down (hidden fields too; space never moves a row) |
| `←` `→` | detail level: `minimal`, `normal`, `detailed` |
| `s` / `S` | next separator preset / type your own |
| `c` | colours on / off |
| `r` | reset to defaults |
| `enter` | save and exit |
| `q` / `Esc` | quit (asks again if there are unsaved changes) |

When the input is not a terminal (for example piped), it falls back to text commands, one per
line: a number toggles a field, `u<n>` / `d<n>` moves one, `l` level, `s` separator, `c`
colours, `r` reset, `w` save, `q` quit.

Or set options directly:

```bash
claude-statusline config --level minimal --fields model,context,5h,7d --separator " · "
claude-statusline config --colors off
claude-statusline config --show       # print current settings
claude-statusline config --reset      # back to defaults
claude-statusline preview             # print a sample line with the current settings
```

Settings are stored in `~/.claude/claude-statusline.json` (override with the
`CLAUDE_STATUSLINE_CONFIG` environment variable). Fields: `model`, `effort`, `context`, `cache`,
`5h`, `7d`, `share`, `cacheio` (off by default; turn it on with `claude-statusline configure`
or `--fields`). The order in `fields` is the order on the line.

Detail levels:

- `minimal`: percentages only, no reset times or session share details.
- `normal`: the default shown at the top of this page.
- `detailed`: adds tokens left in the context, the cache TTL, weekday of the reset, and the
  session's weighted tokens next to its share. The `cacheio` field shows exact token counts.

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

`install` sets `statusLine` in `~/.claude/settings.json` and keeps a backup of the file.
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

For each window (5 h, 7 d):

    session share = used_percent_of_limit * session_weighted_tokens / window_weighted_tokens

Both totals count usage since the window started (`reset time - 5 h` or `- 7 d`), not the last
5 h or 7 d: usage of the previous window would otherwise inflate the window total.
Only local transcripts in `~/.claude/projects` are counted, including subagents of the session.
If usage happened on another machine or in the web app, the window total is too small and the
share is too high. Calls of the last 7 days are kept in an index
(`~/.cache/claude-statusline/index.json`); each run reads only lines added to transcripts since
the previous run, so the totals are always current and a run takes well under 0.1 s.

## Limits

- By default the statusline refreshes only when Claude Code updates it (after responses and
  similar events), so it stands still while subagents work. Add `"refreshInterval": 10` to the
  `statusLine` block in `~/.claude/settings.json` to re-run it every 10 s as well; the session
  share then includes subagent work as it happens.
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
