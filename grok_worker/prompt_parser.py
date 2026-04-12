from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REFERENCE_TOKEN_RE = re.compile(r"@((?:[Ss]\d+)|(?:[1-5]))\b")


@dataclass
class PromptBlock:
    number: int
    tag: str
    body: str
    rendered_prompt: str
    raw: str
    references: list[str]


def _normalize_body(body: str) -> str:
    lines = [line.rstrip() for line in str(body or "").splitlines()]
    return "\n".join(lines).strip()


def _render_prompt(prefix: str, number: int, pad_width: int, body: str) -> tuple[str, str]:
    tag = f"{prefix}{str(number).zfill(max(3, int(pad_width or 3)))}"
    body_text = _normalize_body(body)
    return tag, f"{tag} Prompt : {body_text}"


def _normalize_prompt_chunk(chunk: str) -> str:
    lines = [line.rstrip() for line in str(chunk or "").splitlines()]
    return "\n".join(lines).strip()


def parse_prompt_blocks(
    raw_text: str,
    *,
    prefix: str = "S",
    pad_width: int = 3,
    separator: str = "|||",
) -> list[PromptBlock]:
    chunks = [part.strip() for part in str(raw_text or "").split(separator) if part.strip()]
    items: list[PromptBlock] = []
    for chunk in chunks:
        normalized_chunk = _normalize_prompt_chunk(chunk)
        if not normalized_chunk:
            continue

        lines = normalized_chunk.splitlines()
        first_line = str(lines[0] or "").strip() if lines else ""
        rest_lines = lines[1:]
        number = None
        body = ""
        tag = ""
        rendered = normalized_chunk

        labeled_match = re.match(
            rf"^\s*({re.escape(prefix)}\s*0*([1-9][0-9]*))\s*(?:PROMPT|프롬프트)\s*:\s*(.*)\s*$",
            first_line,
            re.IGNORECASE | re.DOTALL,
        )
        if labeled_match:
            number = int(labeled_match.group(2))
            tag = f"{prefix}{str(number).zfill(max(3, int(pad_width or 3)))}"
            inline_body = str(labeled_match.group(3) or "").strip()
            body_parts = []
            if inline_body:
                body_parts.append(inline_body)
            if rest_lines:
                body_parts.append("\n".join(rest_lines).strip())
            body = _normalize_body("\n".join(part for part in body_parts if part.strip()))
        else:
            inline_match = re.match(r"^\s*0*([1-9][0-9]*)\s*:\s*(.*)\s*$", first_line, re.DOTALL)
            if inline_match:
                number = int(inline_match.group(1))
                inline_body = str(inline_match.group(2) or "").strip()
                body_parts = []
                if inline_body:
                    body_parts.append(inline_body)
                if rest_lines:
                    body_parts.append("\n".join(rest_lines).strip())
                body = _normalize_body("\n".join(part for part in body_parts if part.strip()))
                tag, rendered = _render_prompt(prefix, number, pad_width, body)
            else:
                multi_match = re.match(r"^\s*0*([1-9][0-9]*)\s*:\s*$", first_line)
                if not multi_match:
                    continue
                number = int(multi_match.group(1))
                body = _normalize_body("\n".join(rest_lines))
                tag, rendered = _render_prompt(prefix, number, pad_width, body)

        if not number or not body:
            continue

        refs: list[str] = []
        seen_refs: set[str] = set()
        for match in REFERENCE_TOKEN_RE.finditer(rendered):
            token = str(match.group(1) or "").upper()
            if not token or token in seen_refs:
                continue
            seen_refs.add(token)
            refs.append(token)
        items.append(
            PromptBlock(
                number=number,
                tag=tag,
                body=body,
                rendered_prompt=rendered,
                raw=normalized_chunk,
                references=refs,
            )
        )
    items.sort(key=lambda item: item.number)
    return items


def load_prompt_blocks(
    path: Path,
    *,
    prefix: str = "S",
    pad_width: int = 3,
    separator: str = "|||",
) -> list[PromptBlock]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    return parse_prompt_blocks(raw, prefix=prefix, pad_width=pad_width, separator=separator)


def summarize_prompt_file(
    path: Path,
    *,
    prefix: str = "S",
    pad_width: int = 3,
    separator: str = "|||",
) -> str:
    items = load_prompt_blocks(path, prefix=prefix, pad_width=pad_width, separator=separator)
    if not items:
        return f"{path.name} | 프롬프트 없음"
    return f"{path.name} | 총 {len(items)}개 | {items[0].number:03d}~{items[-1].number:03d}"


def compress_numbers(numbers: Iterable[int], prefix: str = "") -> str:
    nums = sorted({int(n) for n in numbers if int(n) > 0})
    if not nums:
        return ""
    ranges: list[str] = []
    start = prev = nums[0]
    for value in nums[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(_format_range(start, prev, prefix))
        start = prev = value
    ranges.append(_format_range(start, prev, prefix))
    return ",".join(ranges)


def _format_range(start: int, end: int, prefix: str = "") -> str:
    left = f"{prefix}{start:03d}"
    right = f"{prefix}{end:03d}"
    if start == end:
        return left
    return f"{left}-{right}"
