# Architecture

AI Token Bars is a GNOME Shell extension plus one optional Claude Code helper.

## Components

- `extension/extension.js` renders two progress bars in the GNOME top panel.
- `extension/stylesheet.css` defines panel spacing and actor dimensions.
- `scripts/claude-statusline.py` receives Claude Code statusline JSON on stdin
  and writes a small cache file for GNOME Shell to read.
- `scripts/configure-claude-statusline.py` updates `~/.claude/settings.json` to
  call the statusline helper.

## Codex Flow

1. The extension reads `~/.codex/state_5.sqlite`.
2. It selects the most recently updated non-archived thread.
3. It tails that thread's rollout JSONL file.
4. It reads the latest `token_count` event.
5. It uses `rate_limits.primary.used_percent` for the panel bar.

This is intentionally read-only.

## Claude Code Flow

1. Claude Code calls the configured `statusLine` command.
2. `scripts/claude-statusline.py` receives Claude's live status payload.
3. The script writes `~/.cache/claude-token-bar/status.json`.
4. The extension reads that cache every refresh cycle.
5. It uses the five-hour rate-limit percentage when available, otherwise the
   context-window percentage.

## Refresh Cost

The extension refreshes every 10 seconds. Each refresh performs one tiny JSON
read for Claude and a read-only `sqlite3` query plus `tail` for Codex. There are
no network calls.

Claude Code statusline support runs only while Claude Code is active.

## Safety

The extension does not read Claude credentials. The statusline helper stores only
usage metadata and model labels. It does not copy prompts, transcript content,
workspace paths, session identifiers, OAuth tokens, or API keys.
