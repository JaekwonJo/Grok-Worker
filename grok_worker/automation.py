from __future__ import annotations

import mimetypes
import random
import re
import time
import math
from datetime import datetime
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
        download_dir = self._resolve_download_dir()
        typing_delay_ms = self._typing_delay_ms()
        generate_wait_seconds = self._generate_wait_seconds()
        next_prompt_wait_seconds = self._next_prompt_wait_seconds()
        break_every_count = self._break_every_count()
        break_minutes = self._break_minutes()
        media_mode = self._media_mode()

        set_status("브라우저 준비 중")
        log(f"🌐 Grok 실행 시작 | {plan.selection_summary}")
        log("📝 그록워커 방식: 프롬프트 안의 @S001/@S994 같은 참조를 먼저 업로드하고, 입력 중에는 Image 1~5 선택으로 처리합니다.")
        log(f"⏱️ 생성 후 다운로드 대기: {generate_wait_seconds:.1f}초 | 다운로드 후 다음 작업 대기: {next_prompt_wait_seconds:.1f}초")
        log(f"🎛️ 작업 모드: {self._media_summary()}")

        with sync_playwright() as p:
            context = None
            close_context = False
            try:
                context, page, close_context = self._open_browser_session(
                    playwright=p,
                    profile_dir=profile_dir,
                    site_url=site_url,
                    log=log,
                )
                self._wait_for_grok_input(page)

                total = len(plan.items)
                for idx, item in enumerate(plan.items, start=1):
                    if should_stop():
                        set_status("중지됨")
                        log("⏹️ 사용자 중지 요청으로 작업을 멈췄습니다.")
                        return
                    wait_if_paused()
                    update_queue(item.number, "running", f"{item.tag} 실행 중", "")
                    completed = False
                    max_attempts = 2
                    for attempt in range(1, max_attempts + 1):
                        if attempt > 1:
                            update_queue(item.number, "running", f"{item.tag} 재시도 {attempt - 1}/1", "")
                            log(f"🔁 {item.tag} 재시도 {attempt - 1}/1 시작")
                        set_status(f"{item.tag} {('비디오' if media_mode == 'video' else '이미지')} 옵션 맞추는 중")
                        self._apply_generation_settings(page, item.tag, log, set_status)
                        set_status(f"{item.tag} 입력 중 ({idx}/{total})")
                        log(f"✍️ 프롬프트 입력 시작: {item.tag}")
                        try:
                            self._run_single_item(
                                page=page,
                                item=item,
                                typing_delay_ms=typing_delay_ms,
                                log=log,
                                set_status=set_status,
                                should_stop=should_stop,
                                wait_if_paused=wait_if_paused,
                            )
                            image_path = self._download_latest_result(
                                page=page,
                                item=item,
                                download_dir=download_dir,
                                timeout_seconds=generate_wait_seconds,
                                log=log,
                                set_status=set_status,
                                should_stop=should_stop,
                                wait_if_paused=wait_if_paused,
                            )
                            update_queue(item.number, "success", f"저장: {image_path.name}", image_path.name)
                            set_status(f"{item.tag} 완료")
                            log(f"✅ 저장 완료: {image_path.name}")
                            self._wait_after_download(
                                seconds=next_prompt_wait_seconds,
                                log=log,
                                set_status=set_status,
                                item_tag=item.tag,
                                should_stop=should_stop,
                                wait_if_paused=wait_if_paused,
                            )
                            set_status(f"{item.tag} 처음 화면 복귀 중")
                            self._reset_for_next_prompt(page, log)
                            completed = True
                            break
                        except Exception as exc:
                            self._save_debug_screenshot(page, item.tag, log)
                            if attempt < max_attempts and not should_stop():
                                log(f"⚠️ {item.tag} 실패, 1회 재시도합니다: {exc}")
                                set_status(f"{item.tag} 재시도 준비")
                                self._safe_recover(page, log)
                                continue
                            update_queue(item.number, "failed", str(exc), "")
                            set_status(f"{item.tag} 실패")
                            log(f"❌ {item.tag} 실패: {exc}")
                            self._safe_recover(page, log)
                    if not completed and should_stop():
                        set_status("중지됨")
                        return
                    if (
                        idx < total
                        and break_every_count > 0
                        and break_minutes > 0
                        and idx % break_every_count == 0
                    ):
                        self._take_random_break(
                            count=idx,
                            minutes=break_minutes,
                            log=log,
                            set_status=set_status,
                            should_stop=should_stop,
                            wait_if_paused=wait_if_paused,
                        )
                set_status("전체 완료")
            finally:
                if close_context and context is not None:
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

    def _humanize_enabled(self) -> bool:
        return bool(self.cfg.get("humanize_typing", True))

    def _generate_wait_seconds(self) -> float:
        raw = float(self.cfg.get("generate_wait_seconds", 5.0) or 0.0)
        return max(0.0, raw)

    def _next_prompt_wait_seconds(self) -> float:
        raw = float(self.cfg.get("next_prompt_wait_seconds", 2.0) or 0.0)
        return max(0.0, raw)

    def _site_url(self) -> str:
        return str(self.cfg.get("grok_site_url") or "https://grok.com/imagine").strip() or "https://grok.com/imagine"

    def _break_every_count(self) -> int:
        raw = int(self.cfg.get("break_every_count", 0) or 0)
        return max(0, raw)

    def _break_minutes(self) -> float:
        raw = float(self.cfg.get("break_minutes", 0.0) or 0.0)
        return max(0.0, raw)

    def _media_mode(self) -> str:
        return str(self.cfg.get("media_mode") or "image").strip().lower() or "image"

    def _video_quality(self) -> str:
        return str(self.cfg.get("video_quality") or "720p").strip() or "720p"

    def _video_duration(self) -> str:
        return str(self.cfg.get("video_duration") or "10s").strip() or "10s"

    def _aspect_ratio(self) -> str:
        return str(self.cfg.get("aspect_ratio") or "16:9").strip() or "16:9"

    def _media_summary(self) -> str:
        if self._media_mode() == "video":
            return f"비디오 | {self._video_quality()} | {self._video_duration()} | {self._aspect_ratio()}"
        return f"이미지 | {self._aspect_ratio()}"

    def _browser_launch_mode(self) -> str:
        return str(self.cfg.get("browser_launch_mode") or "managed").strip().lower() or "managed"

    def _browser_attach_url(self) -> str:
        return str(self.cfg.get("browser_attach_url") or "http://127.0.0.1:9222").strip() or "http://127.0.0.1:9222"

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

    def _open_browser_session(self, *, playwright, profile_dir: Path, site_url: str, log: LogFn):
        mode = self._browser_launch_mode()
        if mode == "edge_attach":
            attach_url = self._browser_attach_url()
            log(f"🔌 기존 Edge 창 연결 시도: {attach_url}")
            browser = playwright.chromium.connect_over_cdp(attach_url)
            context = self._pick_browser_context(browser, site_url)
            page = self._pick_browser_page(context, site_url, allow_fallback_first=False)
            if page is None:
                page = context.new_page()
            if site_url not in str(page.url or ""):
                page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.bring_to_front()
            except Exception:
                pass
            log("🌐 기존 Edge 창 연결 완료")
            return context, page, False

        context = self._launch_context(playwright, profile_dir)
        page = self._pick_browser_page(context, site_url, allow_fallback_first=True)
        if page is None:
            page = context.new_page()
        page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
        return context, page, True

    def _pick_browser_context(self, browser, site_url: str):
        contexts = list(browser.contexts or [])
        if not contexts:
            raise RuntimeError("연결된 Edge에서 사용할 브라우저 컨텍스트를 찾지 못했습니다.")
        site_url = str(site_url or "").strip()
        for context in contexts:
            for page in list(context.pages or []):
                try:
                    if site_url and site_url in str(page.url or ""):
                        return context
                except Exception:
                    continue
        return contexts[0]

    def _pick_browser_page(self, context, site_url: str, allow_fallback_first: bool = True):
        pages = [page for page in list(context.pages or []) if page and (not page.is_closed())]
        if not pages:
            return None
        site_url = str(site_url or "").strip()
        if site_url:
            for page in pages:
                try:
                    if site_url in str(page.url or ""):
                        return page
                except Exception:
                    continue
        for page in pages:
            try:
                page_url = str(page.url or "")
            except Exception:
                page_url = ""
            if "grok.com" in page_url:
                return page
        if allow_fallback_first:
            return pages[0]
        return None

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

    def _apply_generation_settings(self, page, item_tag: str, log: LogFn, set_status: StatusFn) -> None:
        mode = self._media_mode()
        targets = [("모드", "비디오" if mode == "video" else "이미지")]
        if mode == "video":
            targets.append(("품질", self._video_quality()))
            targets.append(("길이", self._video_duration()))
        targets.append(("비율", self._aspect_ratio()))
        for label, target in targets:
            set_status(f"{item_tag} {label} 설정 중")
            if label == "비율":
                success = self._set_aspect_ratio(page, target)
            else:
                success = self._click_generation_option(page, target)
            if success:
                log(f"🎚️ {label} 설정: {target}")
            else:
                log(f"⚠️ {label} 설정 버튼을 못 찾아 그대로 진행: {target}")
            time.sleep(0.12)
        self._dismiss_generation_overlay(page)

    def _click_generation_option(self, page, label: str) -> bool:
        input_loc = self._find_prompt_input(page)
        input_box = None
        if input_loc is not None:
            try:
                input_box = input_loc.bounding_box()
            except Exception:
                input_box = None
        target = str(label or "").strip().lower().replace(" ", "")
        best = None
        best_score = -1.0
        for selector in ("button", "[role='button']", "div"):
            try:
                count = min(page.locator(selector).count(), 140)
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
                    if input_box and box["y"] < (input_box["y"] - 80):
                        continue
                    text = (loc.inner_text(timeout=80) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    blob = f"{text} {aria}".lower().replace(" ", "")
                    if target not in blob:
                        continue
                    score = 0.0
                    if input_box:
                        score += 1800 - abs((box["y"] + box["height"] / 2.0) - (input_box["y"] + input_box["height"] / 2.0))
                        score += 600 - min(600, abs(box["x"] - input_box["x"]))
                    if 24 <= box["height"] <= 56:
                        score += 120
                    if 24 <= box["width"] <= 180:
                        score += 120
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        if best is None:
            return False
        best.click(timeout=4000)
        return True

    def _dismiss_generation_overlay(self, page) -> None:
        for _ in range(2):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.08)

    def _set_aspect_ratio(self, page, target: str) -> bool:
        target = str(target or "").strip()
        input_loc = self._find_prompt_input(page)
        input_box = None
        if input_loc is not None:
            try:
                input_box = input_loc.bounding_box()
            except Exception:
                input_box = None

        trigger = None
        best_score = -1.0
        ratio_tokens = {"2:3", "3:2", "1:1", "9:16", "16:9"}
        for selector in ("button", "[role='button']", "div"):
            try:
                count = min(page.locator(selector).count(), 140)
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
                    text = (loc.inner_text(timeout=80) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    blob = f"{text} {aria}"
                    if not any(token in blob for token in ratio_tokens):
                        continue
                    score = 0.0
                    if input_box:
                        if box["y"] < (input_box["y"] - 80):
                            continue
                        score += 1800 - abs((box["y"] + box["height"] / 2.0) - (input_box["y"] + input_box["height"] / 2.0))
                        score += 600 - min(600, abs(box["x"] - input_box["x"]))
                    if target in blob:
                        score += 2000
                    if 24 <= box["height"] <= 56:
                        score += 120
                    if score > best_score:
                        best_score = score
                        trigger = loc
                except Exception:
                    continue

        if trigger is None:
            return False

        try:
            current_text = (trigger.inner_text(timeout=80) or "").strip()
        except Exception:
            current_text = ""
        try:
            current_aria = (trigger.get_attribute("aria-label") or "").strip()
        except Exception:
            current_aria = ""
        current_blob = f"{current_text} {current_aria}"
        if target in current_blob:
            return True

        trigger.click(timeout=4000)
        time.sleep(0.2)

        option = None
        for selector in ("button", "[role='option']", "[role='button']", "div", "span"):
            try:
                count = min(page.locator(selector).count(), 160)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = page.locator(selector).nth(idx)
                    if not loc.is_visible():
                        continue
                    text = (loc.inner_text(timeout=80) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    if text == target or aria == target:
                        option = loc
                        break
                except Exception:
                    continue
            if option is not None:
                break

        if option is None:
            return False
        option.click(timeout=4000)
        time.sleep(0.15)
        return True

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

    def _find_plus_button(self, page, input_loc=None):
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        input_box = None
        if input_loc is not None:
            try:
                input_box = input_loc.bounding_box()
            except Exception:
                input_box = None
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
                    area = float(box["width"]) * float(box["height"])
                    if input_box:
                        center_y = box["y"] + (box["height"] / 2.0)
                        input_mid_y = input_box["y"] + (input_box["height"] / 2.0)
                        vertical_gap = abs(center_y - input_mid_y)
                        if vertical_gap < max(60, input_box["height"] * 1.2):
                            score += 2200
                        else:
                            score -= 700
                        left_gap = input_box["x"] - (box["x"] + box["width"])
                        if -30 <= left_gap <= 180:
                            score += 2400
                        else:
                            score -= 900
                        if box["x"] <= input_box["x"] + 60:
                            score += 900
                    if area > 6000:
                        score -= 5000
                    elif 700 <= area <= 5000:
                        score += 800
                    if box["y"] > viewport["height"] * 0.55:
                        score += 300
                    else:
                        score -= 1500
                    if box["x"] < 60:
                        score -= 3000
                    if abs(box["width"] - box["height"]) < 18:
                        score += 120
                    if text == "+" or aria == "+":
                        score += 700
                    if "추가" in text or "Add" in text or "plus" in aria.lower():
                        score += 400
                    if text and text not in {"+"}:
                        score -= 400
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        return best

    def _run_single_item(
        self,
        *,
        page,
        item: PromptBlock,
        typing_delay_ms: int,
        log: LogFn,
        set_status: StatusFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> None:
        set_status(f"{item.tag} 입력창 준비")
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
        reference_slots = self._build_reference_slots(item.rendered_prompt)
        log(f"📌 필요 이미지 수: {len(reference_slots)}")
        if reference_slots:
            slot_summary = ", ".join(f"Image {slot}=@{token}" for token, slot in sorted(reference_slots.items(), key=lambda item: item[1]))
            log(f"🧩 참조 슬롯 순서: {slot_summary}")
        if reference_slots:
            set_status(f"{item.tag} 참조 업로드 중")
            self._upload_prompt_reference_images(page, reference_slots, log)
            input_loc = self._find_prompt_input(page)
            if input_loc is None:
                raise RuntimeError("이미지 선택 후 프롬프트 입력창을 다시 찾지 못했습니다.")
            input_loc.click(timeout=5000)
            time.sleep(0.15)
        for part in self._split_prompt_parts(item.rendered_prompt):
            if should_stop():
                raise RuntimeError("사용자 중지")
            wait_if_paused()
            if part["type"] == "text":
                text = str(part["value"] or "")
                if text:
                    set_status(f"{item.tag} 프롬프트 입력 중")
                    self._type_text_human_like(
                        page=page,
                        text=text,
                        base_delay_ms=typing_delay_ms,
                        should_stop=should_stop,
                        wait_if_paused=wait_if_paused,
                    )
                continue
            ref_token = self._normalize_reference_token(str(part["value"] or ""))
            ref_idx = reference_slots.get(ref_token)
            if ref_idx is None:
                raise RuntimeError(f"참조 이미지 매핑을 찾지 못했습니다: @{ref_token}")
            set_status(f"{item.tag} Image {ref_idx} 선택 중")
            self._attach_reference_token(page, ref_idx, log)
            log(f"🔖 레퍼런스 선택: @{ref_token} -> Image {ref_idx}")
        input_loc = self._find_prompt_input(page)
        submit = self._find_submit_button(page, input_loc)
        if submit is None:
            log("⚠️ 전송 버튼 미탐: Enter 제출 폴백으로 진행합니다.")
        else:
            log(f"🧭 제출 버튼 후보: {self._describe_locator(submit)}")
        set_status(f"{item.tag} 제출 시도")
        self._submit_prompt(page=page, input_loc=input_loc, submit=submit, log=log)
        log("📨 전송 완료")

    def _split_prompt_parts(self, rendered_prompt: str) -> list[dict]:
        parts: list[dict] = []
        last = 0
        for match in REFERENCE_TOKEN_RE.finditer(rendered_prompt):
            if match.start() > last:
                parts.append({"type": "text", "value": rendered_prompt[last:match.start()]})
            parts.append({"type": "reference", "value": str(match.group(1) or "").upper()})
            last = match.end()
        if last < len(rendered_prompt):
            parts.append({"type": "text", "value": rendered_prompt[last:]})
        return parts

    def _type_text_human_like(
        self,
        *,
        page,
        text: str,
        base_delay_ms: int,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> None:
        typo_pool = "abcdefghijklmnopqrstuvwxyz"
        typed_since_pause = 0
        for ch in text:
            if should_stop():
                raise RuntimeError("사용자 중지")
            wait_if_paused()
            if ch == "\n":
                page.keyboard.press("Shift+Enter")
                typed_since_pause = 0
                time.sleep(random.uniform(0.05, 0.16))
                continue
            delay = max(8, int(base_delay_ms * random.uniform(0.7, 1.5)))
            if self._humanize_enabled() and ch.isalpha() and random.random() < 0.015:
                typo = random.choice(typo_pool)
                if typo.lower() == ch.lower():
                    typo = "x"
                page.keyboard.type(typo, delay=delay)
                time.sleep(random.uniform(0.03, 0.12))
                page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.02, 0.08))
            page.keyboard.type(ch, delay=delay)
            typed_since_pause += 1
            if not self._humanize_enabled():
                continue
            if ch in ",.;:)":
                time.sleep(random.uniform(0.04, 0.14))
                typed_since_pause = 0
                continue
            if ch == " " and typed_since_pause >= random.randint(6, 14):
                time.sleep(random.uniform(0.06, 0.22))
                typed_since_pause = 0
                continue
            if random.random() < 0.01:
                time.sleep(random.uniform(0.08, 0.28))

    def _submit_prompt(self, *, page, input_loc, submit, log: LogFn) -> None:
        before_text = self._read_prompt_input_text(input_loc)
        modes = ("click", "force", "enter") if submit is not None else ("enter", "ctrl_enter")
        for attempt, mode in enumerate(modes, start=1):
            try:
                if mode == "click":
                    submit.click(timeout=3000)
                elif mode == "force":
                    submit.click(timeout=3000, force=True)
                elif mode == "ctrl_enter":
                    input_loc.click(timeout=3000)
                    time.sleep(0.1)
                    page.keyboard.press("Control+Enter")
                else:
                    input_loc.click(timeout=3000)
                    time.sleep(0.1)
                    page.keyboard.press("Enter")
                if self._wait_for_submit_effect(page, input_loc, submit, before_text):
                    log(f"✅ 제출 성공 확인: {mode}")
                    return
                log(f"⚠️ 제출 확인 실패: {mode}")
            except Exception as exc:
                log(f"⚠️ 제출 시도 {attempt} 실패({mode}): {exc}")
            time.sleep(0.35)
        raise RuntimeError("제출 버튼을 눌렀지만 실제 제출이 시작되지 않았습니다.")

    def _read_prompt_input_text(self, input_loc) -> str:
        for reader in (
            lambda: input_loc.input_value(timeout=200),
            lambda: input_loc.inner_text(timeout=200),
            lambda: input_loc.text_content(timeout=200),
        ):
            try:
                value = reader()
                if value is not None:
                    return str(value).strip()
            except Exception:
                continue
        return ""

    def _wait_for_submit_effect(self, page, input_loc, submit, before_text: str) -> bool:
        deadline = time.time() + 2.5
        before_len = len(before_text.strip())
        while time.time() < deadline:
            try:
                current_text = self._read_prompt_input_text(input_loc)
            except Exception:
                current_text = ""
            current_len = len(current_text.strip())
            if before_len > 0 and current_len <= max(2, int(before_len * 0.3)):
                return True
            if submit is not None:
                try:
                    aria = (submit.get_attribute("aria-label") or "").strip().lower()
                except Exception:
                    aria = ""
                try:
                    text = (submit.inner_text(timeout=100) or "").strip().lower()
                except Exception:
                    text = ""
                if any(token in aria for token in ("stop", "cancel", "중지", "정지")):
                    return True
                if any(token in text for token in ("stop", "cancel", "중지", "정지")):
                    return True
                try:
                    disabled = (submit.get_attribute("disabled") or "").strip().lower()
                    aria_disabled = (submit.get_attribute("aria-disabled") or "").strip().lower()
                except Exception:
                    disabled = ""
                    aria_disabled = ""
                if disabled in {"true", "disabled"} or aria_disabled == "true":
                    return True
                try:
                    if not submit.is_visible():
                        return True
                except Exception:
                    return True
            time.sleep(0.15)
        return False

    def _normalize_reference_token(self, token: str) -> str:
        cleaned = str(token or "").strip().upper().lstrip("@")
        if not cleaned:
            return ""
        if cleaned.startswith("S") and cleaned[1:].isdigit():
            return f"S{int(cleaned[1:]):03d}"
        return cleaned

    def _attach_reference_token(self, page, ref_idx: int, log: LogFn) -> None:
        last_error = None
        for attempt, mode in enumerate(("insert", "type", "shift2"), start=1):
            try:
                self._open_reference_picker(page, mode)
                option = self._find_reference_option(page, ref_idx)
                if option is not None:
                    log(f"📎 Image {ref_idx} 선택 후보: {self._describe_locator(option)}")
                    option.click(timeout=5000)
                else:
                    log(f"⌨️ Image {ref_idx} 키보드 선택 시도")
                    self._select_reference_option_with_keyboard(page, ref_idx)
                time.sleep(0.25)
                return
            except Exception as exc:
                last_error = exc
                log(f"⚠️ @ 선택창 시도 {attempt} 실패: {exc}")
                time.sleep(0.35)
        raise RuntimeError(f"Image {ref_idx} 선택창을 열지 못했습니다: {last_error}")

    def _open_reference_picker(self, page, mode: str) -> None:
        if mode == "insert":
            page.keyboard.insert_text("@")
        elif mode == "shift2":
            try:
                page.keyboard.press("Shift+2")
            except Exception:
                page.keyboard.press("@")
        else:
            page.keyboard.type("@", delay=20)
        time.sleep(0.45)

    def _find_reference_option(self, page, ref_idx: int, timeout_ms: int = 5000):
        normalized_targets = {f"IMAGE{ref_idx}", f"IMAGE {ref_idx}".replace(" ", "")}
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            for selector in ("button", "[role='button']", "[role='option']", "div", "li", "span"):
                try:
                    locs = page.locator(selector)
                    count = min(locs.count(), 120)
                except Exception:
                    continue
                for idx in range(count):
                    try:
                        loc = locs.nth(idx)
                        if not loc.is_visible():
                            continue
                        text = (loc.inner_text(timeout=80) or "").strip().upper().replace(" ", "")
                        aria = (loc.get_attribute("aria-label") or "").strip().upper().replace(" ", "")
                        if text in normalized_targets or aria in normalized_targets:
                            return loc
                    except Exception:
                        continue
            time.sleep(0.15)
        return None

    def _select_reference_option_with_keyboard(self, page, ref_idx: int) -> None:
        for _ in range(max(0, ref_idx - 1)):
            page.keyboard.press("ArrowDown")
            time.sleep(0.08)
        page.keyboard.press("Enter")

    def _build_reference_slots(self, rendered_prompt: str) -> dict[str, int]:
        token_stats: dict[str, dict[str, int]] = {}
        for match in REFERENCE_TOKEN_RE.finditer(str(rendered_prompt or "")):
            token = self._normalize_reference_token(str(match.group(1) or ""))
            if not token:
                continue
            stat = token_stats.setdefault(token, {"count": 0, "first_pos": match.start()})
            stat["count"] += 1
            stat["first_pos"] = min(stat["first_pos"], match.start())
        ordered = sorted(
            token_stats.items(),
            key=lambda item: (-int(item[1]["count"]), int(item[1]["first_pos"])),
        )
        return {token: idx for idx, (token, _meta) in enumerate(ordered, start=1)}

    def _upload_prompt_reference_images(self, page, reference_slots: dict[str, int], log: LogFn) -> None:
        files = self._resolve_reference_files(reference_slots, log)
        if not files:
            return
        input_loc = self._find_prompt_input(page)
        input_box = None
        if input_loc is not None:
            try:
                input_box = input_loc.bounding_box()
            except Exception:
                input_box = None

        opened = False
        if input_box:
            click_x = max(12.0, float(input_box["x"]) - 28.0)
            click_y = float(input_box["y"]) + (float(input_box["height"]) / 2.0)
            log(f"➕ + 버튼 좌표 클릭 시도: ({click_x:.1f}, {click_y:.1f})")
            page.mouse.click(click_x, click_y)
            time.sleep(0.5)
            if self._find_upload_trigger(page) is not None:
                opened = True

        if not opened:
            plus = self._find_plus_button(page, input_loc)
            if plus is None:
                raise RuntimeError("이미지 선택용 + 버튼을 찾지 못했습니다.")
            log(f"➕ 이미지 패널 열기 버튼: {self._describe_locator(plus)}")
            plus.click(timeout=5000)
            time.sleep(0.7)

        upload_trigger = self._find_upload_trigger(page)
        if upload_trigger is None:
            raise RuntimeError("업로드 영역을 찾지 못했습니다.")
        log(f"🗂️ 업로드 영역: {self._describe_locator(upload_trigger)}")
        file_paths = [str(path) for path in files]
        log(f"🪜 참조 이미지 순차 업로드: {len(file_paths)}개")
        for idx, file_path in enumerate(file_paths, start=1):
            file_name = Path(file_path).name
            log(f"🖼️ 참조 이미지 업로드 {idx}/{len(file_paths)}: {file_name}")
            if self._try_set_input_files_direct(page, [file_path], log):
                time.sleep(1.2)
                continue
            try:
                with page.expect_file_chooser(timeout=8000) as chooser_info:
                    upload_trigger.click(timeout=5000)
                chooser = chooser_info.value
                chooser.set_files([file_path])
                time.sleep(1.2)
            except Exception as exc:
                raise RuntimeError(f"참조 이미지 업로드 창을 열지 못했습니다: {exc}") from exc
        log(f"🖼️ 참조 이미지 업로드 완료: {len(file_paths)}개")
        time.sleep(1.5)
        return

    def _find_upload_trigger(self, page):
        candidates = []
        for selector in ("button", "[role='button']", "div", "label"):
            try:
                locator = page.locator(selector)
                count = min(locator.count(), 80)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = locator.nth(idx)
                    if not loc.is_visible():
                        continue
                    text = (loc.inner_text(timeout=100) or "").strip()
                    aria = (loc.get_attribute("aria-label") or "").strip()
                    box = loc.bounding_box()
                    if not box:
                        continue
                    blob = f"{text} {aria}".lower()
                    if "업로드" not in blob and "upload" not in blob and "드롭" not in blob:
                        continue
                    score = 0.0
                    if box["x"] < 260:
                        score += 300
                    if box["y"] < 260:
                        score += 300
                    score += min(box["width"] * box["height"], 50000)
                    candidates.append((score, loc))
                except Exception:
                    continue
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _try_set_input_files_direct(self, page, file_paths: list[str], log: LogFn) -> bool:
        try:
            inputs = page.locator("input[type='file']")
            count = min(inputs.count(), 8)
        except Exception:
            return False
        for idx in range(count):
            try:
                loc = inputs.nth(idx)
                loc.set_input_files(file_paths, timeout=5000)
                log("🗂️ 파일 입력 요소에 직접 업로드")
                return True
            except Exception:
                continue
        return False

    def _resolve_reference_files(self, reference_slots: dict[str, int], log: LogFn) -> list[Path]:
        resolved: list[Path] = []
        for token, slot in sorted(reference_slots.items(), key=lambda item: item[1]):
            path = self._find_reference_file(token)
            if path is None:
                raise RuntimeError(f"참조 이미지 파일을 찾지 못했습니다: @{token}")
            log(f"🗂️ 참조 파일 매핑: @{token} -> Image {slot} -> {path.name}")
            resolved.append(path)
        return resolved

    def _find_reference_file(self, token: str) -> Path | None:
        token = self._normalize_reference_token(token)
        if not token:
            return None
        search_roots = [self._resolve_download_dir()]
        candidates: list[Path] = []
        for root in search_roots:
            if not root or not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
                    continue
                candidates.append(path)
        exact_targets = self._reference_file_variants(token)
        for path in candidates:
            stem = path.stem.upper()
            if stem in exact_targets:
                return path
        for path in candidates:
            stem = path.stem.upper()
            if any(stem.startswith(prefix) for prefix in exact_targets):
                return path
        return None

    def _reference_file_variants(self, token: str) -> set[str]:
        variants = {token, f"@{token}"}
        if token.startswith("S") and token[1:].isdigit():
            number = int(token[1:])
            variants.update(
                {
                    f"S{number}",
                    f"S{number:03d}",
                    f"@S{number}",
                    f"@S{number:03d}",
                }
            )
        return {item.upper() for item in variants if item}

    def _wait_for_reference_panel_images(self, page, needed_refs: int):
        deadline = time.time() + 8.0
        best = []
        while time.time() < deadline:
            best = self._collect_reference_panel_images(page)
            if len(best) >= needed_refs:
                return best
            time.sleep(0.25)
        return best

    def _collect_reference_panel_images(self, page):
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        candidates = []
        seen = set()
        try:
            image_locator = page.locator("img")
            count = min(image_locator.count(), 120)
        except Exception:
            return []

        for idx in range(count):
            try:
                img = image_locator.nth(idx)
                if not img.is_visible():
                    continue
                box = img.bounding_box()
                if not box:
                    continue
                x = float(box.get("x") or 0.0)
                y = float(box.get("y") or 0.0)
                w = float(box.get("width") or 0.0)
                h = float(box.get("height") or 0.0)
                if w < 28 or h < 28:
                    continue
                if w > 220 or h > 220:
                    continue
                if y > viewport["height"] * 0.72:
                    continue
                if x < viewport["width"] * 0.22:
                    continue
                key = (round(x, 1), round(y, 1), round(w, 1), round(h, 1))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(((y, x), img))
            except Exception:
                continue

        candidates.sort(key=lambda item: item[0])
        return [img for _meta, img in candidates]

    def _describe_locator(self, locator) -> str:
        if locator is None:
            return "-"
        text = ""
        aria = ""
        box = None
        try:
            text = (locator.inner_text(timeout=100) or "").strip()
        except Exception:
            text = ""
        try:
            aria = (locator.get_attribute("aria-label") or "").strip()
        except Exception:
            aria = ""
        try:
            box = locator.bounding_box()
        except Exception:
            box = None
        if box:
            return (
                f"text='{text[:40]}' aria='{aria[:40]}' "
                f"box=({float(box.get('x') or 0.0):.1f},{float(box.get('y') or 0.0):.1f},"
                f"{float(box.get('width') or 0.0):.1f},{float(box.get('height') or 0.0):.1f})"
            )
        return f"text='{text[:40]}' aria='{aria[:40]}'"

    def _save_debug_screenshot(self, page, tag: str, log: LogFn) -> None:
        logs_dir = self.base_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        safe_tag = re.sub(r"[^A-Za-z0-9_-]+", "_", str(tag or "unknown"))
        path = logs_dir / f"{safe_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            log(f"🖼️ 실패 스크린샷 저장: {path}")
        except Exception as exc:
            log(f"⚠️ 실패 스크린샷 저장 실패: {exc}")

    def _find_submit_button(self, page, input_loc=None):
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        input_box = None
        if input_loc is not None:
            try:
                input_box = input_loc.bounding_box()
            except Exception:
                input_box = None
        best = None
        best_score = -1.0
        for selector in ("button", "[role='button']", "div", "span"):
            try:
                count = min(page.locator(selector).count(), 140)
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
                    if input_box:
                        if (box["x"] + box["width"]) < (input_box["x"] + input_box["width"] - 140):
                            continue
                        center_y = box["y"] + (box["height"] / 2.0)
                        input_mid_y = input_box["y"] + (input_box["height"] / 2.0)
                        if abs(center_y - input_mid_y) < max(60, input_box["height"] * 1.6):
                            score += 2600
                        else:
                            score -= 1500
                        right_edge_gap = abs((box["x"] + box["width"]) - (input_box["x"] + input_box["width"]))
                        if right_edge_gap < 36:
                            score += 2600
                        elif right_edge_gap < 90:
                            score += 1400
                        else:
                            score -= 1200
                        if box["x"] < input_box["x"] - 40:
                            score -= 1200
                    if box["y"] > viewport["height"] * 0.55:
                        score += 200
                    if box["x"] > viewport["width"] * 0.75:
                        score += 120
                    if abs(box["width"] - box["height"]) < 20:
                        score += 200
                    if box["width"] <= 80 and box["height"] <= 80:
                        score += 250
                    if "전송" in text or "Send" in text or "submit" in aria.lower():
                        score += 1000
                    lowered_text = text.lower()
                    lowered_aria = aria.lower()
                    if "이미지" in text or "image" in lowered_text or "image" in lowered_aria:
                        score -= 3500
                    if "비디오" in text or "video" in lowered_text or "video" in lowered_aria:
                        score -= 3500
                    if "업로드" in text or "upload" in lowered_text or "upload" in lowered_aria:
                        score -= 4000
                    if "저장" in text or "저장" in aria or "save" in text.lower() or "save" in aria.lower():
                        score -= 4000
                    if "공유" in text or "share" in lowered_text or "share" in lowered_aria:
                        score -= 3000
                    if score > best_score:
                        best_score = score
                        best = loc
                except Exception:
                    continue
        if best is not None and best_score > -900:
            return best

        fallback = None
        fallback_score = -1.0
        for selector in ("button", "[role='button']", "div", "span"):
            try:
                count = min(page.locator(selector).count(), 180)
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
                    lowered_text = text.lower()
                    lowered_aria = aria.lower()
                    if "이미지" in text or "image" in lowered_text or "image" in lowered_aria:
                        continue
                    if "비디오" in text or "video" in lowered_text or "video" in lowered_aria:
                        continue
                    if "업로드" in text or "upload" in lowered_text or "upload" in lowered_aria:
                        continue
                    if "공유" in text or "share" in lowered_text or "share" in lowered_aria:
                        continue
                    if any(token in lowered_text for token in ("480p", "720p", "6s", "10s", "16:9", "9:16", "1:1", "2:3", "3:2")):
                        continue
                    if any(token in lowered_aria for token in ("480p", "720p", "6s", "10s", "16:9", "9:16", "1:1", "2:3", "3:2")):
                        continue
                    score = 0.0
                    if box["x"] > viewport["width"] * 0.72:
                        score += 2400
                    if box["y"] > viewport["height"] * 0.72:
                        score += 2400
                    if 20 <= box["width"] <= 84 and 20 <= box["height"] <= 84:
                        score += 500
                    if abs(box["width"] - box["height"]) < 20:
                        score += 220
                    if "submit" in lowered_aria or "전송" in text or "전송" in aria:
                        score += 1800
                    if input_box:
                        center_y = box["y"] + (box["height"] / 2.0)
                        input_mid_y = input_box["y"] + (input_box["height"] / 2.0)
                        if abs(center_y - input_mid_y) < 120:
                            score += 1200
                        if box["x"] >= (input_box["x"] + input_box["width"] - 120):
                            score += 1200
                    if not text and not aria:
                        score += 80
                    if score > fallback_score:
                        fallback_score = score
                        fallback = loc
                except Exception:
                    continue
        if fallback is not None and fallback_score > 2000:
            return fallback
        return best

    def _download_latest_result(
        self,
        *,
        page,
        item: PromptBlock,
        download_dir: Path,
        timeout_seconds: float,
        log: LogFn,
        set_status: StatusFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> Path:
        log(f"⏳ 결과 생성 대기 (최대 {timeout_seconds:.1f}초)")
        download_button = self._wait_for_download_button_or_open_result(
            page=page,
            item_tag=item.tag,
            log=log,
            set_status=set_status,
            should_stop=should_stop,
            wait_if_paused=wait_if_paused,
            timeout_seconds=timeout_seconds,
        )
        if download_button is None:
            raise RuntimeError("다운로드 버튼을 찾지 못했습니다.")
        set_status(f"{item.tag} 다운로드 클릭")
        with page.expect_download(timeout=30000) as download_info:
            download_button.click(timeout=5000)
        download = download_info.value
        suggested = download.suggested_filename or f"{item.tag}.png"
        ext = Path(suggested).suffix or ".png"
        target = download_dir / f"@{item.tag}{ext}"
        target = self._unique_path(target)
        download.save_as(str(target))
        return target

    def _wait_after_download(
        self,
        *,
        seconds: float,
        log: LogFn,
        set_status: StatusFn,
        item_tag: str,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> None:
        if seconds <= 0:
            return
        log(f"⏳ 다운로드 후 {seconds:.1f}초 대기")
        self._controlled_sleep(
            seconds=seconds,
            should_stop=should_stop,
            wait_if_paused=wait_if_paused,
            on_tick=lambda remain: set_status(f"{item_tag} 다음 작업 대기 {remain}초"),
        )

    def _take_random_break(
        self,
        *,
        count: int,
        minutes: float,
        log: LogFn,
        set_status: StatusFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
    ) -> None:
        seconds = max(1.0, minutes * 60.0 * random.uniform(0.7, 1.3))
        log(f"☕ 휴식 시작: {count}개 작업 후 {seconds:.1f}초 랜덤 휴식")
        self._controlled_sleep(
            seconds=seconds,
            should_stop=should_stop,
            wait_if_paused=wait_if_paused,
            on_tick=lambda remain: set_status(f"휴식 중 {remain}초"),
        )

    def _controlled_sleep(
        self,
        seconds: float,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
        on_tick: Callable[[int], None] | None = None,
    ) -> None:
        deadline = time.time() + max(0.0, seconds)
        last_remaining = None
        while time.time() < deadline:
            if should_stop():
                raise RuntimeError("사용자 중지")
            wait_if_paused()
            if on_tick is not None:
                remaining = max(0, int(math.ceil(deadline - time.time())))
                if remaining != last_remaining:
                    last_remaining = remaining
                    on_tick(remaining)
            time.sleep(min(0.2, max(0.0, deadline - time.time())))

    def _wait_for_download_button_or_open_result(
        self,
        *,
        page,
        item_tag: str,
        log: LogFn,
        set_status: StatusFn,
        should_stop: StopFn,
        wait_if_paused: PauseFn,
        timeout_seconds: float,
    ):
        deadline = time.time() + max(0.5, timeout_seconds)
        opened_result = False
        last_remaining = None
        extended_once = False
        while time.time() < deadline:
            if should_stop():
                return None
            wait_if_paused()
            remaining = max(0, int(math.ceil(deadline - time.time())))
            if remaining != last_remaining:
                last_remaining = remaining
                set_status(f"{item_tag} 생성 대기 {remaining}초")
            button = self._locate_download_button(page)
            if button is not None:
                return button
            if not opened_result:
                try:
                    set_status(f"{item_tag} 결과 카드 여는 중")
                    self._open_latest_result_card(page)
                    opened_result = True
                    time.sleep(0.6)
                    continue
                except Exception:
                    pass
            time.sleep(0.4)
            if time.time() >= deadline and not extended_once and self._should_extend_download_wait(page):
                deadline += 12.0
                extended_once = True
                log("⌛ 다운로드 버튼이 아직 안 떠서 12초 추가 대기합니다.")
        return None

    def _should_extend_download_wait(self, page) -> bool:
        patterns = ("더보기", "생성 중", "생성", "%")
        for pattern in patterns:
            try:
                loc = page.get_by_text(pattern, exact=False)
                if loc.count() and loc.first.is_visible():
                    return True
            except Exception:
                continue
        return False

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
                    lowered_text = text.lower()
                    lowered_aria = aria.lower()
                    if "다운로드" in text or "download" in lowered_text or "download" in lowered_aria:
                        if not self._locator_is_enabled(loc):
                            continue
                        return loc
                except Exception:
                    continue
        try:
            label = page.get_by_text("다운로드", exact=False)
            if label.count() and self._locator_is_enabled(label.first):
                return label.first
        except Exception:
            pass
        viewport = page.viewport_size or {"width": 1440, "height": 940}
        toolbar_candidates = []
        for selector in ("button", "[role='button']"):
            try:
                locator = page.locator(selector)
                count = min(locator.count(), 80)
            except Exception:
                continue
            for idx in range(count):
                try:
                    loc = locator.nth(idx)
                    if not loc.is_visible():
                        continue
                    box = loc.bounding_box()
                    if not box:
                        continue
                    if box["x"] < viewport["width"] * 0.70:
                        continue
                    if not (24 <= box["width"] <= 72 and 24 <= box["height"] <= 72):
                        continue
                    if box["y"] < viewport["height"] * 0.12 or box["y"] > viewport["height"] * 0.95:
                        continue
                    if not self._locator_is_enabled(loc):
                        continue
                    toolbar_candidates.append((float(box["y"]), loc))
                except Exception:
                    continue
        if len(toolbar_candidates) >= 3:
            toolbar_candidates.sort(key=lambda item: item[0])
            # 오른쪽 세로 아이콘에서 아래에서 3번째가 다운로드 버튼인 경우가 많습니다.
            return toolbar_candidates[-3][1]
        return None

    def _locator_is_enabled(self, locator) -> bool:
        try:
            disabled = str(locator.get_attribute("disabled") or "").strip().lower()
            if disabled in {"true", "disabled"}:
                return False
        except Exception:
            pass
        try:
            aria_disabled = str(locator.get_attribute("aria-disabled") or "").strip().lower()
            if aria_disabled == "true":
                return False
        except Exception:
            pass
        try:
            if not locator.is_enabled():
                return False
        except Exception:
            pass
        return True

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
        site_url = self._site_url()
        try:
            close_btn = page.locator("button").filter(has_text="닫기").first
            if close_btn.count() and close_btn.is_visible():
                close_btn.click(timeout=1200)
        except Exception:
            pass
        try:
            page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
            self._wait_for_grok_input(page)
            log("🏠 처음 Grok 화면으로 돌아가서 다음 작업 준비 완료")
        except Exception:
            pass

    def _safe_recover(self, page, log: LogFn) -> None:
        try:
            page.goto(self._site_url(), wait_until="domcontentloaded", timeout=60000)
            self._wait_for_grok_input(page)
            log("♻️ 실패 후 처음 Grok 화면으로 복구")
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
