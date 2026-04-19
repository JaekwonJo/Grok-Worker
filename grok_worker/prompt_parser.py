from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# 한글 조사(@S999가, @S001은 등)가 바로 붙는 경우도 참조 토큰으로 인식합니다.
# ASCII 영숫자/언더스코어가 뒤에 이어질 때만 토큰 연장으로 보고 제외합니다.
REFERENCE_TOKEN_RE = re.compile(r"@((?:[Ss]\d+)|(?:[1-5]))(?![A-Za-z0-9_])")


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


def _normalize_prefix_aliases(prefix: str, extra_prefixes: Iterable[str] = ()) -> tuple[str, ...]:
    aliases: list[str] = []
    for token in (prefix, *(extra_prefixes or ())):
        normalized = str(token or "").strip().upper()
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    if not aliases:
        aliases.append("S")
    return tuple(aliases)


def _normalize_prompt_chunk(chunk: str) -> str:
    lines = [line.rstrip() for line in str(chunk or "").splitlines()]
    return "\n".join(lines).strip()


def parse_prompt_blocks(
    raw_text: str,
    *,
    prefix: str = "S",
    pad_width: int = 3,
    separator: str = "|||",
    extra_prefixes: Iterable[str] = (),
) -> list[PromptBlock]:
    prefix_aliases = _normalize_prefix_aliases(prefix, extra_prefixes)
    prefix_pattern = "|".join(re.escape(token) for token in prefix_aliases)
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
            rf"^\s*(((?:{prefix_pattern})\s*0*([1-9][0-9]*))(?:\s*>\s*(?:{prefix_pattern})\s*0*([1-9][0-9]*))?)\s*(?:PROMPT|프롬프트)\s*:\s*(.*)\s*$",
            first_line,
            re.IGNORECASE | re.DOTALL,
        )
        if labeled_match:
            number = int(labeled_match.group(3))
            prompt_spec = str(labeled_match.group(1) or "").strip()
            tag_head = prompt_spec.split(">", 1)[0].strip()
            prefix_match = re.match(r"^\s*([A-Za-z]+)", tag_head)
            display_prefix = str(prefix_match.group(1) or prefix).strip().upper() if prefix_match else str(prefix or "S").strip().upper()
            tag = f"{display_prefix}{str(number).zfill(max(3, int(pad_width or 3)))}"
            inline_body = str(labeled_match.group(5) or "").strip()
            body_parts = []
            if inline_body:
                body_parts.append(inline_body)
            if rest_lines:
                body_parts.append("\n".join(rest_lines).strip())
            body = _normalize_body("\n".join(part for part in body_parts if part.strip()))
            rendered = f"{prompt_spec.upper()} Prompt : {body}"
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
    extra_prefixes: Iterable[str] = (),
) -> list[PromptBlock]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    return parse_prompt_blocks(raw, prefix=prefix, pad_width=pad_width, separator=separator, extra_prefixes=extra_prefixes)


def summarize_prompt_file(
    path: Path,
    *,
    prefix: str = "S",
    pad_width: int = 3,
    separator: str = "|||",
    extra_prefixes: Iterable[str] = (),
) -> str:
    items = load_prompt_blocks(path, prefix=prefix, pad_width=pad_width, separator=separator, extra_prefixes=extra_prefixes)
    if not items:
        return f"{path.name} | 프롬프트 없음"
    number_text = ",".join(f"{item.number:03d}" for item in items)
    return f"{path.name} | 총 {len(items)}개 | {number_text}"


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
