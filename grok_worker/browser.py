from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable


LogFn = Callable[[str], None]


class BrowserManager:
    def __init__(self, log: LogFn | None = None):
        self.log = log or (lambda message: None)
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()

    def open_project(self, url: str, profile_dir: str) -> None:
        if self.thread and self.thread.is_alive():
            self.log("브라우저 작업봇 창이 이미 열려 있습니다.")
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run_browser,
            args=(str(url or "").strip(), str(profile_dir or "").strip()),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run_browser(self, url: str, profile_dir: str) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self.log(f"Playwright 로드 실패: {exc}")
            return

        target_url = url or "https://grok.com/imagine"
        profile_path = Path(profile_dir).resolve()
        profile_path.mkdir(parents=True, exist_ok=True)

        self.log(f"브라우저 작업봇 창 열기: {target_url}")
        with sync_playwright() as p:
            context = None
            try:
                try:
                    context = p.chromium.launch_persistent_context(
                        str(profile_path),
                        headless=False,
                        channel="msedge",
                        viewport={"width": 1380, "height": 920},
                        accept_downloads=True,
                    )
                except Exception:
                    context = p.chromium.launch_persistent_context(
                        str(profile_path),
                        headless=False,
                        viewport={"width": 1380, "height": 920},
                        accept_downloads=True,
                    )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(target_url, wait_until="domcontentloaded")
                self.log("브라우저 준비 완료")
                while not self.stop_event.wait(0.5):
                    pass
            except Exception as exc:
                self.log(f"브라우저 실행 실패: {exc}")
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass
                self.log("브라우저 작업봇 창 종료")
