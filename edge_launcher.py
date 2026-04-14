from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


DEFAULT_URL = "https://grok.com/imagine"
DEFAULT_OUTER_WIDTH = 1000
DEFAULT_OUTER_HEIGHT = 1040


def _load_position(config_path: Path) -> tuple[int | None, int | None]:
    if not config_path.exists():
        return None, None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    try:
        left = int(data.get("edge_window_left"))
        top = int(data.get("edge_window_top"))
    except Exception:
        return None, None
    return left, top


def _load_browser_profile_dir(config_path: Path, fallback: str) -> Path:
    profile_raw = str(fallback or "").strip()
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        configured = str(data.get("browser_profile_dir") or "").strip()
        if configured and configured != "runtime/browser_profile_1":
            profile_raw = configured
    profile_path = Path(profile_raw)
    if not profile_path.is_absolute():
        profile_path = config_path.parent / profile_path
    return profile_path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--profile-dir", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--width", default=DEFAULT_OUTER_WIDTH, type=int)
    parser.add_argument("--height", default=DEFAULT_OUTER_HEIGHT, type=int)
    args = parser.parse_args()

    profile_dir = _load_browser_profile_dir(Path(args.config).resolve(), args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    config_path = Path(args.config).resolve()
    left, top = _load_position(config_path)

    edge_args = [
        "msedge",
        f"--remote-debugging-port={int(args.port)}",
        f"--user-data-dir={str(profile_dir)}",
        f"--window-size={max(760, int(args.width))},{max(700, int(args.height))}",
        "--new-window",
        str(args.url or DEFAULT_URL).strip() or DEFAULT_URL,
    ]
    if left is not None and top is not None:
        edge_args.insert(3, f"--window-position={left},{top}")

    subprocess.Popen(["cmd.exe", "/c", "start", "", *edge_args])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
