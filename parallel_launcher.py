from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_edge_executable() -> str:
    candidates = [
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("Microsoft Edge executable was not found.")


def find_python_command() -> str:
    pythonw = shutil.which("pythonw")
    if pythonw:
        return pythonw
    return sys.executable


def launch_edge(base_dir: Path, edge_exe: str, index: int) -> None:
    port = 9221 + index
    profile_dir = base_dir / "runtime" / f"edge_attach_profile_{index}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            edge_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--new-window",
            "https://grok.com/imagine",
        ],
        cwd=str(base_dir),
    )


def launch_worker(base_dir: Path, python_cmd: str, index: int) -> None:
    port = 9221 + index
    subprocess.Popen(
        [
            python_cmd,
            "main.py",
            "--instance",
            f"worker{index}",
            "--attach-url",
            f"http://127.0.0.1:{port}",
            "--worker-name",
            f"Grok_Worker{index}",
        ],
        cwd=str(base_dir),
    )


def main() -> int:
    raw = (sys.argv[1] if len(sys.argv) > 1 else "2").strip()
    if raw not in {"2", "3"}:
        print("[ERROR] Please enter 2 or 3.")
        return 1

    count = int(raw)
    base_dir = Path(__file__).resolve().parent
    edge_exe = find_edge_executable()
    python_cmd = find_python_command()

    print(f"[INFO] Preparing {count} parallel workers.")
    for index in range(1, count + 1):
        port = 9221 + index
        print(f"[INFO] Opening Edge {index} on port {port}")
        launch_edge(base_dir, edge_exe, index)

    print("[INFO] Waiting 2 seconds before opening worker windows...")
    time.sleep(2.0)

    for index in range(1, count + 1):
        port = 9221 + index
        print(f"[INFO] Opening worker {index} on port {port}")
        launch_worker(base_dir, python_cmd, index)

    print("[INFO] Done. Sign in with different accounts in each Edge window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
