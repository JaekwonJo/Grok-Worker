from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .prompt_parser import PromptBlock, load_prompt_blocks


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

