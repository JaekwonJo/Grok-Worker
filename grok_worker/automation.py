from __future__ import annotations

import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .prompt_parser import PromptBlock, REFERENCE_TOKEN_RE, load_prompt_blocks


LogFn = Callable[[str], None]
StatusFn = Callable[[str], None]
QueueFn = Callable[[int, str, str, str], None]
StopFn = Callable[[], bool]
PauseFn = Callable[[], None]

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class RunPlan:
    items: list[PromptBlock]
    selection_summary: str


class GrokAutomationEngine:
    def __init__(self, base_dir: Path, cfg: dict):
        self.base_dir = Path(base_dir)
        self.cfg = cfg

    def build_plan(self) -> RunPlan:
        prompt_slots = list(self.cfg.get("prompt_slots") or [])
        if not prompt_slots:
            return RunPlan(items=[], selection_summary="프롬프트 파일 없음")
        slot_index = max(0, min(int(self.cfg.get("prompt_slot_index", 0) or 0), len(prompt_slots) - 1))
        slot = prompt_slots[slot_index]
        path = self.base_dir / str(slot.get("file") or "")
        items = load_prompt_blocks(
            path,
            prefix=str(self.cfg.get("prompt_prefix") or "S"),
            pad_width=int(self.cfg.get("prompt_pad_width", 3) or 3),
            separator=str(self.cfg.get("prompt_separator") or "|||"),
        )
        selected = self._filter_items(items)
        summary = self._selection_summary(selected)
        return RunPlan(items=selected, selection_summary=summary)

    def run(
        self,
        *,
        plan: RunPlan,
        log: LogFn,
        set_status: StatusFn,
        update_queue: QueueFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> None:
        if not plan.items:
            set_status("선택된 작업 없음")
            return

        site_url = str(self.cfg.get("grok_site_url") or "https://grok.com/imagine").strip()
        profile_dir = self._resolve_profile_dir()
        reference_files = self._reference_files_for_run(plan.items)
        download_dir = self._resolve_download_dir()
        typing_delay_ms = self._typing_delay_ms()

        set_status("브라우저 준비 중")
        log(f"🌐 Grok 실행 시작 | {plan.selection_summary}")
        if reference_files:
            log(f"🖼️ 레퍼런스 이미지 {len(reference_files)}개 사용: {', '.join(path.name for path in reference_files)}")
        else:
            log("🖼️ 레퍼런스 이미지 없음: 텍스트만으로 진행")

        with sync_playwright() as p:
            context = None
            try:
                context = self._launch_context(p, profile_dir)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
                self._wait_for_grok_input(page)
                if reference_files:
                    set_status("레퍼런스 업로드 준비")
                    self._prepare_reference_library(page, reference_files, log)

                total = len(plan.items)
                for idx, item in enumerate(plan.items, start=1):
                    if should_stop():
                        set_status("중지됨")
                        log("⏹️ 사용자 중지 요청으로 작업을 멈췄습니다.")
                        return
                    wait_if_paused()
                    update_queue(item.number, "running", f"{item.tag} 실행 중", "")
                    set_status(f"{item.tag} 입력 중 ({idx}/{total})")
                    log(f"✍️ 프롬프트 입력 시작: {item.tag}")
                    try:
                        self._run_single_item(
                            page=page,
                            item=item,
                            reference_count=len(reference_files),
                            typing_delay_ms=typing_delay_ms,
                            log=log,
                            should_stop=should_stop,
                            wait_if_paused=wait_if_paused,
                        )
                        set_status(f"{item.tag} 생성 대기")
                        image_path = self._download_latest_result(
                            page=page,
                            item=item,
                            download_dir=download_dir,
                            log=log,
                            should_stop=should_stop,
                            wait_if_paused=wait_if_paused,
                        )
                        update_queue(item.number, "success", f"저장: {image_path.name}", image_path.name)
                        set_status(f"{item.tag} 완료")
                        log(f"✅ 저장 완료: {image_path.name}")
                        self._reset_for_next_prompt(page, log)
                    except Exception as exc:
                        update_queue(item.number, "failed", str(exc), "")
                        set_status(f"{item.tag} 실패")
                        log(f"❌ {item.tag} 실패: {exc}")
                        self._safe_recover(page, log)
                set_status("전체 완료")
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass

    def _filter_items(self, items: list[PromptBlock]) -> list[PromptBlock]:
        mode = str(self.cfg.get("number_mode") or "range").strip().lower()
        if mode == "manual":
            wanted = set(self._parse_manual_numbers(str(self.cfg.get("manual_numbers") or "")))
            return [item for item in items if item.number in wanted]
        start = int(self.cfg.get("start_number", 1) or 1)
        end = int(self.cfg.get("end_number", start) or start)
        lo, hi = min(start, end), max(start, end)
        return [item for item in items if lo <= item.number <= hi]

    def _parse_manual_numbers(self, raw: str) -> list[int]:
        result: set[int] = set()
        for part in str(raw or "").replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                left, right = part.split("-", 1)
                if left.isdigit() and right.isdigit():
                    lo, hi = sorted((int(left), int(right)))
                    result.update(range(lo, hi + 1))
                continue
            if part.isdigit():
                result.add(int(part))
        return sorted(result)

    def _selection_summary(self, items: list[PromptBlock]) -> str:
        if not items:
            return "선택된 작업 없음"
        preview = ", ".join(f"{item.number:03d}" for item in items[:8])
        remain = len(items) - min(len(items), 8)
        if remain > 0:
            return f"{len(items)}개 선택: {preview} 외 {remain}개"
        return f"{len(items)}개 선택: {preview}"

    def _resolve_profile_dir(self) -> Path:
        raw = str(self.cfg.get("browser_profile_dir") or "").strip()
        if not raw:
            raw = "runtime/browser_profile_1"
        path = Path(raw)
        if not path.is_absolute():
            path = self.base_dir / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_download_dir(self) -> Path:
        raw = str(self.cfg.get("download_output_dir") or "").strip()
        path = Path(raw) if raw else (self.base_dir / "downloads")
        if not path.is_absolute():
            path = self.base_dir / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _typing_delay_ms(self) -> int:
        speed = float(self.cfg.get("typing_speed", 1.0) or 1.0)
        speed = max(0.5, min(2.0, speed))
        base = 34
        return max(8, int(base / speed))

    def _reference_files_for_run(self, items: list[PromptBlock]) -> list[Path]:
        needed = 0
        for item in items:
            if item.references:
                needed = max(needed, max(item.references))
        needed = max(needed, 0)
        raw = str(self.cfg.get("reference_image_dir") or "").strip()
        if not raw:
            return []
        folder = Path(raw)
        if not folder.is_absolute():
            folder = self.base_dir / folder
        if not folder.exists():
            return []
        files = sorted(
            [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES],
            key=lambda path: path.name.lower(),
        )
        if not files:
            return []
        limit = max(needed, min(5, len(files)))
        return files[: min(5, limit)]

    def _launch_context(self, playwright, profile_dir: Path):
        kwargs = {
            "headless": False,
            "accept_downloads": True,
            "viewport": {"width": 1440, "height": 940},
        }
        try:
            return playwright.chromium.launch_persistent_context(str(profile_dir), channel="msedge", **kwargs)
        except Exception:
            return playwright.chromium.launch_persistent_context(str(profile_dir), **kwargs)

    def _wait_for_grok_input(self, page) -> None:
        candidates = [
            "textarea",
            "[contenteditable='true']",
            "textarea[placeholder*='텍스트']",
        ]
        deadline = time.time() + 30
        while time.time() < deadline:
            locator = self._find_prompt_input(page)
            if locator is not None:
                return
            for selector in candidates:
                try:
                    if page.locator(selector).count():
                        return
                except Exception:
                    continue
            time.sleep(0.5)
        raise RuntimeError("Grok 입력창을 찾지 못했습니다.")

    def _find_prompt_input(self, page):
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        best = None
        best_score = -1.0
        selectors = ["textarea", "[contenteditable='true']", "[role='textbox']"]
        for selector in selectors:
            try:
                count = min(page.locator(selector).count(), 12)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = page.locator(selector).nth(idx)
                    if not loc.is_visible():
                        continue
                    box = loc.bounding_box()
                    if not box:
                        continue
                    score = 0.0
                    if box["y"] > viewport["height"] * 0.55:
                        score += 1000
                    score += min(box["width"], 900)
                    if box["height"] >= 32:
                        score += 60
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        return best

    def _find_plus_button(self, page):
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        best = None
        best_score = -1.0
        for selector in ("button", "[role='button']"):
            try:
                count = min(page.locator(selector).count(), 40)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = page.locator(selector).nth(idx)
                    if not loc.is_visible():
                        continue
                    box = loc.bounding_box()
                    if not box:
                        continue
                    text = (loc.inner_text(timeout=200) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    score = 0.0
                    if box["y"] > viewport["height"] * 0.55:
                        score += 600
                    if box["x"] < viewport["width"] * 0.2:
                        score += 300
                    if abs(box["width"] - box["height"]) < 18:
                        score += 120
                    if text == "+" or aria == "+":
                        score += 700
                    if "추가" in text or "Add" in text or "plus" in aria.lower():
                        score += 400
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        return best

    def _prepare_reference_library(self, page, reference_files: list[Path], log: LogFn) -> None:
        upload_input = None
        try:
            upload_input = page.locator("input[type='file']").first
            if not upload_input.count():
                upload_input = None
        except Exception:
            upload_input = None
        if upload_input is None:
            plus = self._find_plus_button(page)
            if plus is None:
                raise RuntimeError("이미지 추가 + 버튼을 찾지 못했습니다.")
            plus.click(timeout=5000)
            time.sleep(0.6)
            try:
                upload_input = page.locator("input[type='file']").last
            except Exception:
                upload_input = None
        if upload_input is not None:
            upload_input.set_input_files([str(path) for path in reference_files], timeout=15000)
        else:
            upload_tile = page.get_by_text("Upload or drop", exact=False)
            with page.expect_file_chooser(timeout=10000) as chooser_info:
                upload_tile.first.click(timeout=5000)
            chooser = chooser_info.value
            chooser.set_files([str(path) for path in reference_files])
        log("🖼️ 레퍼런스 업로드 완료")
        time.sleep(2.0)
        page.reload(wait_until="domcontentloaded", timeout=60000)
        self._wait_for_grok_input(page)
        log("🔄 업로드 후 새로고침 완료")

    def _run_single_item(
        self,
        *,
        page,
        item: PromptBlock,
        reference_count: int,
        typing_delay_ms: int,
        log: LogFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> None:
        input_loc = self._find_prompt_input(page)
        if input_loc is None:
            raise RuntimeError("프롬프트 입력창을 찾지 못했습니다.")
        input_loc.click(timeout=5000)
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
        except Exception:
            pass
        time.sleep(0.2)
        for part in self._split_prompt_parts(item.rendered_prompt):
            if should_stop():
                raise RuntimeError("사용자 중지")
            wait_if_paused()
            if part["type"] == "text":
                text = str(part["value"] or "")
                if text:
                    page.keyboard.type(text, delay=typing_delay_ms)
                continue
            ref_idx = int(part["value"])
            if ref_idx > max(reference_count, 0):
                raise RuntimeError(f"레퍼런스 이미지 {ref_idx}번이 없습니다.")
            self._attach_reference_token(page, ref_idx)
            log(f"🔖 레퍼런스 첨부: @{ref_idx}")
        submit = self._find_submit_button(page)
        if submit is None:
            raise RuntimeError("전송 화살표 버튼을 찾지 못했습니다.")
        submit.click(timeout=5000)
        log("📨 전송 완료")

    def _split_prompt_parts(self, rendered_prompt: str) -> list[dict]:
        parts: list[dict] = []
        last = 0
        for match in REFERENCE_TOKEN_RE.finditer(rendered_prompt):
            if match.start() > last:
                parts.append({"type": "text", "value": rendered_prompt[last:match.start()]})
            parts.append({"type": "reference", "value": int(match.group(1))})
            last = match.end()
        if last < len(rendered_prompt):
            parts.append({"type": "text", "value": rendered_prompt[last:]})
        return parts

    def _attach_reference_token(self, page, ref_idx: int) -> None:
        page.keyboard.type("@", delay=10)
        time.sleep(0.4)
        popup = page.locator("text=Image 1")
        popup.first.wait_for(timeout=8000)
        for _ in range(max(0, ref_idx - 1)):
            page.keyboard.press("ArrowDown")
            time.sleep(0.08)
        page.keyboard.press("Enter")
        time.sleep(0.25)

    def _find_submit_button(self, page):
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        best = None
        best_score = -1.0
        for selector in ("button", "[role='button']"):
            try:
                count = min(page.locator(selector).count(), 60)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = page.locator(selector).nth(idx)
                    if not loc.is_visible():
                        continue
                    box = loc.bounding_box()
                    if not box:
                        continue
                    text = (loc.inner_text(timeout=100) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    score = 0.0
                    if box["y"] > viewport["height"] * 0.55:
                        score += 900
                    if box["x"] > viewport["width"] * 0.75:
                        score += 700
                    if abs(box["width"] - box["height"]) < 20:
                        score += 200
                    if "전송" in text or "Send" in text or "submit" in aria.lower():
                        score += 1000
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        return best

    def _download_latest_result(
        self,
        *,
        page,
        item: PromptBlock,
        download_dir: Path,
        log: LogFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> Path:
        log("⏳ 결과 생성 대기")
        download_button = self._wait_for_download_button_or_open_result(page, should_stop, wait_if_paused)
        if download_button is None:
            raise RuntimeError("다운로드 버튼을 찾지 못했습니다.")
        with page.expect_download(timeout=30000) as download_info:
            download_button.click(timeout=5000)
        download = download_info.value
        suggested = download.suggested_filename or f"{item.tag}.png"
        ext = Path(suggested).suffix or ".png"
        target = download_dir / f"{item.tag}{ext}"
        target = self._unique_path(target)
        download.save_as(str(target))
        return target

    def _wait_for_download_button_or_open_result(self, page, should_stop: StopFn, wait_if_paused: PauseFn):
        deadline = time.time() + 180
        opened_result = False
        while time.time() < deadline:
            if should_stop():
                return None
            wait_if_paused()
            button = self._locate_download_button(page)
            if button is not None:
                return button
            if not opened_result:
                try:
                    self._open_latest_result_card(page)
                    opened_result = True
                    time.sleep(1.0)
                    continue
                except Exception:
                    pass
            time.sleep(2.0)
        return None

    def _locate_download_button(self, page):
        for selector in ("button", "[role='button']"):
            try:
                locator = page.locator(selector)
                count = min(locator.count(), 40)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = locator.nth(idx)
                    if not loc.is_visible():
                        continue
                    text = (loc.inner_text(timeout=100) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    if "다운로드" in text or "download" in aria.lower():
                        return loc
                except Exception:
                    continue
        try:
            label = page.get_by_text("다운로드", exact=False)
            if label.count():
                return label.first
        except Exception:
            pass
        return None

    def _open_latest_result_card(self, page) -> None:
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        best = None
        best_score = -1.0
        for selector in ("img", "[role='img']", "button", "[role='button']"):
            try:
                count = min(page.locator(selector).count(), 80)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = page.locator(selector).nth(idx)
                    if not loc.is_visible():
                        continue
                    box = loc.bounding_box()
                    if not box:
                        continue
                    if box["y"] > viewport["height"] * 0.78:
                        continue
                    area = box["width"] * box["height"]
                    score = area
                    if box["y"] < viewport["height"] * 0.45:
                        score += 200000
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        if best is None:
            raise RuntimeError("결과 카드를 찾지 못했습니다.")
        best.click(timeout=5000)

    def _reset_for_next_prompt(self, page, log: LogFn) -> None:
        try:
            close_btn = page.locator("button").filter(has_text="닫기").first
            if close_btn.count() and close_btn.is_visible():
                close_btn.click(timeout=1200)
        except Exception:
            pass
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            self._wait_for_grok_input(page)
            log("🔄 다음 작업 준비 완료")
        except Exception:
            pass

    def _safe_recover(self, page, log: LogFn) -> None:
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            self._wait_for_grok_input(page)
            log("♻️ 실패 후 화면 복구")
        except Exception:
            log("⚠️ 실패 후 화면 복구도 실패")

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        idx = 2
        while True:
            candidate = path.with_name(f"{path.stem} ({idx}){path.suffix}")
            if not candidate.exists():
                return candidate
            idx += 1
