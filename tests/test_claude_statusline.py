from __future__ import annotations

import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType


def load_statusline_module() -> ModuleType:
    script = Path(__file__).resolve().parents[1] / "scripts" / "claude-statusline.py"
    spec = importlib.util.spec_from_file_location("claude_statusline", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {script}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CacheMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_statusline_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        cache_dir = Path(self.temp_dir.name) / "claude-token-bar"
        self.module.CACHE_DIR = cache_dir
        self.module.CACHE_FILE = cache_dir / "status.json"
        self.module.LOCK_FILE = cache_dir / "status.lock"
        self.now = int(time.time())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def payload(
        self,
        *,
        model: str,
        context: int,
        five_hour_used: int,
        five_hour_reset: int,
        weekly_used: int,
        weekly_reset: int,
    ) -> dict[str, object]:
        return {
            "model": {"id": model, "display_name": model},
            "context_window": {"used_percentage": context},
            "rate_limits": {
                "five_hour": {
                    "used_percentage": five_hour_used,
                    "resets_at": five_hour_reset,
                },
                "seven_day": {
                    "used_percentage": weekly_used,
                    "resets_at": weekly_reset,
                },
            },
        }

    def merge(self, payload: dict[str, object]) -> dict[str, object]:
        return self.module.merge_cache(self.module.build_cache(payload))

    def test_stale_idle_writer_cannot_replace_current_limits(self) -> None:
        weekly_reset = self.now + 5 * 24 * 60 * 60
        stale = self.payload(
            model="Stale session",
            context=5,
            five_hour_used=16,
            five_hour_reset=self.now - 60,
            weekly_used=10,
            weekly_reset=weekly_reset,
        )
        current = self.payload(
            model="Current session",
            context=9,
            five_hour_used=13,
            five_hour_reset=self.now + 4 * 60 * 60,
            weekly_used=19,
            weekly_reset=weekly_reset,
        )

        self.merge(stale)
        merged = self.merge(current)
        current_updated_at = merged["updated_at"]
        merged = self.merge(stale)

        self.assertEqual(merged["rate_limits"]["five_hour"]["used_percentage"], 13)
        self.assertEqual(merged["rate_limits"]["seven_day"]["used_percentage"], 19)
        self.assertEqual(merged["context_window"]["used_percentage"], 9)
        self.assertEqual(merged["model"]["display_name"], "Current session")
        self.assertEqual(merged["updated_at"], current_updated_at)

    def test_new_reset_window_replaces_higher_usage_from_old_window(self) -> None:
        weekly_reset = self.now + 5 * 24 * 60 * 60
        old_window = self.payload(
            model="Old window",
            context=20,
            five_hour_used=99,
            five_hour_reset=self.now + 60,
            weekly_used=20,
            weekly_reset=weekly_reset,
        )
        new_window = self.payload(
            model="New window",
            context=1,
            five_hour_used=1,
            five_hour_reset=self.now + 5 * 60 * 60,
            weekly_used=21,
            weekly_reset=weekly_reset,
        )

        self.merge(old_window)
        merged = self.merge(new_window)

        self.assertEqual(merged["rate_limits"]["five_hour"]["used_percentage"], 1)
        self.assertEqual(merged["rate_limits"]["seven_day"]["used_percentage"], 21)

    def test_statusline_uses_limit_closest_to_exhaustion(self) -> None:
        cache = self.module.build_cache(
            self.payload(
                model="Claude",
                context=9,
                five_hour_used=13,
                five_hour_reset=self.now + 4 * 60 * 60,
                weekly_used=19,
                weekly_reset=self.now + 5 * 24 * 60 * 60,
            )
        )

        self.assertEqual(self.module.statusline_text(cache), "Claude 7d 19%")


if __name__ == "__main__":
    unittest.main()
