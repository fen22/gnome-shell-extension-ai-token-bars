#!/usr/bin/env python3
"""Cache Claude Code statusline usage for the GNOME token bar."""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


CACHE_DIR = Path.home() / ".cache" / "claude-token-bar"
CACHE_FILE = CACHE_DIR / "status.json"
LOCK_FILE = CACHE_DIR / "status.lock"
WINDOW_NAMES = ("five_hour", "seven_day")


def get_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def get_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def copy_window(window: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("used_percentage", "remaining_percentage", "resets_at"):
        value = get_number(window.get(key))
        if value is not None:
            result[key] = value
    return result


def window_is_current(window: dict[str, Any], now: int) -> bool:
    """Return whether a rate-limit snapshot can still describe this window."""
    if get_number(window.get("used_percentage")) is None:
        return False

    resets_at = get_number(window.get("resets_at"))
    return resets_at is None or resets_at > now


def merge_window(
    cached: dict[str, Any], incoming: dict[str, Any], now: int
) -> tuple[dict[str, Any], bool]:
    """Keep the newest rate-limit window and its highest observed usage.

    Statusline refresh timers can repeatedly submit an old session snapshot.
    Reset times identify a newer window; within one window, consumed usage is
    monotonic, so the highest observation is the safest account-wide value.
    """
    cached = copy_window(cached)
    incoming = copy_window(incoming)
    cached_current = window_is_current(cached, now)
    incoming_current = window_is_current(incoming, now)

    if not cached_current and not incoming_current:
        return {}, False
    if incoming_current and not cached_current:
        return incoming, True
    if cached_current and not incoming_current:
        return cached, False

    cached_reset = get_number(cached.get("resets_at"))
    incoming_reset = get_number(incoming.get("resets_at"))
    if incoming_reset is not None and cached_reset is not None:
        if incoming_reset > cached_reset:
            return incoming, True
        if incoming_reset < cached_reset:
            return cached, False
    elif incoming_reset is not None:
        return incoming, True
    elif cached_reset is not None:
        return cached, False

    cached_used = get_number(cached.get("used_percentage"))
    incoming_used = get_number(incoming.get("used_percentage"))
    if incoming_used is not None and (
        cached_used is None or incoming_used > cached_used
    ):
        return incoming, True

    return cached, False


def build_cache(payload: dict[str, Any]) -> dict[str, Any]:
    model = get_dict(payload.get("model"))
    context_window = get_dict(payload.get("context_window"))
    rate_limits = get_dict(payload.get("rate_limits"))

    current_usage = get_dict(context_window.get("current_usage"))
    context_cache: dict[str, Any] = {}
    for key in (
        "used_percentage",
        "remaining_percentage",
        "context_window_size",
        "total_input_tokens",
        "total_output_tokens",
        "exceeds_200k_tokens",
    ):
        value = context_window.get(key)
        if isinstance(value, bool):
            context_cache[key] = value
        else:
            number = get_number(value)
            if number is not None:
                context_cache[key] = number

    if current_usage:
        context_cache["current_usage"] = {
            key: value
            for key, value in current_usage.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }

    cache = {
        "version": 2,
        "updated_at": int(time.time()),
        "model": {
            "id": model.get("id"),
            "display_name": model.get("display_name"),
        },
        "context_window": context_cache,
        "rate_limits": {
            "five_hour": copy_window(get_dict(rate_limits.get("five_hour"))),
            "seven_day": copy_window(get_dict(rate_limits.get("seven_day"))),
        },
    }
    return cache


def read_cache() -> dict[str, Any]:
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
        return cache if isinstance(cache, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def merge_cache(incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge one session snapshot into the account-wide cache under a lock."""
    CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = int(time.time())

    with LOCK_FILE.open("a+", encoding="utf-8") as lock_handle:
        os.chmod(LOCK_FILE, 0o600)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        cached = read_cache()
        cached_limits = get_dict(cached.get("rate_limits"))
        incoming_limits = get_dict(incoming.get("rate_limits"))
        merged_limits: dict[str, dict[str, Any]] = {}
        incoming_has_newer_limit = False

        for name in WINDOW_NAMES:
            merged_window, incoming_won = merge_window(
                get_dict(cached_limits.get(name)),
                get_dict(incoming_limits.get(name)),
                now,
            )
            merged_limits[name] = merged_window
            incoming_has_newer_limit = incoming_has_newer_limit or incoming_won

        has_current_limit = any(merged_limits.values())
        incoming_matches_merged = has_current_limit and all(
            not merged_limits[name]
            or copy_window(get_dict(incoming_limits.get(name))) == merged_limits[name]
            for name in WINDOW_NAMES
        )
        use_incoming_snapshot = (
            not cached
            or incoming_has_newer_limit
            or not has_current_limit
            or incoming_matches_merged
        )

        snapshot_source = incoming if use_incoming_snapshot else cached
        merged = {
            "version": 2,
            "model": get_dict(snapshot_source.get("model")),
            "context_window": get_dict(snapshot_source.get("context_window")),
            "rate_limits": merged_limits,
        }

        cached_comparable = {
            key: value for key, value in cached.items() if key != "updated_at"
        }
        if merged == cached_comparable:
            merged["updated_at"] = int(cached.get("updated_at") or now)
        else:
            merged["updated_at"] = now

        write_cache(merged)
        return merged


def write_cache(cache: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".status.", suffix=".json", dir=CACHE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, CACHE_FILE)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def pct(value: Any) -> str | None:
    number = get_number(value)
    if number is None:
        return None
    return f"{number:.0f}%"


def statusline_text(cache: dict[str, Any]) -> str:
    model = get_dict(cache.get("model"))
    rate_limits = get_dict(cache.get("rate_limits"))
    context_window = get_dict(cache.get("context_window"))
    five_hour = get_dict(rate_limits.get("five_hour"))
    weekly = get_dict(rate_limits.get("seven_day"))

    model_name = model.get("display_name") or model.get("id") or "Claude"
    five_hour_used = get_number(five_hour.get("used_percentage"))
    weekly_used = get_number(weekly.get("used_percentage"))
    context_pct = pct(context_window.get("used_percentage"))

    if weekly_used is not None and (
        five_hour_used is None or weekly_used > five_hour_used
    ):
        return f"{model_name} 7d {pct(weekly_used)}"
    if five_hour_used is not None:
        return f"{model_name} 5h {pct(five_hour_used)}"
    if context_pct:
        return f"{model_name} ctx {context_pct}"
    return str(model_name)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("statusline input was not a JSON object")

        cache = merge_cache(build_cache(payload))
        print(statusline_text(cache))
        return 0
    except Exception as exc:
        print(f"Claude status unavailable: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
