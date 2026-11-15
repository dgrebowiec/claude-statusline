---
name: release
description: Release a new version of claude-statusline - bump the version, finish CHANGELOG and README, run the tests, commit, tag, push and create the GitHub release (a tag alone does not show up under Releases). Use when the user asks to release, publish, tag or ship a version ("wydaj wersję", "zrób release", "podbij wersję", "utwórz tag", "wypchnij wersję").
---

# Release a version of claude-statusline

A release is complete only when ALL of these hold: version bumped, CHANGELOG section for it,
README matches the code, tests green, commit pushed, annotated tag pushed, GitHub release
published and marked Latest. A pushed tag without `gh release create` does NOT appear under
"Releases" on GitHub - never stop after the tag.

## 1. Pick the version

- Current version: `claude_statusline/__init__.py` (`__version__`); `pyproject.toml` reads it
  from there (`dynamic = ["version"]`), so that is the only place to change.
- Semantic versioning: new fields / options / visible changes -> minor (`1.3.0` -> `1.4.0`);
  fixes only -> patch (`1.3.0` -> `1.3.1`); breaking config format -> major.
- Check the tag is free: `git tag -l vX.Y.Z` and `gh release view vX.Y.Z` (must fail).
- If the user did not name the version, propose one from the changes and go on.

## 2. CHANGELOG.md

- Changes collect under `## Unreleased` while working. Rename it to `## X.Y.Z` (no date, as in
  the existing sections). If there is no Unreleased section, write the entries from
  `git log --oneline vPREV..HEAD`.
- One line per user-visible change, in English, naming the option / key / field
  (`config --rows 2`, key `f`, `agents` field). Mention changed defaults and what happens to
  existing settings files.

## 3. README.md

- Every new option, field, key and default must be described: feature list at the top,
  Configure (key table, text commands, `config` examples), field list, Themes / bars, agent panel.
- Defaults in the README must match `config.py` / `themes.py` (`DEFAULT_FIELDS`, `DEFAULT_BARS`,
  `rows`, `DEFAULT_THEME`, `DEFAULT_BAR`).
- English only: no Polish words in examples (agent names, task labels). Check:
  `grep -n -i "wykonawca\|[ąćęłńóśźż]" README.md CHANGELOG.md` must print nothing.
- Screenshots in `docs/images/` (`statusline.png`, `configure.png`): regenerate with
  `python3 scripts/screenshots.py` whenever the look of the line or the configurator changed.
  It draws ◤ and ▓▒░ as full cells, as a terminal does; a plain HTML render of those glyphs
  leaves small triangles with gaps and does not match the real terminal. Open both images and
  compare them with the terminal before committing.

## 4. Verify

```bash
python3 -m pytest -q                       # all green
pipx install --force .                     # the user's live status line uses this
claude-statusline --version                # prints X.Y.Z
claude-statusline preview                  # renders without errors
```

## 5. Commit, tag, push

- `git status -s` first. Stage explicit paths only (`CHANGELOG.md README.md claude_statusline
  tests docs/images/...`), never `git add -A` / `.`: `.idea/`, `.claude/scheduled_tasks.lock`,
  scratch files and screenshots of the user's screen stay out.
- Commit message: short summary with the version in brackets, e.g.
  `Skill and agents fields, limit bars, two rows (1.3.0)`, a short bullet body, and the
  Co-Authored-By line.
- Annotated tag on that commit: `git tag -a vX.Y.Z -m "X.Y.Z"`.
- A tag that was already created locally but NOT pushed may be moved (`git tag -f -a ...`).
  A pushed tag is never moved: release a new patch version instead.
- `git push origin main` then `git push origin vX.Y.Z`.

## 6. GitHub release

Notes = the CHANGELOG section of this version, title = the tag (as in earlier releases):

```bash
python3 -c "
s=open('CHANGELOG.md').read(); a=s.index('## X.Y.Z\n')+len('## X.Y.Z\n'); b=s.find('\n## ',a)
print(s[a:b if b>0 else None].strip())" > "$SCRATCH/notes.md"
gh release create vX.Y.Z --title vX.Y.Z --notes-file "$SCRATCH/notes.md" --verify-tag
```

## 7. Check it landed

```bash
gh release list --limit 2                       # vX.Y.Z first, marked Latest
git rev-parse vX.Y.Z^{} origin/main             # the same commit
git ls-remote --tags origin | grep vX.Y.Z       # the tag is on GitHub
```

Report to the user: version, commit, release URL, and anything left out on purpose.
