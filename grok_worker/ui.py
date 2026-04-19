from __future__ import annotations

import os
import re
import threading
import time
import tkinter as tk
import math
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .automation import GrokAutomationEngine
from .browser import BrowserManager
from .config import CONFIG_FILE, DEFAULT_CONFIG, LOGS_DIR, default_attach_profile_dir, next_prompt_slot_file, save_config, load_config
from .prompt_parser import compress_numbers, load_prompt_blocks, summarize_prompt_file
from .queue_state import QueueItem


class GrokWorkerApp:
    def __init__(
        self,
        base_dir: Path,
        *,
        config_name: str = CONFIG_FILE,
        instance_key: str = "",
        forced_attach_url: str | None = None,
        forced_worker_name: str | None = None,
        forced_geometry: str | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.config_name = str(config_name or CONFIG_FILE).strip() or CONFIG_FILE
        self.instance_key = str(instance_key or "").strip()
        self.forced_attach_url = str(forced_attach_url or "").strip() or None
        self.forced_worker_name = str(forced_worker_name or "").strip() or None
        self.forced_geometry = str(forced_geometry or "").strip() or None
        self.cfg = load_config(self.base_dir, config_name=self.config_name)
        if self.forced_attach_url:
            self.cfg["browser_attach_url"] = self.forced_attach_url
        if self.forced_worker_name:
            self.cfg["worker_name"] = self.forced_worker_name
        self._normalize_browser_profile_dir()
        self.theme = self._build_theme()
        self._suspend_auto_save = True
        self.browser = BrowserManager(self.log)
        self.queue_items: list[QueueItem] = []
        self.log_lines: list[str] = []
        self.run_log_path: Path | None = None
        self.run_log_fp = None
        self.action_trace_path: Path | None = None
        self.action_trace_fp = None
        self.run_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.settings_collapsed = False
        self.log_panel_visible = False
        self._status_countdown_after_id: str | None = None
        self._status_countdown_deadline: float | None = None
        self._status_countdown_prefix: str | None = None
        self._resize_drag_origin: tuple[int, int, int, int] | None = None

        self.root = tk.Tk()
        self.root.title(f"Grok Worker - {self.cfg.get('worker_name', 'Grok Worker1')}")
        saved_geometry = str(self.cfg.get("window_geometry") or "").strip()
        default_geometry = str(DEFAULT_CONFIG.get("window_geometry") or "920x560")
        initial_geometry = saved_geometry or self.forced_geometry or default_geometry
        if self.forced_geometry and (not saved_geometry or saved_geometry == default_geometry):
            initial_geometry = self.forced_geometry
        self.root.geometry(initial_geometry)
        self.root.minsize(820, 520)
        self.root.configure(bg=self.theme["root_bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_vars()
        self._build_ui()
        self._load_vars_from_config()
        self._apply_settings_visibility()
        self._apply_media_visibility()
        self._suspend_auto_save = False
        self.refresh_all()

    def _build_vars(self) -> None:
        self.worker_name_var = tk.StringVar()
        self.prompt_slot_var = tk.StringVar()
        self.download_dir_var = tk.StringVar()
        self.media_mode_var = tk.StringVar()
        self.video_quality_var = tk.StringVar()
        self.video_duration_var = tk.StringVar()
        self.aspect_ratio_var = tk.StringVar()
        self.number_mode_var = tk.StringVar()
        self.start_number_var = tk.StringVar()
        self.end_number_var = tk.StringVar()
        self.manual_numbers_var = tk.StringVar()
        self.typing_speed_var = tk.DoubleVar()
        self.humanize_typing_var = tk.BooleanVar()
        self.generate_wait_var = tk.StringVar()
        self.next_prompt_wait_var = tk.StringVar()
        self.break_every_var = tk.StringVar()
        self.break_minutes_var = tk.StringVar()
        self.status_var = tk.StringVar(value="준비 완료")
        self.progress_var = tk.StringVar(value="0 / 0 (0.0%)")
        self.project_summary_var = tk.StringVar(value="사이트: grok.com/imagine")
        self.queue_summary_var = tk.StringVar(value="활성 0개 | 완료 0 | 실패 0 | 대기 0")
        self.prompt_file_summary_var = tk.StringVar(value="")
        self.attach_url_var = tk.StringVar(value="")

    def _build_theme(self) -> dict[str, str]:
        identity = f"{self.instance_key} {self.forced_worker_name or ''} {self.cfg.get('worker_name') or ''}".lower()
        if "worker2" in identity or identity.endswith("2"):
            return {
                "root_bg": "#1a1311",
                "top_left_bg": "#3a2118",
                "top_left_border": "#d27a49",
                "top_mid_bg": "#4a2617",
                "top_mid_border": "#ea9d5e",
                "top_right_bg": "#3a2118",
                "settings_bg": "#402217",
                "settings_border": "#d27a49",
                "queue_panel_bg": "#3a2118",
                "queue_panel_border": "#d27a49",
                "log_panel_bg": "#241513",
                "log_text_bg": "#160e0d",
                "log_text_fg": "#ffe2d0",
                "muted_fg": "#f1c8b0",
                "sub_fg": "#e7b595",
                "chip_bg": "#5a2d1b",
                "chip_fg": "#ffd1ae",
                "progress_bg": "#26140f",
                "progress_border": "#8c5435",
                "progress_fill": "#ff9855",
                "small_btn_bg": "#5a2d1b",
                "open_btn_bg": "#a95727",
                "start_btn_bg": "#cf6a2d",
                "settings_toggle_bg": "#5a2d1b",
                "status_fg": "#ffb37d",
            }
        if "worker3" in identity or identity.endswith("3"):
            return {
                "root_bg": "#101815",
                "top_left_bg": "#1a2d27",
                "top_left_border": "#49b287",
                "top_mid_bg": "#203831",
                "top_mid_border": "#5ec6a0",
                "top_right_bg": "#1a2d27",
                "settings_bg": "#193129",
                "settings_border": "#49b287",
                "queue_panel_bg": "#183028",
                "queue_panel_border": "#49b287",
                "log_panel_bg": "#121d19",
                "log_text_bg": "#0f1512",
                "log_text_fg": "#daf8eb",
                "muted_fg": "#b7d8cb",
                "sub_fg": "#a5d6c1",
                "chip_bg": "#203a32",
                "chip_fg": "#8ef0c5",
                "progress_bg": "#12211d",
                "progress_border": "#3d6c59",
                "progress_fill": "#58d39f",
                "small_btn_bg": "#203a32",
                "open_btn_bg": "#2e6e5a",
                "start_btn_bg": "#2f8a68",
                "settings_toggle_bg": "#203a32",
                "status_fg": "#8ef0c5",
            }
        return {
            "root_bg": "#14161b",
            "top_left_bg": "#1d2432",
            "top_left_border": "#41608a",
            "top_mid_bg": "#202b3e",
            "top_mid_border": "#4c6b9a",
            "top_right_bg": "#1d2432",
            "settings_bg": "#1a2f4f",
            "settings_border": "#5b84b8",
            "queue_panel_bg": "#17283f",
            "queue_panel_border": "#5b84b8",
            "log_panel_bg": "#14161b",
            "log_text_bg": "#101723",
            "log_text_fg": "#d7e5ff",
            "muted_fg": "#a9bdd8",
            "sub_fg": "#c4d4ec",
            "chip_bg": "#20304a",
            "chip_fg": "#8fd0ff",
            "progress_bg": "#152033",
            "progress_border": "#314966",
            "progress_fill": "#4ca7ff",
            "small_btn_bg": "#233042",
            "open_btn_bg": "#31527d",
            "start_btn_bg": "#2f8a68",
            "settings_toggle_bg": "#233042",
            "status_fg": "#79e3a0",
        }

    def _bg(self, key: str) -> str:
        return self.theme[key]

    def _build_ui(self) -> None:
        root = self.root

        top = tk.Frame(root, bg=self._bg("root_bg"))
        top.pack(fill="x", padx=10, pady=(10, 6))

        top_left = tk.Frame(top, bg=self._bg("top_left_bg"), highlightbackground=self._bg("top_left_border"), highlightthickness=1)
        top_left.pack(side="left", fill="both", expand=True)
        tk.Label(top_left, text="Grok Worker", bg=self._bg("top_left_bg"), fg="#ffffff", font=("Malgun Gothic", 13, "bold")).pack(anchor="w", padx=10, pady=(6, 1))
        tk.Label(top_left, textvariable=self.worker_name_var, bg=self._bg("top_left_bg"), fg=self._bg("muted_fg"), font=("Malgun Gothic", 9)).pack(anchor="w", padx=10, pady=(0, 6))

        top_mid = tk.Frame(top, bg=self._bg("top_mid_bg"), width=250, highlightbackground=self._bg("top_mid_border"), highlightthickness=1)
        top_mid.pack(side="left", padx=8, fill="y")
        tk.Label(top_mid, text="진행 상황", bg=self._bg("top_mid_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10, "bold")).pack(pady=(6, 1))
        tk.Label(top_mid, textvariable=self.project_summary_var, bg=self._bg("top_mid_bg"), fg=self._bg("sub_fg"), font=("Malgun Gothic", 8)).pack()
        tk.Label(top_mid, textvariable=self.progress_var, bg=self._bg("top_mid_bg"), fg=self._bg("chip_fg"), font=("Consolas", 12, "bold")).pack(pady=(2, 3))
        self.progress_canvas = tk.Canvas(top_mid, width=230, height=14, bg=self._bg("progress_bg"), highlightthickness=1, highlightbackground=self._bg("progress_border"))
        self.progress_canvas.pack(padx=10, pady=(0, 6))
        self.progress_fill = self.progress_canvas.create_rectangle(0, 0, 0, 18, fill=self._bg("progress_fill"), outline="")

        top_right = tk.Frame(top, bg=self._bg("top_right_bg"), highlightbackground=self._bg("top_left_border"), highlightthickness=1)
        top_right.pack(side="left", fill="both", expand=True)
        tk.Label(top_right, text="현재 상태", bg=self._bg("top_right_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10, "bold")).pack(anchor="e", padx=10, pady=(6, 1))
        tk.Label(top_right, textvariable=self.status_var, bg=self._bg("top_right_bg"), fg=self._bg("status_fg"), font=("Malgun Gothic", 10, "bold"), wraplength=180, justify="right").pack(anchor="e", padx=10, pady=(0, 6))

        action_row = tk.Frame(root, bg=self._bg("root_bg"))
        action_row.pack(fill="x", padx=10, pady=(0, 6))
        action_left = tk.Frame(action_row, bg=self._bg("root_bg"))
        action_left.pack(side="left")
        action_right = tk.Frame(action_row, bg=self._bg("root_bg"))
        action_right.pack(side="right")

        self._action_button(action_left, "완전정지", self.stop_all, self._bg("small_btn_bg"), small=True).pack(side="left", padx=(0, 6))
        self._action_button(action_left, "일시정지", self.pause_run, self._bg("small_btn_bg"), small=True).pack(side="left", padx=6)
        self._action_button(action_left, "재개", self.resume_run, self._bg("small_btn_bg"), small=True).pack(side="left", padx=6)
        self.settings_toggle_btn = self._action_button(action_left, "⚙ 설정 접기", self.toggle_settings_panel, self._bg("settings_toggle_bg"), small=True)
        self.settings_toggle_btn.pack(side="left", padx=6)
        self._action_button(action_right, "작업봇 창 열기", self.open_browser_window, self._bg("open_btn_bg")).pack(side="left", padx=(0, 6))
        self._action_button(action_right, "▶ 시작", self.start_run, self._bg("start_btn_bg")).pack(side="left")

        body = tk.Frame(root, bg=self._bg("root_bg"))
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        settings = tk.Frame(body, bg=self._bg("settings_bg"), highlightbackground=self._bg("settings_border"), highlightthickness=1)
        self.settings_frame = settings

        settings.pack(fill="x")
        settings.grid_columnconfigure(0, weight=6)
        settings.grid_columnconfigure(1, weight=4)

        left = tk.Frame(settings, bg=self._bg("settings_bg"))
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=8)
        right = tk.Frame(settings, bg=self._bg("settings_bg"))
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=8)

        self._build_basic_settings(left)
        self._build_number_settings(right)

        lower = tk.Frame(body, bg=self._bg("root_bg"))
        self.lower_frame = lower
        lower.pack(fill="both", expand=True, pady=(8, 0))
        lower_content = tk.Frame(lower, bg=self._bg("root_bg"))
        self.lower_content = lower_content
        lower_content.pack(fill="both", expand=True)

        queue_wrap = tk.Frame(lower_content, bg=self._bg("queue_panel_bg"), highlightbackground=self._bg("queue_panel_border"), highlightthickness=1)
        self.queue_wrap = queue_wrap
        queue_wrap.pack(side="left", fill="both", expand=True)

        queue_header = tk.Frame(queue_wrap, bg=self._bg("queue_panel_bg"))
        queue_header.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(queue_header, text="대기열", bg=self._bg("queue_panel_bg"), fg="#ffffff", font=("Malgun Gothic", 10, "bold")).pack(side="left")
        self.log_toggle_btn = self._action_button(queue_header, "로그 보기", self.toggle_log_panel, self._bg("open_btn_bg"), small=True)
        self.log_toggle_btn.pack(side="right", padx=(8, 0))
        self._action_button(queue_header, "실패 번호 복붙", self.copy_failed_numbers, self._bg("open_btn_bg"), small=True).pack(side="right", padx=(8, 0))
        self._action_button(queue_header, "지우기", self.clear_queue, self._bg("open_btn_bg"), small=True).pack(side="right")
        tk.Label(queue_header, textvariable=self.queue_summary_var, bg=self._bg("queue_panel_bg"), fg=self._bg("sub_fg"), font=("Malgun Gothic", 8)).pack(side="right", padx=(10, 12))

        queue_body = tk.Frame(queue_wrap, bg=self._bg("queue_panel_bg"))
        queue_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.queue_canvas = tk.Canvas(queue_body, bg=self._bg("queue_panel_bg"), highlightthickness=0)
        self.queue_scroll = tk.Scrollbar(queue_body, orient="vertical", command=self.queue_canvas.yview)
        self.queue_canvas.configure(yscrollcommand=self.queue_scroll.set)
        self.queue_scroll.pack(side="right", fill="y")
        self.queue_canvas.pack(side="left", fill="both", expand=True)
        self.queue_inner = tk.Frame(self.queue_canvas, bg=self._bg("queue_panel_bg"))
        self.queue_window = self.queue_canvas.create_window((0, 0), window=self.queue_inner, anchor="nw")
        self.queue_inner.bind("<Configure>", lambda _e: self._update_queue_scroll())
        self.queue_canvas.bind("<Configure>", self._on_queue_canvas_resize)
        self.queue_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        log_frame = tk.Frame(lower_content, bg=self._bg("log_panel_bg"), highlightbackground=self._bg("queue_panel_border"), highlightthickness=1, width=250)
        self.log_frame = log_frame
        log_frame.pack_propagate(False)
        tk.Label(log_frame, text="로그", bg=self._bg("log_panel_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10, "bold")).pack(anchor="w", padx=8, pady=(8, 4))
        self.log_text = tk.Text(log_frame, height=6, bg=self._bg("log_text_bg"), fg=self._bg("log_text_fg"), insertbackground="#ffffff", relief="solid", borderwidth=1)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log_text.configure(state="disabled")

        resize_bar = tk.Frame(root, bg=self._bg("root_bg"))
        resize_bar.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(resize_bar, text="창 크기 조절", bg=self._bg("root_bg"), fg=self._bg("sub_fg"), font=("Malgun Gothic", 8)).pack(side="right", padx=(0, 6))
        resize_handle = tk.Frame(
            resize_bar,
            bg=self._bg("small_btn_bg"),
            width=36,
            height=22,
            cursor="size_nw_se",
            highlightbackground=self._bg("top_left_border"),
            highlightthickness=1,
        )
        resize_handle.pack(side="right")
        resize_handle.pack_propagate(False)
        tk.Label(resize_handle, text="◢", bg=self._bg("small_btn_bg"), fg="#ffffff", font=("Malgun Gothic", 10, "bold")).pack(expand=True)
        resize_handle.bind("<ButtonPress-1>", self._start_resize_drag)
        resize_handle.bind("<B1-Motion>", self._on_resize_drag)
        resize_handle.bind("<ButtonRelease-1>", self._end_resize_drag)
        self.root.after(120, self._apply_log_panel_visibility)

    def _start_resize_drag(self, event) -> None:
        self._resize_drag_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _on_resize_drag(self, event) -> None:
        if not self._resize_drag_origin:
            return
        start_x, start_y, start_w, start_h = self._resize_drag_origin
        min_w, min_h = 820, 520
        new_w = max(min_w, start_w + (event.x_root - start_x))
        new_h = max(min_h, start_h + (event.y_root - start_y))
        self.root.geometry(f"{new_w}x{new_h}")

    def _end_resize_drag(self, _event=None) -> None:
        self._resize_drag_origin = None

    def _build_basic_settings(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="기본 설정", bg=self._bg("settings_bg"), fg="#ffffff", font=("Malgun Gothic", 11, "bold")).pack(anchor="w", padx=4, pady=(0, 6))

        self._labeled_combo(parent, "프롬프트 파일", self.prompt_slot_var, self.prompt_slot_changed)
        prompt_btns = tk.Frame(parent, bg=self._bg("settings_bg"))
        prompt_btns.pack(fill="x", padx=4, pady=(0, 4))
        for col in range(4):
            prompt_btns.grid_columnconfigure(col, weight=1)
        self._action_button(prompt_btns, "파일 열기", self.open_prompt_file, self._bg("open_btn_bg"), small=True, width=8).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._action_button(prompt_btns, "이름수정", self.rename_prompt_file, self._bg("open_btn_bg"), small=True, width=8).grid(row=0, column=1, sticky="ew", padx=6)
        self._action_button(prompt_btns, "삭제", self.delete_prompt_file, self._bg("open_btn_bg"), small=True, width=8).grid(row=0, column=2, sticky="ew", padx=6)
        self._action_button(prompt_btns, "추가", self.add_prompt_file, self._bg("open_btn_bg"), small=True, width=6).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        prompt_summary_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        prompt_summary_row.pack(fill="x", padx=4, pady=(0, 8))
        tk.Label(
            prompt_summary_row,
            textvariable=self.prompt_file_summary_var,
            bg=self._bg("settings_bg"),
            fg=self._bg("sub_fg"),
            font=("Malgun Gothic", 9),
            justify="left",
            anchor="nw",
            height=3,
        ).pack(side="left", fill="x", expand=True, anchor="w")
        self._action_button(prompt_summary_row, "번호복사", self.copy_prompt_numbers, self._bg("open_btn_bg"), small=True, width=8).pack(side="right", padx=(8, 0), anchor="n")

        self._path_row(parent, "저장 폴더", self.download_dir_var, self.choose_download_dir)
        attach_note = tk.Frame(parent, bg=self._bg("settings_bg"))
        attach_note.pack(fill="x", padx=4, pady=(0, 8))
        tk.Label(attach_note, text="브라우저 연결", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        tk.Label(
            attach_note,
            textvariable=self.attach_url_var,
            bg=self._bg("chip_bg"),
            fg=self._bg("chip_fg"),
            font=("Consolas", 10, "bold"),
            padx=10,
            pady=5,
        ).pack(anchor="w", pady=(6, 0))
        self.browser_profile_state_label = tk.Label(
            attach_note,
            text="현재 프로필: -",
            bg=self._bg("settings_bg"),
            fg=self._bg("sub_fg"),
            font=("Malgun Gothic", 9),
        )
        self.browser_profile_state_label.pack(anchor="w", pady=(8, 4))
        profile_btn_row = tk.Frame(attach_note, bg=self._bg("settings_bg"))
        profile_btn_row.pack(fill="x")
        self._action_button(profile_btn_row, "새 브라우저 프로필 만들기", self.create_browser_profile, self._bg("open_btn_bg"), small=True).pack(side="left")

    def _build_number_settings(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="번호 설정", bg=self._bg("settings_bg"), fg="#ffffff", font=("Malgun Gothic", 11, "bold")).pack(anchor="w", padx=4, pady=(0, 6))

        media_mode_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        media_mode_row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(media_mode_row, text="작업 모드", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        for text, value in (("이미지", "image"), ("비디오", "video")):
            tk.Radiobutton(
                media_mode_row,
                text=text,
                value=value,
                variable=self.media_mode_var,
                command=self.on_media_mode_changed,
                bg=self._bg("settings_bg"),
                fg="#ffffff",
                selectcolor=self._bg("chip_bg"),
                activebackground=self._bg("settings_bg"),
                activeforeground="#ffffff",
                font=("Malgun Gothic", 10),
            ).pack(side="left", padx=(12, 12))

        self.video_settings_frame = tk.Frame(parent, bg=self._bg("settings_bg"))
        video_row_1 = tk.Frame(self.video_settings_frame, bg=self._bg("settings_bg"))
        video_row_1.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(video_row_1, text="비디오 품질", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        for text, value in (("480p", "480p"), ("720p", "720p")):
            tk.Radiobutton(
                video_row_1,
                text=text,
                value=value,
                variable=self.video_quality_var,
                command=lambda: self.auto_save("비디오 품질 변경"),
                bg=self._bg("settings_bg"),
                fg="#ffffff",
                selectcolor=self._bg("chip_bg"),
                activebackground=self._bg("settings_bg"),
                activeforeground="#ffffff",
                font=("Malgun Gothic", 10),
            ).pack(side="left", padx=(12, 10))

        video_row_2 = tk.Frame(self.video_settings_frame, bg=self._bg("settings_bg"))
        video_row_2.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(video_row_2, text="길이", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        for text, value in (("6초", "6s"), ("10초", "10s")):
            tk.Radiobutton(
                video_row_2,
                text=text,
                value=value,
                variable=self.video_duration_var,
                command=lambda: self.auto_save("비디오 길이 변경"),
                bg=self._bg("settings_bg"),
                fg="#ffffff",
                selectcolor=self._bg("chip_bg"),
                activebackground=self._bg("settings_bg"),
                activeforeground="#ffffff",
                font=("Malgun Gothic", 10),
            ).pack(side="left", padx=(12, 10))

        aspect_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        aspect_row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(aspect_row, text="비율", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        tk.Radiobutton(
            aspect_row,
            text="16:9",
            value="16:9",
            variable=self.aspect_ratio_var,
            command=lambda: self.auto_save("비율 변경"),
            bg=self._bg("settings_bg"),
            fg="#ffffff",
            selectcolor=self._bg("chip_bg"),
            activebackground=self._bg("settings_bg"),
            activeforeground="#ffffff",
            font=("Malgun Gothic", 10),
        ).pack(side="left", padx=(12, 10))

        mode_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        mode_row.pack(fill="x", padx=4, pady=(0, 6))
        for text, value in (("연속", "range"), ("개별", "manual")):
            tk.Radiobutton(
                mode_row,
                text=text,
                value=value,
                variable=self.number_mode_var,
                command=self.on_number_mode_changed,
                bg=self._bg("settings_bg"),
                fg="#ffffff",
                selectcolor=self._bg("chip_bg"),
                activebackground=self._bg("settings_bg"),
                activeforeground="#ffffff",
                font=("Malgun Gothic", 10),
            ).pack(side="left", padx=(0, 18))

        range_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        range_row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(range_row, text="연속 범위", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.start_entry = tk.Entry(range_row, textvariable=self.start_number_var, width=8, font=("Consolas", 12))
        self.start_entry.pack(side="left", padx=(12, 6))
        self._bind_entry_autosave(self.start_entry, "번호 범위 변경")
        tk.Label(range_row, text="~", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.end_entry = tk.Entry(range_row, textvariable=self.end_number_var, width=8, font=("Consolas", 12))
        self.end_entry.pack(side="left", padx=(6, 0))
        self._bind_entry_autosave(self.end_entry, "번호 범위 변경")

        manual_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        manual_row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(manual_row, text="개별 번호", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        self.manual_entry = tk.Entry(manual_row, textvariable=self.manual_numbers_var, font=("Consolas", 12))
        self.manual_entry.pack(fill="x", pady=(6, 0))
        self._bind_entry_autosave(self.manual_entry, "개별 번호 변경")

        speed_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        speed_row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(speed_row, text="타이핑 속도", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        self.speed_scale = tk.Scale(
            speed_row,
            from_=0.5,
            to=2.0,
            resolution=0.1,
            orient="horizontal",
            variable=self.typing_speed_var,
            bg=self._bg("settings_bg"),
            fg="#ffffff",
            troughcolor=self._bg("chip_bg"),
            highlightthickness=0,
            command=lambda _v: self.auto_save("타이핑 속도 변경"),
        )
        self.speed_scale.pack(fill="x")

        humanize_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        humanize_row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(humanize_row, text="인간처럼 입력", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        tk.Label(humanize_row, text="항상 ON", bg=self._bg("chip_bg"), fg=self._bg("status_fg"), font=("Malgun Gothic", 10, "bold"), padx=10, pady=3).pack(side="left", padx=(10, 0))

        wait_row_1 = tk.Frame(parent, bg=self._bg("settings_bg"))
        wait_row_1.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(wait_row_1, text="생성 후 다운로드 대기(초)", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.generate_wait_entry = tk.Entry(wait_row_1, textvariable=self.generate_wait_var, width=8, font=("Consolas", 11))
        self.generate_wait_entry.pack(side="left", padx=(12, 0))
        self._bind_entry_autosave(self.generate_wait_entry, "생성 대기시간 변경")

        wait_row_2 = tk.Frame(parent, bg=self._bg("settings_bg"))
        wait_row_2.pack(fill="x", padx=4, pady=(0, 4))
        tk.Label(wait_row_2, text="다운로드 후 다음 작업 대기(초)", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.next_prompt_wait_entry = tk.Entry(wait_row_2, textvariable=self.next_prompt_wait_var, width=8, font=("Consolas", 11))
        self.next_prompt_wait_entry.pack(side="left", padx=(12, 0))
        self._bind_entry_autosave(self.next_prompt_wait_entry, "다음 작업 대기시간 변경")

        break_row = tk.Frame(parent, bg=self._bg("settings_bg"))
        break_row.pack(fill="x", padx=4, pady=(6, 0))
        tk.Label(break_row, text="몇 개마다 휴식", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.break_every_entry = tk.Entry(break_row, textvariable=self.break_every_var, width=6, font=("Consolas", 11))
        self.break_every_entry.pack(side="left", padx=(10, 12))
        self._bind_entry_autosave(self.break_every_entry, "휴식 간격 변경")
        tk.Label(break_row, text="휴식 시간(분)", bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.break_minutes_entry = tk.Entry(break_row, textvariable=self.break_minutes_var, width=6, font=("Consolas", 11))
        self.break_minutes_entry.pack(side="left", padx=(10, 0))
        self._bind_entry_autosave(self.break_minutes_entry, "휴식 시간 변경")

    def _labeled_combo(self, parent: tk.Frame, label: str, variable: tk.StringVar, callback) -> None:
        row = tk.Frame(parent, bg=self._bg("settings_bg"))
        row.pack(fill="x", padx=4, pady=(0, 6))
        tk.Label(row, text=label, bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        combo = tk.OptionMenu(row, variable, "")
        combo.configure(font=("Malgun Gothic", 10), bg="#f0ede4", width=38, highlightthickness=0)
        combo.pack(fill="x", pady=(6, 0))
        variable.trace_add("write", lambda *_: callback())
        self.prompt_menu = combo

    def _path_row(self, parent: tk.Frame, label: str, variable: tk.StringVar, command) -> None:
        row = tk.Frame(parent, bg=self._bg("settings_bg"))
        row.pack(fill="x", padx=4, pady=(0, 8))
        tk.Label(row, text=label, bg=self._bg("settings_bg"), fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        input_row = tk.Frame(row, bg=self._bg("settings_bg"))
        input_row.pack(fill="x", pady=(6, 0))
        entry = tk.Entry(input_row, textvariable=variable, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True)
        self._bind_entry_autosave(entry, f"{label} 변경")
        self._action_button(input_row, "선택", command, self._bg("open_btn_bg"), small=True).pack(side="left", padx=(8, 0))

    def _bind_entry_autosave(self, widget, reason: str) -> None:
        widget.bind("<FocusOut>", lambda _e, r=reason: self.auto_save(r))
        widget.bind("<Return>", lambda _e, r=reason: self.auto_save(r))

    def _action_button(self, parent, text, command, bg, small=False, width=None):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="#ffffff",
            activebackground=bg,
            activeforeground="#ffffff",
            relief="flat",
            padx=14 if not small else 10,
            pady=8 if not small else 5,
            font=("Malgun Gothic", 10, "bold" if not small else "normal"),
            width=width,
            cursor="hand2",
        )

    def _load_vars_from_config(self) -> None:
        self.worker_name_var.set(str(self.forced_worker_name or self.cfg.get("worker_name") or "Grok Worker1"))
        slots = self.cfg.get("prompt_slots") or []
        slot_index = max(0, min(int(self.cfg.get("prompt_slot_index", 0) or 0), len(slots) - 1))
        self.prompt_slot_var.set(str((slots[slot_index] or {}).get("name") or ""))
        self.download_dir_var.set(str(self.cfg.get("download_output_dir") or ""))
        self.media_mode_var.set(str(self.cfg.get("media_mode") or "image"))
        self.video_quality_var.set(str(self.cfg.get("video_quality") or "720p"))
        self.video_duration_var.set(str(self.cfg.get("video_duration") or "10s"))
        self.aspect_ratio_var.set(str(self.cfg.get("aspect_ratio") or "16:9"))
        self.number_mode_var.set(str(self.cfg.get("number_mode") or "range"))
        self.start_number_var.set(str(self.cfg.get("start_number", 1) or 1))
        self.end_number_var.set(str(self.cfg.get("end_number", 10) or 10))
        self.manual_numbers_var.set(str(self.cfg.get("manual_numbers") or ""))
        self.typing_speed_var.set(float(self.cfg.get("typing_speed", 1.0) or 1.0))
        self.humanize_typing_var.set(True)
        self.generate_wait_var.set(str(self.cfg.get("generate_wait_seconds", 5.0) or 5.0))
        self.next_prompt_wait_var.set(str(self.cfg.get("next_prompt_wait_seconds", 2.0) or 2.0))
        self.break_every_var.set(str(self.cfg.get("break_every_count", 0) or 0))
        self.break_minutes_var.set(str(self.cfg.get("break_minutes", 0.0) or 0.0))
        self.settings_collapsed = bool(self.cfg.get("settings_collapsed", False))
        self.log_panel_visible = bool(self.cfg.get("log_panel_visible", False))

    def _write_vars_to_config(self) -> None:
        slots = self.cfg.get("prompt_slots") or []
        self.cfg["worker_name"] = self.worker_name_var.get().strip() or "Grok Worker1"
        selected_dir = self.download_dir_var.get().strip()
        self.cfg["download_output_dir"] = selected_dir
        self.cfg["reference_image_dir"] = selected_dir
        self.cfg["browser_launch_mode"] = "edge_attach"
        self.cfg["browser_attach_url"] = self.forced_attach_url or str(self.cfg.get("browser_attach_url") or "http://127.0.0.1:9222")
        self.cfg["media_mode"] = self.media_mode_var.get().strip() or "image"
        self.cfg["video_quality"] = self.video_quality_var.get().strip() or "720p"
        self.cfg["video_duration"] = self.video_duration_var.get().strip() or "10s"
        self.cfg["aspect_ratio"] = self.aspect_ratio_var.get().strip() or "16:9"
        self.cfg["number_mode"] = self.number_mode_var.get().strip() or "range"
        self.cfg["start_number"] = self._int_or_default(self.start_number_var.get(), 1)
        self.cfg["end_number"] = self._int_or_default(self.end_number_var.get(), self.cfg["start_number"])
        self.cfg["manual_numbers"] = self.manual_numbers_var.get().strip()
        self.cfg["typing_speed"] = round(float(self.typing_speed_var.get() or 1.0), 1)
        self.cfg["humanize_typing"] = True
        self.cfg["generate_wait_seconds"] = self._float_or_default(self.generate_wait_var.get(), 5.0)
        self.cfg["next_prompt_wait_seconds"] = self._float_or_default(self.next_prompt_wait_var.get(), 2.0)
        self.cfg["break_every_count"] = self._nonnegative_int_or_default(self.break_every_var.get(), 0)
        self.cfg["break_minutes"] = self._float_or_default(self.break_minutes_var.get(), 0.0)
        self.cfg["window_geometry"] = self.root.geometry()
        self.cfg["lower_pane_sash"] = self._current_lower_pane_sash()
        self.cfg["settings_collapsed"] = bool(self.settings_collapsed)
        self.cfg["log_panel_visible"] = bool(self.log_panel_visible)

        slot_name = self.prompt_slot_var.get().strip()
        for idx, slot in enumerate(slots):
            if str(slot.get("name") or "").strip() == slot_name:
                self.cfg["prompt_slot_index"] = idx
                break

    def auto_save(self, reason: str = "") -> None:
        if self._suspend_auto_save:
            return
        self._write_vars_to_config()
        save_config(self.base_dir, self.cfg, self.config_name)
        if reason:
            self.log(f"자동 저장: {reason}")
        self.refresh_summary_only()

    def manual_save(self) -> None:
        self._write_vars_to_config()
        path = save_config(self.base_dir, self.cfg, self.config_name)
        self.log(f"설정 저장: {path.name}")
        self.refresh_summary_only()

    def refresh_all(self) -> None:
        self._refresh_prompt_menu()
        self.on_number_mode_changed()
        self._apply_settings_visibility()
        self._apply_media_visibility()
        self._apply_log_panel_visibility()
        self.refresh_summary_only()
        self._render_queue()

    def toggle_settings_panel(self) -> None:
        self.settings_collapsed = not self.settings_collapsed
        self._apply_settings_visibility()
        self.auto_save("설정 접기/펼치기 변경")

    def toggle_log_panel(self) -> None:
        self.log_panel_visible = not self.log_panel_visible
        self._apply_log_panel_visibility()
        self.auto_save("로그 패널 표시 변경")

    def on_media_mode_changed(self) -> None:
        self._apply_media_visibility()
        if not self._suspend_auto_save:
            self.auto_save("작업 모드 변경")

    def _apply_settings_visibility(self) -> None:
        if self.settings_collapsed:
            try:
                self.settings_frame.pack_forget()
            except Exception:
                pass
            self.settings_toggle_btn.configure(text="⚙ 설정 펼치기")
        else:
            if not self.settings_frame.winfo_manager():
                self.settings_frame.pack(fill="x", before=self.lower_frame)
            self.settings_toggle_btn.configure(text="⚙ 설정 접기")

    def _apply_log_panel_visibility(self) -> None:
        if self.log_panel_visible:
            if not self.log_frame.winfo_manager():
                self.log_frame.pack(side="right", fill="both", padx=(8, 0))
            self.log_toggle_btn.configure(text="로그 숨기기")
        else:
            if self.log_frame.winfo_manager():
                self.log_frame.pack_forget()
            self.log_toggle_btn.configure(text="로그 보기")
            self.root.after(50, self._render_queue)

    def _apply_media_visibility(self) -> None:
        if self.media_mode_var.get().strip() == "video":
            if not self.video_settings_frame.winfo_manager():
                self.video_settings_frame.pack(fill="x", padx=0, pady=(0, 2))
        else:
            try:
                self.video_settings_frame.pack_forget()
            except Exception:
                pass

    def _format_prompt_summary_for_ui(self, summary: str, *, max_lines: int = 3, max_chars: int = 92) -> str:
        raw = str(summary or "").strip()
        if not raw:
            return ""
        parts = [part.strip() for part in raw.split("|")]
        if len(parts) < 3:
            if len(raw) <= max_chars * max_lines:
                return raw
            return raw[: max_chars * max_lines - 3].rstrip(", ") + "..."
        head = " | ".join(parts[:2]).strip()
        numbers = [token.strip() for token in parts[2].split(",") if token.strip()]
        lines: list[str] = []
        current = f"{head} | "
        current_limit = max_chars
        for token in numbers:
            piece = token if current.endswith("| ") else f",{token}"
            if len(current) + len(piece) <= current_limit:
                current += piece
                continue
            lines.append(current.rstrip(", "))
            if len(lines) >= max_lines:
                lines[-1] = lines[-1].rstrip(", ") + "..."
                return "\n".join(lines)
            current = token
        lines.append(current.rstrip(", "))
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(", ") + "..."
        return "\n".join(lines)

    def refresh_summary_only(self) -> None:
        attach_url = str(self.cfg.get("browser_attach_url") or "http://127.0.0.1:9222").strip()
        media_label = "비디오" if str(self.cfg.get("media_mode") or "image") == "video" else "이미지"
        self.project_summary_var.set(f"사이트: grok.com/imagine | 기존 Edge 연결 | {media_label}")
        self.attach_url_var.set(f"기존 Edge 연결 고정 | {attach_url}")
        self._refresh_browser_profile_ui()
        slots = self.cfg.get("prompt_slots") or []
        slot_idx = int(self.cfg.get("prompt_slot_index", 0) or 0)
        if slots:
            slot_file = str((slots[slot_idx] or {}).get("file") or "")
            slot_path = self.base_dir / slot_file
            summary = summarize_prompt_file(
                slot_path,
                prefix=str(self.cfg.get("prompt_prefix") or "S"),
                pad_width=int(self.cfg.get("prompt_pad_width", 3) or 3),
                separator=str(self.cfg.get("prompt_separator") or "|||"),
                extra_prefixes=("V",) if str(self.cfg.get("media_mode") or "image") == "video" else (),
            )
            self.prompt_file_summary_var.set(self._format_prompt_summary_for_ui(summary))
        self._refresh_queue_summary()
        self._refresh_progress_display()
        self.root.title(f"Grok Worker - {self.cfg.get('worker_name', 'Grok Worker1')}")

    def _refresh_prompt_menu(self) -> None:
        menu = self.prompt_menu["menu"]
        menu.delete(0, "end")
        values = [str(slot.get("name") or "") for slot in self.cfg.get("prompt_slots") or []]
        for value in values:
            menu.add_command(label=value, command=lambda v=value: self.prompt_slot_var.set(v))
        if values and self.prompt_slot_var.get() not in values:
            self.prompt_slot_var.set(values[0])

    def on_number_mode_changed(self) -> None:
        mode = self.number_mode_var.get().strip()
        state_range = "normal" if mode == "range" else "disabled"
        state_manual = "normal" if mode == "manual" else "disabled"
        self.start_entry.configure(state=state_range)
        self.end_entry.configure(state=state_range)
        self.manual_entry.configure(state=state_manual)
        if not self._suspend_auto_save:
            self.auto_save("번호 방식 변경")

    def prompt_slot_changed(self) -> None:
        if (not self._suspend_auto_save) and self.prompt_slot_var.get().strip():
            self.auto_save("프롬프트 파일 선택 변경")

    def add_prompt_file(self) -> None:
        name = simpledialog.askstring("프롬프트 파일 추가", "프롬프트 파일 이름을 입력하세요:", parent=self.root)
        if not name:
            return
        file_rel = next_prompt_slot_file(self.base_dir, self.cfg.get("prompt_slots") or [])
        path = self.base_dir / file_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        slot = {"name": name.strip(), "file": file_rel}
        self.cfg.setdefault("prompt_slots", []).append(slot)
        self.prompt_slot_var.set(name.strip())
        self.auto_save("프롬프트 파일 추가")
        self.refresh_all()

    def rename_prompt_file(self) -> None:
        current = self.prompt_slot_var.get().strip()
        if not current:
            return
        new_name = simpledialog.askstring("프롬프트 파일 이름 수정", "새 이름을 입력하세요:", parent=self.root, initialvalue=current)
        if not new_name:
            return
        for slot in self.cfg.get("prompt_slots") or []:
            if str(slot.get("name") or "").strip() == current:
                slot["name"] = new_name.strip()
                break
        self.prompt_slot_var.set(new_name.strip())
        self.auto_save("프롬프트 파일 이름 수정")
        self.refresh_all()

    def delete_prompt_file(self) -> None:
        current = self.prompt_slot_var.get().strip()
        slots = self.cfg.get("prompt_slots") or []
        if len(slots) <= 1:
            messagebox.showwarning("삭제 불가", "프롬프트 파일은 최소 1개는 남아 있어야 합니다.", parent=self.root)
            return
        doomed = None
        kept = []
        for slot in slots:
            if str(slot.get("name") or "").strip() == current and doomed is None:
                doomed = slot
            else:
                kept.append(slot)
        self.cfg["prompt_slots"] = kept
        if doomed:
            try:
                (self.base_dir / str(doomed.get("file") or "")).unlink(missing_ok=True)
            except Exception:
                pass
        self.prompt_slot_var.set(str((kept[0] or {}).get("name") or ""))
        self.auto_save("프롬프트 파일 삭제")
        self.refresh_all()

    def open_prompt_file(self) -> None:
        slot = self._current_prompt_slot()
        if not slot:
            return
        path = self.base_dir / str(slot.get("file") or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        try:
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("파일 경로", str(path), parent=self.root)

    def choose_download_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="저장 폴더 선택")
        if path:
            self.download_dir_var.set(path)
            self.auto_save("저장 폴더 변경")

    def open_browser_window(self) -> None:
        self._write_vars_to_config()
        url = str(self.cfg.get("grok_site_url") or "https://grok.com/imagine")
        attach_url = str(self.cfg.get("browser_attach_url") or "http://127.0.0.1:9222")
        profile_dir = str(self._browser_profile_path())
        launch_mode = "edge_attach"
        self.browser.open_project(url, profile_dir, launch_mode, attach_url, self.cfg)

    def start_run(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다.", parent=self.root)
            return
        self._write_vars_to_config()
        save_config(self.base_dir, self.cfg, self.config_name)
        plan = GrokAutomationEngine(self.base_dir, self.cfg).build_plan()
        if not plan.items:
            self.queue_items = []
            self._render_queue()
            self._refresh_progress_display()
            self._set_status_text("선택된 작업 없음")
            if str(self.cfg.get("number_mode") or "") == "manual" and not str(self.cfg.get("manual_numbers") or "").strip():
                messagebox.showwarning("개별 번호 비어 있음", "지금은 `개별`이 켜져 있는데 번호칸이 비어 있어요.\n번호를 적거나 `연속`으로 바꿔주세요.", parent=self.root)
                self.log("작업 준비 실패: 개별 번호칸이 비어 있어서 실행할 작업이 없습니다.")
            else:
                self.log("작업 준비: 선택된 작업 없음")
            return
        self._open_run_log_file()
        self._open_action_trace_file()
        self.queue_items = [
            QueueItem(number=item.number, tag=item.tag, prompt=item.rendered_prompt, status="pending", message=item.body)
            for item in plan.items
        ]
        self.log(f"작업 준비: {plan.selection_summary}")
        self._render_queue()
        self._refresh_progress_display()
        self.stop_event.clear()
        self.pause_event.clear()
        self._set_status_text("작업 시작")
        self.run_thread = threading.Thread(target=self._run_plan_thread, args=(plan,), daemon=True)
        self.run_thread.start()

    def stop_all(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()
        self.browser.stop()
        self.log("완전정지 요청")

    def pause_run(self) -> None:
        self.pause_event.set()
        self._set_status_text("일시정지")
        self.log("일시정지")

    def resume_run(self) -> None:
        self.pause_event.clear()
        self._set_status_text("재개")
        self.log("재개")

    def clear_queue(self) -> None:
        self.queue_items = []
        self._set_status_text("준비 완료")
        self._render_queue()
        self._refresh_progress_display()
        self.log("대기열 초기화")

    def copy_failed_numbers(self) -> None:
        failed = [item.number for item in self.queue_items if item.status == "failed"]
        text = compress_numbers(failed)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log(f"실패 번호 복사: {text or '(없음)'}")

    def copy_prompt_numbers(self) -> None:
        slot = self._current_prompt_slot()
        path = self.base_dir / str((slot or {}).get("file") or "")
        items = load_prompt_blocks(
            path,
            prefix=str(self.cfg.get("prompt_prefix") or "S"),
            pad_width=int(self.cfg.get("prompt_pad_width", 3) or 3),
            separator=str(self.cfg.get("prompt_separator") or "|||"),
            extra_prefixes=("V",) if str(self.cfg.get("media_mode") or "image") == "video" else (),
        )
        text = ",".join(f"{item.number:03d}" for item in items)
        if not text:
            messagebox.showwarning("번호 복사", "복사할 번호가 없습니다.", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log(f"프롬프트 번호 복사: {text}")

    def _render_queue(self) -> None:
        for child in self.queue_inner.winfo_children():
            child.destroy()
        width = max(self.queue_canvas.winfo_width(), 760)
        columns = 3 if width >= 930 else (2 if width >= 620 else 1)
        card_width = max(220, (width - 24) // columns - 10)
        for idx, item in enumerate(self.queue_items):
            row = idx // columns
            col = idx % columns
            card = tk.Frame(self.queue_inner, bg=self._queue_bg(item.status), highlightbackground=self._queue_border(item.status), highlightthickness=1, width=card_width)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            card.grid_propagate(False)
            tk.Label(card, text=f"{item.tag} Prompt", bg=self._queue_bg(item.status), fg="#ffffff", anchor="w", font=("Malgun Gothic", 10, "bold")).pack(fill="x", padx=10, pady=(8, 2))
            prompt_preview = item.prompt.replace("\n", " ")
            tk.Label(card, text=prompt_preview[:58], bg=self._queue_bg(item.status), fg="#dde9ff", anchor="w", justify="left", wraplength=card_width - 20, font=("Malgun Gothic", 9)).pack(fill="x", padx=10)
            tk.Label(card, text=self._queue_status_text(item), bg=self._queue_bg(item.status), fg=self._queue_status_color(item.status), anchor="w", justify="left", wraplength=card_width - 20, font=("Malgun Gothic", 9)).pack(fill="x", padx=10, pady=(6, 10))
        for col in range(columns):
            self.queue_inner.grid_columnconfigure(col, weight=1, minsize=card_width)
        self._refresh_queue_summary()
        self._update_queue_scroll()

    def _queue_status_text(self, item: QueueItem) -> str:
        mapping = {
            "pending": "보류 중",
            "running": "실행 중",
            "success": f"저장: {item.file_name or '-'}",
            "failed": item.message or "실패",
            "paused": "일시정지",
        }
        return mapping.get(item.status, item.status)

    def _queue_bg(self, status: str) -> str:
        return {
            "pending": "#1f314b",
            "running": "#5a4314",
            "success": "#123a29",
            "failed": "#4a1d24",
            "paused": "#323042",
        }.get(status, "#1f314b")

    def _queue_border(self, status: str) -> str:
        return {
            "pending": "#5b84b8",
            "running": "#c8963a",
            "success": "#3ccf88",
            "failed": "#ea6b7a",
            "paused": "#8a92a5",
        }.get(status, "#5b84b8")

    def _queue_status_color(self, status: str) -> str:
        return {
            "pending": "#8fd0ff",
            "running": "#ffd486",
            "success": "#8df0bd",
            "failed": "#ff95a3",
            "paused": "#d4d7e2",
        }.get(status, "#8fd0ff")

    def _refresh_queue_summary(self) -> None:
        active = sum(1 for item in self.queue_items if item.status == "running")
        done = sum(1 for item in self.queue_items if item.status == "success")
        failed = sum(1 for item in self.queue_items if item.status == "failed")
        pending = sum(1 for item in self.queue_items if item.status == "pending")
        self.queue_summary_var.set(f"활성 {active}개 | 완료 {done} | 실패 {failed} | 대기 {pending}")

    def _refresh_progress_display(self) -> None:
        total = len(self.queue_items)
        done = sum(1 for item in self.queue_items if item.status == "success")
        percent = (done / total * 100.0) if total else 0.0
        self.progress_var.set(f"{done} / {total} ({percent:.1f}%)")
        width = 300
        self.progress_canvas.coords(self.progress_fill, 0, 0, width * (percent / 100.0), 16)

    def _update_queue_scroll(self) -> None:
        self.queue_canvas.configure(scrollregion=self.queue_canvas.bbox("all"))

    def _on_queue_canvas_resize(self, event) -> None:
        self.queue_canvas.itemconfigure(self.queue_window, width=event.width)
        self._render_queue()

    def _on_mousewheel(self, event) -> None:
        try:
            self.queue_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _current_lower_pane_sash(self) -> int:
        return int(self.cfg.get("lower_pane_sash", 700) or 700)

    def _restore_lower_pane_sash(self) -> None:
        return

    def _on_lower_pane_released(self, _event=None) -> None:
        return

    def log(self, message: str) -> None:
        line = str(message or "").strip()
        if not line:
            return
        stamped = f"[{datetime.now().strftime('%H:%M:%S')}] {line}"
        self.log_lines.append(stamped)
        self.log_lines = self.log_lines[-400:]
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "\n".join(self.log_lines))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self._write_run_log_line(stamped)

    def _current_prompt_slot(self) -> dict:
        current = self.prompt_slot_var.get().strip()
        for slot in self.cfg.get("prompt_slots") or []:
            if str(slot.get("name") or "").strip() == current:
                return slot
        return (self.cfg.get("prompt_slots") or [{}])[0]

    def _int_or_default(self, value, default: int) -> int:
        try:
            return max(1, int(str(value).strip()))
        except Exception:
            return default

    def _nonnegative_int_or_default(self, value, default: int) -> int:
        try:
            return max(0, int(str(value).strip()))
        except Exception:
            return default

    def _float_or_default(self, value, default: float) -> float:
        try:
            return max(0.0, round(float(str(value).strip()), 1))
        except Exception:
            return default

    def _default_browser_profile_dir(self) -> str:
        attach_url = str(self.cfg.get("browser_attach_url") or self.forced_attach_url or "http://127.0.0.1:9222").strip()
        return default_attach_profile_dir(attach_url)

    def _normalize_browser_profile_dir(self) -> None:
        current = str(self.cfg.get("browser_profile_dir") or "").strip()
        if (not current) or current == "runtime/browser_profile_1":
            self.cfg["browser_profile_dir"] = self._default_browser_profile_dir()

    def _browser_profile_dir_name(self) -> str:
        self._normalize_browser_profile_dir()
        return str(self.cfg.get("browser_profile_dir") or self._default_browser_profile_dir()).strip()

    def _browser_profile_path(self) -> Path:
        raw = self._browser_profile_dir_name()
        path = Path(raw)
        if not path.is_absolute():
            path = self.base_dir / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _suggest_new_browser_profile_dir(self) -> str:
        current = self._browser_profile_dir_name()
        stem = Path(current).name
        parent = Path(current).parent.as_posix()
        match = re.match(r"^(.*?)(?:_v(\d+))?$", stem)
        if match:
            base_name = (match.group(1) or "edge_attach_profile").strip() or "edge_attach_profile"
            current_no = int(match.group(2)) if match.group(2) else 1
        else:
            base_name = stem or "edge_attach_profile"
            current_no = 1
        candidate_no = max(2, current_no + 1)
        while True:
            candidate_name = f"{base_name}_v{candidate_no}"
            rel = f"{parent}/{candidate_name}" if parent not in {"", "."} else candidate_name
            candidate_path = self.base_dir / rel
            if not candidate_path.exists():
                return rel.replace("\\", "/")
            candidate_no += 1

    def _refresh_browser_profile_ui(self) -> None:
        if hasattr(self, "browser_profile_state_label"):
            self.browser_profile_state_label.config(text=f"현재 프로필: {Path(self._browser_profile_dir_name()).name}")

    def create_browser_profile(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            messagebox.showwarning("안내", "작업 실행 중에는 새 브라우저 프로필을 만들 수 없습니다.\n먼저 중지 후 시도해주세요.", parent=self.root)
            return
        self._write_vars_to_config()
        current = self._browser_profile_dir_name()
        new_profile = self._suggest_new_browser_profile_dir()
        new_path = self.base_dir / new_profile
        try:
            new_path.mkdir(parents=True, exist_ok=True)
            self.cfg["browser_profile_dir"] = new_profile.replace("\\", "/")
            save_config(self.base_dir, self.cfg, self.config_name)
            self._refresh_browser_profile_ui()
            self.refresh_summary_only()
            self.log(f"🆕 새 브라우저 프로필 준비 완료: {Path(current).name} -> {Path(new_profile).name}")
            messagebox.showinfo(
                "새 브라우저 프로필 만들기",
                "새 브라우저 프로필을 만들었습니다.\n\n"
                f"- 이전 프로필: {Path(current).name}\n"
                f"- 새 프로필: {Path(new_profile).name}\n\n"
                "이제 Edge 실행 파일을 다시 열면 새 프로필로 켜집니다.\n"
                "1. 기존 Edge 작업창 닫기\n"
                "2. 워커용 Edge 실행 파일 다시 열기\n"
                "3. 로그인 1번 진행하기",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("새 브라우저 프로필 만들기 실패", f"프로필 생성 중 오류가 났습니다.\n{exc}", parent=self.root)

    def on_close(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()
        self._write_vars_to_config()
        save_config(self.base_dir, self.cfg, self.config_name)
        self.browser.stop()
        self._close_run_log_file()
        self._close_action_trace_file()
        self.root.destroy()

    def _run_plan_thread(self, plan) -> None:
        engine = GrokAutomationEngine(self.base_dir, self.cfg)
        try:
            engine.run(
                plan=plan,
                log=self._thread_log,
                trace_action=self._thread_trace,
                set_status=self._thread_status,
                update_queue=self._thread_queue_update,
                should_stop=self.stop_event.is_set,
                wait_if_paused=self._thread_wait_if_paused,
            )
        except Exception as exc:
            self._thread_log(f"❌ 실행 오류: {exc}")
            self._thread_status("실행 오류")
        finally:
            self.root.after(0, self._render_queue)
            self.root.after(0, self._refresh_progress_display)
            self.root.after(0, self._close_run_log_file)
            self.root.after(0, self._close_action_trace_file)

    def _thread_wait_if_paused(self) -> None:
        while self.pause_event.is_set() and not self.stop_event.is_set():
            time.sleep(0.2)

    def _thread_log(self, message: str) -> None:
        self.root.after(0, lambda m=message: self.log(m))

    def _thread_trace(self, message: str) -> None:
        self.root.after(0, lambda m=message: self._write_action_trace_message(m))

    def _thread_status(self, text: str) -> None:
        self.root.after(0, lambda t=text: self._set_status_text(t))

    def _cancel_status_countdown(self) -> None:
        if self._status_countdown_after_id is not None:
            try:
                self.root.after_cancel(self._status_countdown_after_id)
            except Exception:
                pass
        self._status_countdown_after_id = None
        self._status_countdown_deadline = None
        self._status_countdown_prefix = None

    def _tick_status_countdown(self) -> None:
        deadline = self._status_countdown_deadline
        prefix = self._status_countdown_prefix
        if deadline is None or not prefix:
            self._status_countdown_after_id = None
            return
        remain = max(0, int(math.ceil(deadline - time.time())))
        self.status_var.set(f"{prefix} {remain}초")
        if remain <= 0:
            self._status_countdown_after_id = None
            return
        self._status_countdown_after_id = self.root.after(200, self._tick_status_countdown)

    def _set_status_text(self, text: str) -> None:
        raw = str(text or "").strip()
        match = re.match(r"^(.*?)(\d+)초$", raw)
        if match:
            prefix = str(match.group(1) or "").rstrip()
            seconds = max(0, int(match.group(2) or 0))
            self._cancel_status_countdown()
            self._status_countdown_prefix = prefix
            self._status_countdown_deadline = time.time() + seconds
            self._tick_status_countdown()
            return
        self._cancel_status_countdown()
        self.status_var.set(raw)

    def _thread_queue_update(self, number: int, status: str, message: str, file_name: str) -> None:
        def _apply():
            for item in self.queue_items:
                if item.number == number:
                    item.status = status
                    item.message = message
                    item.file_name = file_name
                    break
            self._render_queue()
            self._refresh_progress_display()
        self.root.after(0, _apply)

    def run(self) -> None:
        self.root.mainloop()

    def _open_run_log_file(self) -> None:
        self._close_run_log_file()
        logs_dir = self.base_dir / LOGS_DIR
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(self.config_name).stem).strip("_") or "worker"
        self.run_log_path = logs_dir / f"grok_worker_run_{log_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.run_log_fp = self.run_log_path.open("a", encoding="utf-8")
        self.log(f"로그 파일 생성: {self.run_log_path}")

    def _write_run_log_line(self, line: str) -> None:
        if self.run_log_fp is None:
            return
        try:
            self.run_log_fp.write(line + "\n")
            self.run_log_fp.flush()
        except Exception:
            pass

    def _close_run_log_file(self) -> None:
        if self.run_log_fp is not None:
            try:
                self.run_log_fp.flush()
                self.run_log_fp.close()
            except Exception:
                pass
        self.run_log_fp = None

    def _open_action_trace_file(self) -> None:
        self._close_action_trace_file()
        logs_dir = self.base_dir / LOGS_DIR
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(self.config_name).stem).strip("_") or "worker"
        self.action_trace_path = logs_dir / f"grok_worker_action_trace_{log_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.action_trace_fp = self.action_trace_path.open("a", encoding="utf-8")
        self._write_action_trace_message(f"액션 로그 파일 생성: {self.action_trace_path}")
        self.log(f"액션 트레이스 로그 생성: {self.action_trace_path}")

    def _write_action_trace_message(self, message: str) -> None:
        line = str(message or "").strip()
        if not line or self.action_trace_fp is None:
            return
        stamped = f"[{datetime.now().strftime('%H:%M:%S')}] {line}"
        try:
            self.action_trace_fp.write(stamped + "\n")
            self.action_trace_fp.flush()
        except Exception:
            pass

    def _close_action_trace_file(self) -> None:
        if self.action_trace_fp is not None:
            try:
                self._write_action_trace_message("액션 로그 종료")
                self.action_trace_fp.flush()
                self.action_trace_fp.close()
            except Exception:
                pass
        self.action_trace_fp = None
