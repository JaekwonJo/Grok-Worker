from __future__ import annotations

import time
from typing import Callable


LogFn = Callable[[str], None]

DEFAULT_EDGE_INNER_WIDTH = 968
DEFAULT_EDGE_INNER_HEIGHT = 940
DEFAULT_EDGE_LEFT = 0
DEFAULT_EDGE_TOP = 0


def _window_setting(cfg: dict, key: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(cfg.get(key, default) or default)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def edge_window_settings(cfg: dict) -> dict[str, int]:
    return {
        "inner_width": _window_setting(cfg, "edge_window_inner_width", DEFAULT_EDGE_INNER_WIDTH, 760, 2200),
        "inner_height": _window_setting(cfg, "edge_window_inner_height", DEFAULT_EDGE_INNER_HEIGHT, 700, 1800),
        "left": _window_setting(cfg, "edge_window_left", DEFAULT_EDGE_LEFT, -3000, 6000),
        "top": _window_setting(cfg, "edge_window_top", DEFAULT_EDGE_TOP, -2000, 4000),
        "lock_position": bool(cfg.get("edge_window_lock_position", False)),
    }


def _read_window_metrics(page) -> dict[str, int]:
    metrics = page.evaluate(
        """
        () => ({
            innerWidth: Math.max(
                window.innerWidth || 0,
                document.documentElement?.clientWidth || 0,
                document.body?.clientWidth || 0
            ),
            innerHeight: Math.max(
                window.innerHeight || 0,
                document.documentElement?.clientHeight || 0,
                document.body?.clientHeight || 0
            ),
            outerWidth: Math.max(window.outerWidth || 0, 0),
            outerHeight: Math.max(window.outerHeight || 0, 0),
            screenX: Math.round(window.screenX || 0),
            screenY: Math.round(window.screenY || 0),
            availWidth: Math.max((window.screen && window.screen.availWidth) || 0, 0),
            availHeight: Math.max((window.screen && window.screen.availHeight) || 0, 0),
        })
        """
    ) or {}
    return {
        "innerWidth": int(metrics.get("innerWidth") or 0),
        "innerHeight": int(metrics.get("innerHeight") or 0),
        "outerWidth": int(metrics.get("outerWidth") or 0),
        "outerHeight": int(metrics.get("outerHeight") or 0),
        "screenX": int(metrics.get("screenX") or 0),
        "screenY": int(metrics.get("screenY") or 0),
        "availWidth": int(metrics.get("availWidth") or 0),
        "availHeight": int(metrics.get("availHeight") or 0),
    }


def apply_edge_window_bounds(
    page,
    cfg: dict,
    *,
    log: LogFn | None = None,
    reason: str = "",
) -> bool:
    settings = edge_window_settings(cfg)
    note = f" ({reason})" if reason else ""
    try:
        metrics = _read_window_metrics(page)
        cfg["edge_window_left"] = int(metrics["screenX"])
        cfg["edge_window_top"] = int(metrics["screenY"])
        border_w = max(0, metrics["outerWidth"] - metrics["innerWidth"])
        border_h = max(0, metrics["outerHeight"] - metrics["innerHeight"])
        target_outer_w = settings["inner_width"] + border_w
        target_outer_h = settings["inner_height"] + border_h
        avail_w = metrics["availWidth"]
        avail_h = metrics["availHeight"]
        if avail_w > 0:
            target_outer_w = min(target_outer_w, avail_w)
        if avail_h > 0:
            target_outer_h = min(target_outer_h, avail_h)
        target_left = metrics["screenX"]
        target_top = metrics["screenY"]
        if settings["lock_position"]:
            target_left = settings["left"]
            target_top = settings["top"]
        if avail_w > 0:
            target_left = max(0, min(target_left, max(0, avail_w - target_outer_w)))
        if avail_h > 0:
            target_top = max(0, min(target_top, max(0, avail_h - target_outer_h)))

        session = page.context.new_cdp_session(page)
        info = session.send("Browser.getWindowForTarget")
        window_id = int(info.get("windowId") or 0)
        if window_id <= 0:
            raise RuntimeError("windowId를 찾지 못했습니다.")

        bounds = {
            "windowState": "normal",
            "width": int(target_outer_w),
            "height": int(target_outer_h),
        }
        if settings["lock_position"]:
            bounds["left"] = int(target_left)
            bounds["top"] = int(target_top)
        session.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": bounds})
        time.sleep(0.20)

        corrected = _read_window_metrics(page)
        cfg["edge_window_left"] = int(corrected["screenX"])
        cfg["edge_window_top"] = int(corrected["screenY"])
        dw = settings["inner_width"] - corrected["innerWidth"]
        dh = settings["inner_height"] - corrected["innerHeight"]
        if abs(dw) > 4 or abs(dh) > 4:
            final_bounds = {
                "windowState": "normal",
                "width": int(max(760, target_outer_w + dw)),
                "height": int(max(700, target_outer_h + dh)),
            }
            if settings["lock_position"]:
                final_bounds["left"] = int(target_left)
                final_bounds["top"] = int(target_top)
            if avail_w > 0:
                final_bounds["width"] = min(final_bounds["width"], avail_w)
            if avail_h > 0:
                final_bounds["height"] = min(final_bounds["height"], avail_h)
            session.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": final_bounds})
            time.sleep(0.20)
            corrected = _read_window_metrics(page)
            cfg["edge_window_left"] = int(corrected["screenX"])
            cfg["edge_window_top"] = int(corrected["screenY"])

        if log is not None:
            log(
                f"🪟 Edge 창 크기 맞춤{note}: 내부 {corrected['innerWidth']}x{corrected['innerHeight']} "
                f"| 위치 {corrected['screenX']},{corrected['screenY']}"
                f"{' | 위치고정' if settings['lock_position'] else ' | 크기만고정'}"
            )
        return True
    except Exception as exc:
        if log is not None:
            log(f"⚠️ Edge 창 크기 맞춤 실패{note}: {exc}")
        return False
