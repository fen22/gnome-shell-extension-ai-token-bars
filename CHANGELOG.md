# Changelog

## Unreleased

- Prevent stale idle Claude sessions from overwriting newer five-hour and
  weekly usage in the shared status cache.
- Ignore expired Claude limit windows and use the limit closest to exhaustion
  for the panel bar.

## 0.2.0

- Fix popup menu growing to fill the screen when a Codex thread title held a long/multi-line prompt.
- Simplify the popup to bounded, single-line rows: used/left percentage, time until reset, and open session count (Codex) or weekly usage (Claude).
- Hard-cap and ellipsize all popup menu labels so no data source can regrow the menu.

## 0.1.0

- Initial public repository structure.
- Add Codex rate-limit usage bar.
- Add Claude Code statusline cache helper and orange usage bar.
