# AI Token Bars

GNOME Shell extension that shows compact usage bars for local AI coding tools in
the top panel.

- **Codex**: reads the latest Codex rate-limit event from local session data.
- **Claude Code**: reads a cache file written by a Claude Code `statusLine`
  helper script.

The panel intentionally stays small: an icon plus a progress bar per tool. More
detail is available from the dropdown menu.

## Status

Tested on GNOME Shell 42. The extension is local-first and does not make network
requests. It reads local files only:

- `~/.codex/state_5.sqlite`
- the active Codex rollout JSONL referenced by that database
- `~/.cache/claude-token-bar/status.json`

## Requirements

- GNOME Shell 42
- `sqlite3`
- `tail`
- Python 3 for Claude Code statusline support
- Claude Code, only if you want the Claude bar populated

## Install

```bash
make install
make configure-claude
make enable
```

If GNOME does not show the extension immediately, reload GNOME Shell with
`Alt+F2`, then `r`, then Enter. On Wayland, log out and back in.

Claude Code must run at least one interaction after `make configure-claude`
before Claude limit data is available.

## Package

```bash
make pack
```

The packaged extension is written to `dist/`.

## Data Model

Codex currently exposes limit usage in local rollout events as percentages. This
extension uses the primary Codex rate-limit percentage for the main Codex bar.

Claude Code exposes richer live usage through its `statusLine` payload. The
helper script writes only usage metadata to:

```text
~/.cache/claude-token-bar/status.json
```

The Claude bar uses `rate_limits.five_hour.used_percentage` when available and
falls back to `context_window.used_percentage`.

## Repository Layout

```text
extension/       GNOME Shell extension source
scripts/         Claude Code statusline and setup helpers
docs/            Design notes
.github/         CI validation
```

## Notes

GNOME Shell caches extension JavaScript in the running session. Changing files on
disk usually requires a Shell reload or logout/login before the changed code is
loaded.
