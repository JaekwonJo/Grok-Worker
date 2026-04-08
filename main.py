import traceback
from pathlib import Path
from tkinter import messagebox

from grok_worker.ui import GrokWorkerApp


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    try:
        app = GrokWorkerApp(base_dir)
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
