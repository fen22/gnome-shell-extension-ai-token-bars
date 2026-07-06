#!/usr/bin/env python3
"""Cache Claude Code statusline usage for the GNOME token bar."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


CACHE_DIR = Path.home() / ".cache" / "claude-token-bar"
CACHE_FILE = CACHE_DIR / "status.json"


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
        "version": 1,
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

    model_name = model.get("display_name") or model.get("id") or "Claude"
    five_hour_pct = pct(five_hour.get("used_percentage"))
    context_pct = pct(context_window.get("used_percentage"))

    if five_hour_pct:
        return f"{model_name} 5h {five_hour_pct}"
    if context_pct:
        return f"{model_name} ctx {context_pct}"
    return str(model_name)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("statusline input was not a JSON object")

        cache = build_cache(payload)
        write_cache(cache)
        print(statusline_text(cache))
        return 0
    except Exception as exc:
        print(f"Claude status unavailable: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
