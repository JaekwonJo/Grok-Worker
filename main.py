import argparse
import re
import traceback
from pathlib import Path
from tkinter import messagebox

from grok_worker.config import CONFIG_FILE
from grok_worker.ui import GrokWorkerApp


def _slugify(text: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_-]+", "_", str(text or "").strip())
    return raw.strip("_") or "worker"


def _default_config_name(instance: str) -> str:
    if not instance:
        return CONFIG_FILE
    return f"grok_worker_config_{_slugify(instance)}.json"


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--instance", default="", help="병렬 실행용 워커 인스턴스 이름")
    parser.add_argument("--config", default="", help="설정 파일 이름")
    parser.add_argument("--attach-url", default="", help="기존 Edge 연결 주소")
    parser.add_argument("--worker-name", default="", help="창에 표시할 워커 이름")
    args = parser.parse_args()
    config_name = str(args.config or "").strip() or _default_config_name(str(args.instance or "").strip())
    try:
        app = GrokWorkerApp(
            base_dir,
            config_name=config_name,
            instance_key=str(args.instance or "").strip(),
            forced_attach_url=str(args.attach_url or "").strip() or None,
            forced_worker_name=str(args.worker_name or "").strip() or None,
        )
        app.run()
    except Exception:
        crash_path = base_dir / "CRASH_LOG.txt"
        crash_text = traceback.format_exc()
        try:
            crash_path.write_text(crash_text, encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror("Grok Worker 실행 실패", f"프로그램 시작 중 오류가 발생했습니다.\n\n자세한 내용: {crash_path}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
