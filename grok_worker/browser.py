from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


LogFn = Callable[[str], None]


class BrowserManager:
    def __init__(self, log: LogFn | None = None):
        self.log = log or (lambda message: None)
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.current_launch_mode = ""
        self.current_attach_url = ""
        self.current_profile_dir = ""
        self.current_target_url = ""

    def open_project(self, url: str, profile_dir: str, launch_mode: str = "managed", attach_url: str = "") -> None:
        if self.thread and self.thread.is_alive():
            self.log("브라우저 작업봇 창이 이미 열려 있습니다.")
            return
        self.current_launch_mode = str(launch_mode or "").strip().lower()
        self.current_attach_url = str(attach_url or "").strip()
        self.current_profile_dir = str(profile_dir or "").strip()
        self.current_target_url = str(url or "").strip()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run_browser,
            args=(
                str(url or "").strip(),
                str(profile_dir or "").strip(),
                str(launch_mode or "").strip().lower(),
                str(attach_url or "").strip(),
            ),
            daemon=True,
        )
        self.thread.start()

    def stop(self, close_window: bool = False) -> None:
        self.stop_event.set()
        if close_window and self.current_launch_mode == "edge_attach":
            self._close_edge_attach_browser(self.current_attach_url)

    def _run_browser(self, url: str, profile_dir: str, launch_mode: str, attach_url: str) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self.log(f"Playwright 로드 실패: {exc}")
            return

        target_url = url or "https://grok.com/imagine"
        profile_path = Path(profile_dir).resolve()
        mode = launch_mode or "managed"
        should_close_context = False

        if mode != "edge_attach":
            profile_path.mkdir(parents=True, exist_ok=True)
            self.log(f"브라우저 작업봇 창 열기: {target_url}")
        else:
            self._ensure_edge_attach_browser(target_url, profile_path, attach_url)
            self.log(f"기존 Edge 창 연결 시도: {attach_url or 'http://127.0.0.1:9222'}")
        with sync_playwright() as p:
            context = None
            try:
                if mode == "edge_attach":
                    browser = p.chromium.connect_over_cdp(attach_url or "http://127.0.0.1:9222")
                    context = self._pick_context(browser, target_url)
                    page = self._pick_page(context, target_url, allow_fallback_first=False)
                    if page is None:
                        page = context.new_page()
                    if target_url not in str(page.url or ""):
                        page.goto(target_url, wait_until="domcontentloaded")
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass
                else:
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
                    should_close_context = True
                    page = self._pick_page(context, target_url, allow_fallback_first=True)
                    if page is None:
                        page = context.new_page()
                    page.goto(target_url, wait_until="domcontentloaded")
                self.log("브라우저 준비 완료")
                while not self.stop_event.wait(0.5):
                    pass
            except Exception as exc:
                self.log(f"브라우저 실행 실패: {exc}")
            finally:
                if should_close_context and context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass
                if mode == "edge_attach":
                    self.log("기존 Edge 연결 종료")
                else:
                    self.log("브라우저 작업봇 창 종료")

    def _ensure_edge_attach_browser(self, target_url: str, profile_path: Path, attach_url: str) -> None:
        port = self._extract_port(attach_url)
        if port <= 0 or self._is_port_open(port):
            return
        edge_exe = self._find_edge_executable()
        profile_path.mkdir(parents=True, exist_ok=True)
        self.log(f"🚀 Edge 자동 실행: 포트 {port}")
        subprocess.Popen(
            [
                edge_exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_path}",
                "--new-window",
                target_url or "https://grok.com/imagine",
            ],
            cwd=str(profile_path.parent),
        )
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if self._is_port_open(port):
                return
            time.sleep(0.25)
        raise RuntimeError(f"Edge 자동 실행은 했지만 포트 {port} 연결 준비가 늦습니다.")

    def _close_edge_attach_browser(self, attach_url: str) -> None:
        port = self._extract_port(attach_url)
        if port <= 0 or not self._is_port_open(port):
            return
        script = (
            "$targets = Get-CimInstance Win32_Process -Filter \"name = 'msedge.exe'\" "
            f"| Where-Object {{ $_.CommandLine -match '--remote-debugging-port={port}' }}; "
            "foreach ($proc in $targets) { "
            "try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.log(f"🛑 연결된 Edge 종료: 포트 {port}")
        except Exception as exc:
            self.log(f"⚠️ 연결된 Edge 종료 실패: {exc}")

    def _extract_port(self, attach_url: str) -> int:
        try:
            parsed = urlparse(str(attach_url or "").strip())
            return int(parsed.port or 0)
        except Exception:
            return 0

    def _is_port_open(self, port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
                return True
        except Exception:
            return False

    def _find_edge_executable(self) -> str:
        candidates = [
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(candidate)
        raise RuntimeError("Microsoft Edge 실행 파일을 찾지 못했습니다.")

    def _pick_context(self, browser, target_url: str):
        contexts = list(browser.contexts or [])
        if not contexts:
            raise RuntimeError("연결된 Edge에서 사용할 브라우저 컨텍스트를 찾지 못했습니다.")
        target_url = str(target_url or "").strip()
        for context in contexts:
            for page in list(context.pages or []):
                try:
                    if target_url and target_url in str(page.url or ""):
                        return context
                except Exception:
                    continue
        return contexts[0]

    def _pick_page(self, context, target_url: str, allow_fallback_first: bool = True):
        pages = [page for page in list(context.pages or []) if page and (not page.is_closed())]
        if not pages:
            return None
        target_url = str(target_url or "").strip()
        if target_url:
            for page in pages:
                try:
                    if target_url in str(page.url or ""):
                        return page
                except Exception:
                    continue
        for page in pages:
            try:
                url = str(page.url or "")
            except Exception:
                url = ""
            if "grok.com" in url:
                return page
        if allow_fallback_first:
            return pages[0]
        return None
