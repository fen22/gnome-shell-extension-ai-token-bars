#!/usr/bin/env python3
"""Configure Claude Code to feed AI Token Bars through statusLine."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        if path.exists():
            os.chmod(tmp_path, path.stat().st_mode & 0o777)
        else:
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def main() -> int:
    script_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else (
        Path.home() / ".claude" / "ai-token-bars-statusline.py"
    )
    settings_path = Path.home() / ".claude" / "settings.json"

    if settings_path.exists():
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        backup_path = settings_path.with_name(f"{settings_path.name}.bak-ai-token-bars-{int(time.time())}")
        backup_path.write_bytes(settings_path.read_bytes())
    else:
        data = {}
        backup_path = None

    data["statusLine"] = {
        "type": "command",
        "command": f"/usr/bin/python3 {script_path}",
        "refreshInterval": 30,
        "padding": 0,
    }

    atomic_write_json(settings_path, data)
    print(f"Configured Claude Code statusLine: {settings_path}")
    if backup_path:
        print(f"Backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
