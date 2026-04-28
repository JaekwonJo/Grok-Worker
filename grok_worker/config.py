from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


CONFIG_FILE = "grok_worker_config.json"
PROMPT_LIBRARY_FILE = "grok_prompt_library.json"
PROMPTS_DIR = "prompts"
RUNTIME_DIR = "runtime"
LOGS_DIR = "logs"
DOWNLOADS_DIR = "downloads"


DEFAULT_CONFIG: dict[str, Any] = {
    "worker_name": "Grok Worker1",
    "project_profiles": [
        {
            "name": "기본 프로젝트",
            "url": "https://grok.com/imagine",
        }
    ],
    "project_index": 0,
    "prompt_slots": [
        {
            "name": "기본 프롬프트 파일",
            "file": f"{PROMPTS_DIR}/grok_prompts_slot_1.txt",
        }
    ],
    "selected_prompt_file": f"{PROMPTS_DIR}/grok_prompts_slot_1.txt",
    "prompt_slot_index": 0,
    "prompt_separator": "|||",
    "prompt_prefix": "S",
    "prompt_pad_width": 3,
    "number_mode": "range",
    "start_number": 1,
    "end_number": 10,
    "manual_numbers": "",
    "reference_image_dir": "",
    "download_output_dir": "",
    "browser_profile_dir": f"{RUNTIME_DIR}/browser_profile_1",
    "browser_launch_mode": "edge_attach",
    "browser_attach_url": "http://127.0.0.1:9222",
    "edge_window_inner_width": 968,
    "edge_window_inner_height": 940,
    "edge_window_left": 0,
    "edge_window_top": 0,
    "edge_window_lock_position": False,
    "media_mode": "image",
    "video_quality": "720p",
    "video_duration": "10s",
    "aspect_ratio": "16:9",
    "typing_speed": 1.0,
    "humanize_typing": True,
    "generate_wait_seconds": 5.0,
    "next_prompt_wait_seconds": 2.0,
    "break_every_count": 0,
    "break_minutes": 0.0,
    "window_geometry": "920x560",
    "lower_pane_sash": 460,
    "settings_collapsed": False,
    "log_panel_visible": False,
    "grok_site_url": "https://grok.com/imagine",
}


def default_attach_profile_dir(attach_url: str) -> str:
    raw = str(attach_url or "http://127.0.0.1:9222").strip()
    try:
        port = int(raw.rsplit(":", 1)[-1])
    except Exception:
        port = 9222
    index = max(1, port - 9221)
    if index == 1:
        return f"{RUNTIME_DIR}/edge_attach_profile"
    return f"{RUNTIME_DIR}/edge_attach_profile_{index}"


def _merge_defaults(defaults: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in (data or {}).items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_app_dirs(base_dir: Path) -> None:
    (base_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (base_dir / RUNTIME_DIR).mkdir(parents=True, exist_ok=True)
    (base_dir / LOGS_DIR).mkdir(parents=True, exist_ok=True)
    (base_dir / DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)


def config_path(base_dir: Path, config_name: str = CONFIG_FILE) -> Path:
    return base_dir / (str(config_name or CONFIG_FILE).strip() or CONFIG_FILE)


def prompt_library_path(base_dir: Path) -> Path:
    return base_dir / PROMPT_LIBRARY_FILE


def _default_prompt_file_path(base_dir: Path) -> Path:
    return base_dir / PROMPTS_DIR / "grok_prompts_slot_1.txt"


def _normalize_prompt_slot_name(name: Any, idx: int) -> str:
    return str(name or f"프롬프트 파일 {idx}").strip() or f"프롬프트 파일 {idx}"


def _normalize_prompt_slot_file(slot: dict[str, Any], idx: int) -> str:
    raw = str((slot or {}).get("file") or f"{PROMPTS_DIR}/grok_prompts_slot_{idx}.txt").strip()
    return raw.replace("\\", "/")


def _is_placeholder_prompt_name(name: str) -> bool:
    normalized = str(name or "").strip()
    return normalized in {"", "기본 프롬프트 파일"} or normalized.startswith("프롬프트 파일")


def _normalize_prompt_slots(base_dir: Path, prompt_slots: list[dict[str, Any]]) -> list[dict[str, str]]:
    slots = list(prompt_slots or [])
    if not slots:
        slots = deepcopy(DEFAULT_CONFIG["prompt_slots"])
    normalized_slots: list[dict[str, str]] = []
    for idx, slot in enumerate(slots, start=1):
        slot_name = _normalize_prompt_slot_name((slot or {}).get("name"), idx)
        slot_file = _normalize_prompt_slot_file(slot or {}, idx)
        normalized_slots.append({"name": slot_name, "file": slot_file})
        path = base_dir / slot_file
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return normalized_slots


def _extract_prompt_slots(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        maybe_slots = raw.get("prompt_slots")
        if isinstance(maybe_slots, list):
            return maybe_slots
    if isinstance(raw, list):
        return raw
    return []


def _merge_prompt_slots(*collections: list[dict[str, Any]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_by_file: dict[str, dict[str, str]] = {}
    for slots in collections:
        for idx, slot in enumerate(slots or [], start=1):
            slot_file = _normalize_prompt_slot_file(slot or {}, idx)
            slot_name = _normalize_prompt_slot_name((slot or {}).get("name"), idx)
            existing = seen_by_file.get(slot_file)
            if existing:
                if _is_placeholder_prompt_name(existing["name"]) and not _is_placeholder_prompt_name(slot_name):
                    existing["name"] = slot_name
                continue
            item = {"name": slot_name, "file": slot_file}
            seen_by_file[slot_file] = item
            merged.append(item)
    return merged or deepcopy(DEFAULT_CONFIG["prompt_slots"])


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def _collect_legacy_prompt_slots(base_dir: Path, config_name: str, current_raw: dict[str, Any]) -> list[dict[str, Any]]:
    slot_collections: list[list[dict[str, Any]]] = []
    current_slots = _extract_prompt_slots(current_raw)
    if current_slots:
        slot_collections.append(current_slots)
    config_paths = sorted(base_dir.glob("grok_worker_config*.json"))
    current_path = config_path(base_dir, config_name)
    if current_path not in config_paths and current_path.exists():
        config_paths.append(current_path)
    for path in config_paths:
        raw = _load_json_file(path)
        slots = _extract_prompt_slots(raw)
        if slots:
            slot_collections.append(slots)
    return _merge_prompt_slots(*slot_collections)


def load_prompt_library(base_dir: Path, *, config_name: str = CONFIG_FILE, current_raw: dict[str, Any] | None = None) -> list[dict[str, str]]:
    ensure_app_dirs(base_dir)
    library_path = prompt_library_path(base_dir)
    if library_path.exists():
        library_slots = _extract_prompt_slots(_load_json_file(library_path))
        if library_slots:
            normalized_slots = _normalize_prompt_slots(base_dir, library_slots)
            save_prompt_library(base_dir, normalized_slots)
            return normalized_slots
    merged_slots = _collect_legacy_prompt_slots(base_dir, config_name, current_raw or {})
    normalized_slots = _normalize_prompt_slots(base_dir, merged_slots)
    save_prompt_library(base_dir, normalized_slots)
    return normalized_slots


def save_prompt_library(base_dir: Path, prompt_slots: list[dict[str, Any]]) -> Path:
    ensure_app_dirs(base_dir)
    normalized_slots = _normalize_prompt_slots(base_dir, prompt_slots)
    path = prompt_library_path(base_dir)
    payload = {"prompt_slots": normalized_slots}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _ensure_prompt_slots(base_dir: Path, cfg: dict[str, Any], *, config_name: str = CONFIG_FILE, current_raw: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_slots = load_prompt_library(base_dir, config_name=config_name, current_raw=current_raw or {})
    raw_selected_file = str((current_raw or {}).get("selected_prompt_file") or "").strip().replace("\\", "/")
    selected_file = raw_selected_file
    if not selected_file and not list((current_raw or {}).get("prompt_slots") or []):
        selected_file = str(cfg.get("selected_prompt_file") or "").strip().replace("\\", "/")
    if not selected_file:
        raw_slots = list((current_raw or {}).get("prompt_slots") or [])
        raw_index = int((current_raw or {}).get("prompt_slot_index", 0) or 0)
        if raw_slots:
            raw_index = max(0, min(raw_index, len(raw_slots) - 1))
            selected_file = _normalize_prompt_slot_file(raw_slots[raw_index], raw_index + 1)
    if not selected_file and normalized_slots:
        prompt_index = int(cfg.get("prompt_slot_index", 0) or 0)
        prompt_index = max(0, min(prompt_index, len(normalized_slots) - 1))
        selected_file = str((normalized_slots[prompt_index] or {}).get("file") or "").strip()
    if normalized_slots and not any(slot["file"] == selected_file for slot in normalized_slots):
        selected_file = str((normalized_slots[0] or {}).get("file") or "").strip()
    cfg["prompt_slots"] = normalized_slots
    cfg["selected_prompt_file"] = selected_file
    selected_index = 0
    for idx, slot in enumerate(normalized_slots):
        if slot["file"] == selected_file:
            selected_index = idx
            break
    cfg["prompt_slot_index"] = selected_index
    return cfg


def load_config(base_dir: Path, config_name: str = CONFIG_FILE) -> dict[str, Any]:
    ensure_app_dirs(base_dir)
    path = config_path(base_dir, config_name)
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        _default_prompt_file_path(base_dir).write_text("", encoding="utf-8")
        cfg["download_output_dir"] = str((base_dir / DOWNLOADS_DIR).resolve())
        save_config(base_dir, cfg, config_name)
        return cfg
    raw = _load_json_file(path)
    cfg = _merge_defaults(DEFAULT_CONFIG, raw)
    cfg = _ensure_prompt_slots(base_dir, cfg, config_name=config_name, current_raw=raw)
    browser_profile_dir = str(cfg.get("browser_profile_dir") or "").strip()
    if (not browser_profile_dir) or browser_profile_dir == DEFAULT_CONFIG["browser_profile_dir"]:
        cfg["browser_profile_dir"] = default_attach_profile_dir(str(cfg.get("browser_attach_url") or ""))
    if not cfg.get("download_output_dir"):
        cfg["download_output_dir"] = str((base_dir / DOWNLOADS_DIR).resolve())
    return cfg


def save_config(base_dir: Path, cfg: dict[str, Any], config_name: str = CONFIG_FILE) -> Path:
    ensure_app_dirs(base_dir)
    cfg = deepcopy(cfg)
    cfg = _ensure_prompt_slots(base_dir, cfg, config_name=config_name, current_raw=cfg)
    save_prompt_library(base_dir, list(cfg.get("prompt_slots") or []))
    path = config_path(base_dir, config_name)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def next_prompt_slot_file(base_dir: Path, existing_slots: list[dict[str, Any]]) -> str:
    used = set()
    for slot in existing_slots or []:
        file_name = str((slot or {}).get("file") or "")
        used.add(file_name)
    idx = 1
    while True:
        rel = f"{PROMPTS_DIR}/grok_prompts_slot_{idx}.txt"
        if rel not in used and not (base_dir / rel).exists():
            return rel
        idx += 1
