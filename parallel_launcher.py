from __future__ import annotations

import shutil
import subprocess
import sys
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


def worker_window_geometry(index: int) -> str:
    geometries = {
        1: "920x560+20+520",
        2: "920x560+980+520",
        3: "920x560+20+520",
    }
    return geometries.get(index, f"920x560+{20 + (index - 1) * 420}+520")


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
            f"Grok Worker{index}",
            "--geometry",
            worker_window_geometry(index),
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
    python_cmd = find_python_command()

    print(f"[INFO] Preparing {count} parallel workers.")
    print("[INFO] Edge는 사용자가 먼저 직접 열고 로그인해야 합니다.")
    print("[INFO] Worker 1 -> http://127.0.0.1:9222")
    if count >= 2:
        print("[INFO] Worker 2 -> http://127.0.0.1:9223")
    if count >= 3:
        print("[INFO] Worker 3 -> http://127.0.0.1:9224")

    for index in range(1, count + 1):
        port = 9221 + index
        print(f"[INFO] Opening worker {index} on port {port}")
        launch_worker(base_dir, python_cmd, index)

    print("[INFO] Done. 각 워커에 맞는 Edge 창에 로그인한 뒤 사용하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
