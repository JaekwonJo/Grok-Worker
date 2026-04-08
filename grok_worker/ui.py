from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .automation import GrokAutomationEngine
from .browser import BrowserManager
from .config import DEFAULT_CONFIG, next_prompt_slot_file, save_config, load_config
from .prompt_parser import compress_numbers, summarize_prompt_file
from .queue_state import QueueItem


class GrokWorkerApp:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.cfg = load_config(self.base_dir)
        self.browser = BrowserManager(self.log)
        self.queue_items: list[QueueItem] = []
        self.log_lines: list[str] = []

        self.root = tk.Tk()
        self.root.title(f"Grok Worker - {self.cfg.get('worker_name', 'Grok_워커1')}")
        self.root.geometry("1140x780")
        self.root.minsize(980, 700)
        self.root.configure(bg="#14161b")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_vars()
        self._build_ui()
        self._load_vars_from_config()
        self.refresh_all()

    def _build_vars(self) -> None:
        self.worker_name_var = tk.StringVar()
        self.project_var = tk.StringVar()
        self.prompt_slot_var = tk.StringVar()
        self.reference_image_dir_var = tk.StringVar()
        self.download_dir_var = tk.StringVar()
        self.browser_profile_var = tk.StringVar()
        self.number_mode_var = tk.StringVar()
        self.start_number_var = tk.StringVar()
        self.end_number_var = tk.StringVar()
        self.manual_numbers_var = tk.StringVar()
        self.typing_speed_var = tk.DoubleVar()
        self.humanize_typing_var = tk.BooleanVar()
        self.status_var = tk.StringVar(value="준비 완료")
        self.progress_var = tk.StringVar(value="0 / 0 (0.0%)")
        self.project_summary_var = tk.StringVar(value="프로젝트: -")
        self.queue_summary_var = tk.StringVar(value="활성 0개 | 완료 0 | 실패 0 | 대기 0")
        self.prompt_file_summary_var = tk.StringVar(value="")

    def _build_ui(self) -> None:
        root = self.root

        top = tk.Frame(root, bg="#14161b")
        top.pack(fill="x", padx=16, pady=(16, 10))

        top_left = tk.Frame(top, bg="#1d2432", highlightbackground="#41608a", highlightthickness=1)
        top_left.pack(side="left", fill="both", expand=True)
        tk.Label(top_left, text="Grok 이미지 워커", bg="#1d2432", fg="#ffffff", font=("Malgun Gothic", 16, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(top_left, textvariable=self.worker_name_var, bg="#1d2432", fg="#a9bdd8", font=("Malgun Gothic", 10)).pack(anchor="w", padx=14, pady=(0, 12))

        top_mid = tk.Frame(top, bg="#202b3e", width=360, highlightbackground="#4c6b9a", highlightthickness=1)
        top_mid.pack(side="left", padx=14, fill="y")
        tk.Label(top_mid, text="진행 상황", bg="#202b3e", fg="#d8e4ff", font=("Malgun Gothic", 12, "bold")).pack(pady=(10, 4))
        tk.Label(top_mid, textvariable=self.project_summary_var, bg="#202b3e", fg="#c4d4ec", font=("Malgun Gothic", 10)).pack()
        tk.Label(top_mid, textvariable=self.progress_var, bg="#202b3e", fg="#80c6ff", font=("Consolas", 15, "bold")).pack(pady=(6, 6))
        self.progress_canvas = tk.Canvas(top_mid, width=300, height=16, bg="#152033", highlightthickness=1, highlightbackground="#314966")
        self.progress_canvas.pack(padx=18, pady=(0, 10))
        self.progress_fill = self.progress_canvas.create_rectangle(0, 0, 0, 18, fill="#4ca7ff", outline="")

        top_right = tk.Frame(top, bg="#1d2432", highlightbackground="#41608a", highlightthickness=1)
        top_right.pack(side="left", fill="both", expand=True)
        tk.Label(top_right, text="현재 상태", bg="#1d2432", fg="#d8e4ff", font=("Malgun Gothic", 11, "bold")).pack(anchor="e", padx=12, pady=(12, 4))
        tk.Label(top_right, textvariable=self.status_var, bg="#1d2432", fg="#79e3a0", font=("Malgun Gothic", 13, "bold"), wraplength=230, justify="right").pack(anchor="e", padx=12, pady=(0, 12))

        body = tk.Frame(root, bg="#14161b")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        settings = tk.Frame(body, bg="#14161b")
        settings.pack(fill="x")

        left = tk.Frame(settings, bg="#1a2f4f", highlightbackground="#5b84b8", highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(settings, bg="#1a2f4f", highlightbackground="#5b84b8", highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_basic_settings(left)
        self._build_number_settings(right)

        action_row = tk.Frame(body, bg="#14161b")
        action_row.pack(fill="x", pady=(12, 10))

        self._action_button(action_row, "완전정지", self.stop_all, "#233042").pack(side="left", padx=(0, 8))
        self._action_button(action_row, "일시정지", self.pause_run, "#233042").pack(side="left", padx=8)
        self._action_button(action_row, "재개", self.resume_run, "#233042").pack(side="left", padx=8)
        self._action_button(action_row, "💾 저장", self.manual_save, "#31527d").pack(side="left", padx=8)
        self._action_button(action_row, "작업봇 창 열기", self.open_browser_window, "#31527d").pack(side="right", padx=(8, 0))
        self._action_button(action_row, "▶ 시작", self.start_run, "#2f8a68").pack(side="right", padx=(8, 0))

        queue_wrap = tk.Frame(body, bg="#17283f", highlightbackground="#5b84b8", highlightthickness=1)
        queue_wrap.pack(fill="both", expand=True)

        queue_header = tk.Frame(queue_wrap, bg="#17283f")
        queue_header.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(queue_header, text="Grok 생성+다운로드 대기열", bg="#17283f", fg="#ffffff", font=("Malgun Gothic", 12, "bold")).pack(side="left")
        self._action_button(queue_header, "실패 번호 복붙", self.copy_failed_numbers, "#31527d", small=True).pack(side="right", padx=(8, 0))
        self._action_button(queue_header, "지우기", self.clear_queue, "#31527d", small=True).pack(side="right")
        tk.Label(queue_header, textvariable=self.queue_summary_var, bg="#17283f", fg="#c4d4ec", font=("Malgun Gothic", 10)).pack(side="right", padx=(12, 16))

        queue_body = tk.Frame(queue_wrap, bg="#17283f")
        queue_body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.queue_canvas = tk.Canvas(queue_body, bg="#17283f", highlightthickness=0)
        self.queue_scroll = tk.Scrollbar(queue_body, orient="vertical", command=self.queue_canvas.yview)
        self.queue_canvas.configure(yscrollcommand=self.queue_scroll.set)
        self.queue_scroll.pack(side="right", fill="y")
        self.queue_canvas.pack(side="left", fill="both", expand=True)
        self.queue_inner = tk.Frame(self.queue_canvas, bg="#17283f")
        self.queue_window = self.queue_canvas.create_window((0, 0), window=self.queue_inner, anchor="nw")
        self.queue_inner.bind("<Configure>", lambda _e: self._update_queue_scroll())
        self.queue_canvas.bind("<Configure>", self._on_queue_canvas_resize)
        self.queue_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        log_frame = tk.Frame(body, bg="#14161b")
        log_frame.pack(fill="both", pady=(10, 0))
        tk.Label(log_frame, text="로그", bg="#14161b", fg="#d8e4ff", font=("Malgun Gothic", 11, "bold")).pack(anchor="w")
        self.log_text = tk.Text(log_frame, height=8, bg="#101723", fg="#d7e5ff", insertbackground="#ffffff", relief="solid", borderwidth=1)
        self.log_text.pack(fill="both", expand=False, pady=(6, 0))
        self.log_text.configure(state="disabled")

    def _build_basic_settings(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="기본 설정", bg="#1a2f4f", fg="#ffffff", font=("Malgun Gothic", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 10))
        header_actions = tk.Frame(parent, bg="#1a2f4f")
        header_actions.pack(fill="x", padx=14, pady=(0, 10))
        self._action_button(header_actions, "새로고침", self.refresh_all, "#31527d", small=True).pack(side="right", padx=(8, 0))
        self._action_button(header_actions, "새 프로필", self.create_new_profile, "#31527d", small=True).pack(side="right", padx=(8, 0))
        self._action_button(header_actions, "이름 변경", self.rename_worker, "#31527d", small=True).pack(side="right")

        self._labeled_combo(parent, "프로젝트", self.project_var, self.project_changed)
        project_btns = tk.Frame(parent, bg="#1a2f4f")
        project_btns.pack(fill="x", padx=14, pady=(0, 10))
        self._action_button(project_btns, "프로젝트 추가", self.add_project, "#31527d", small=True).pack(side="left")
        self._action_button(project_btns, "이름 변경", self.rename_project, "#31527d", small=True).pack(side="left", padx=8)
        self._action_button(project_btns, "URL 편집", self.edit_project_url, "#31527d", small=True).pack(side="left", padx=8)
        self._action_button(project_btns, "삭제", self.delete_project, "#31527d", small=True).pack(side="left", padx=8)

        self._labeled_combo(parent, "프롬프트 파일", self.prompt_slot_var, self.prompt_slot_changed)
        prompt_btns = tk.Frame(parent, bg="#1a2f4f")
        prompt_btns.pack(fill="x", padx=14, pady=(0, 4))
        self._action_button(prompt_btns, "파일 열기", self.open_prompt_file, "#31527d", small=True).pack(side="left")
        self._action_button(prompt_btns, "이름수정", self.rename_prompt_file, "#31527d", small=True).pack(side="left", padx=8)
        self._action_button(prompt_btns, "삭제", self.delete_prompt_file, "#31527d", small=True).pack(side="left", padx=8)
        self._action_button(prompt_btns, "추가", self.add_prompt_file, "#31527d", small=True).pack(side="left", padx=8)
        tk.Label(parent, textvariable=self.prompt_file_summary_var, bg="#1a2f4f", fg="#c8d7eb", font=("Malgun Gothic", 10)).pack(anchor="w", padx=14, pady=(0, 12))

        self._path_row(parent, "레퍼런스 이미지 폴더", self.reference_image_dir_var, self.choose_reference_dir)
        self._path_row(parent, "저장 폴더", self.download_dir_var, self.choose_download_dir)
        self._path_row(parent, "브라우저 프로필", self.browser_profile_var, self.choose_browser_profile_dir)

    def _build_number_settings(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="번호 설정", bg="#1a2f4f", fg="#ffffff", font=("Malgun Gothic", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 10))
        mode_row = tk.Frame(parent, bg="#1a2f4f")
        mode_row.pack(fill="x", padx=14, pady=(0, 10))
        for text, value in (("연속", "range"), ("개별", "manual")):
            tk.Radiobutton(
                mode_row,
                text=text,
                value=value,
                variable=self.number_mode_var,
                command=self.on_number_mode_changed,
                bg="#1a2f4f",
                fg="#ffffff",
                selectcolor="#21314f",
                activebackground="#1a2f4f",
                activeforeground="#ffffff",
                font=("Malgun Gothic", 10),
            ).pack(side="left", padx=(0, 18))

        range_row = tk.Frame(parent, bg="#1a2f4f")
        range_row.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(range_row, text="연속 범위", bg="#1a2f4f", fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.start_entry = tk.Entry(range_row, textvariable=self.start_number_var, width=8, font=("Consolas", 12))
        self.start_entry.pack(side="left", padx=(12, 6))
        tk.Label(range_row, text="~", bg="#1a2f4f", fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(side="left")
        self.end_entry = tk.Entry(range_row, textvariable=self.end_number_var, width=8, font=("Consolas", 12))
        self.end_entry.pack(side="left", padx=(6, 0))

        manual_row = tk.Frame(parent, bg="#1a2f4f")
        manual_row.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(manual_row, text="개별 번호", bg="#1a2f4f", fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        self.manual_entry = tk.Entry(manual_row, textvariable=self.manual_numbers_var, font=("Consolas", 12))
        self.manual_entry.pack(fill="x", pady=(6, 0))

        speed_row = tk.Frame(parent, bg="#1a2f4f")
        speed_row.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(speed_row, text="타이핑 속도", bg="#1a2f4f", fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        self.speed_scale = tk.Scale(
            speed_row,
            from_=0.5,
            to=2.0,
            resolution=0.1,
            orient="horizontal",
            variable=self.typing_speed_var,
            bg="#1a2f4f",
            fg="#ffffff",
            troughcolor="#23354f",
            highlightthickness=0,
            command=lambda _v: self.auto_save("타이핑 속도 변경"),
        )
        self.speed_scale.pack(fill="x")

        tk.Checkbutton(
            parent,
            text="인간처럼 입력하기",
            variable=self.humanize_typing_var,
            command=lambda: self.auto_save("입력 방식 변경"),
            bg="#1a2f4f",
            fg="#ffffff",
            selectcolor="#20304a",
            activebackground="#1a2f4f",
            activeforeground="#ffffff",
            font=("Malgun Gothic", 10),
        ).pack(anchor="w", padx=14, pady=(0, 10))

        hint = (
            "프롬프트 파일은 `001 : 본문 |||` 형식으로 쓰면 됩니다.\n"
            "실행할 때 실제 입력창에는 자동으로 `S001 Prompt : 본문` 형식으로 들어갑니다."
        )
        tk.Label(parent, text=hint, bg="#1a2f4f", fg="#bcd0e9", justify="left", font=("Malgun Gothic", 10)).pack(anchor="w", padx=14, pady=(0, 12))

    def _labeled_combo(self, parent: tk.Frame, label: str, variable: tk.StringVar, callback) -> None:
        row = tk.Frame(parent, bg="#1a2f4f")
        row.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(row, text=label, bg="#1a2f4f", fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        combo = tk.OptionMenu(row, variable, "")
        combo.configure(font=("Malgun Gothic", 10), bg="#f0ede4", width=48, highlightthickness=0)
        combo.pack(fill="x", pady=(6, 0))
        variable.trace_add("write", lambda *_: callback())
        if label == "프로젝트":
            self.project_menu = combo
        else:
            self.prompt_menu = combo

    def _path_row(self, parent: tk.Frame, label: str, variable: tk.StringVar, command) -> None:
        row = tk.Frame(parent, bg="#1a2f4f")
        row.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(row, text=label, bg="#1a2f4f", fg="#d8e4ff", font=("Malgun Gothic", 10)).pack(anchor="w")
        input_row = tk.Frame(row, bg="#1a2f4f")
        input_row.pack(fill="x", pady=(6, 0))
        entry = tk.Entry(input_row, textvariable=variable, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True)
        self._action_button(input_row, "선택", command, "#31527d", small=True).pack(side="left", padx=(8, 0))

    def _action_button(self, parent, text, command, bg, small=False):
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
            cursor="hand2",
        )

    def _load_vars_from_config(self) -> None:
        self.worker_name_var.set(str(self.cfg.get("worker_name") or "Grok_워커1"))
        projects = self.cfg.get("project_profiles") or []
        slots = self.cfg.get("prompt_slots") or []
        project_index = max(0, min(int(self.cfg.get("project_index", 0) or 0), len(projects) - 1))
        slot_index = max(0, min(int(self.cfg.get("prompt_slot_index", 0) or 0), len(slots) - 1))
        self.project_var.set(str((projects[project_index] or {}).get("name") or ""))
        self.prompt_slot_var.set(str((slots[slot_index] or {}).get("name") or ""))
        self.reference_image_dir_var.set(str(self.cfg.get("reference_image_dir") or ""))
        self.download_dir_var.set(str(self.cfg.get("download_output_dir") or ""))
        self.browser_profile_var.set(str(self.cfg.get("browser_profile_dir") or ""))
        self.number_mode_var.set(str(self.cfg.get("number_mode") or "range"))
        self.start_number_var.set(str(self.cfg.get("start_number", 1) or 1))
        self.end_number_var.set(str(self.cfg.get("end_number", 10) or 10))
        self.manual_numbers_var.set(str(self.cfg.get("manual_numbers") or ""))
        self.typing_speed_var.set(float(self.cfg.get("typing_speed", 1.0) or 1.0))
        self.humanize_typing_var.set(bool(self.cfg.get("humanize_typing", True)))

    def _write_vars_to_config(self) -> None:
        projects = self.cfg.get("project_profiles") or []
        slots = self.cfg.get("prompt_slots") or []
        self.cfg["worker_name"] = self.worker_name_var.get().strip() or "Grok_워커1"
        self.cfg["reference_image_dir"] = self.reference_image_dir_var.get().strip()
        self.cfg["download_output_dir"] = self.download_dir_var.get().strip()
        self.cfg["browser_profile_dir"] = self.browser_profile_var.get().strip()
        self.cfg["number_mode"] = self.number_mode_var.get().strip() or "range"
        self.cfg["start_number"] = self._int_or_default(self.start_number_var.get(), 1)
        self.cfg["end_number"] = self._int_or_default(self.end_number_var.get(), self.cfg["start_number"])
        self.cfg["manual_numbers"] = self.manual_numbers_var.get().strip()
        self.cfg["typing_speed"] = round(float(self.typing_speed_var.get() or 1.0), 1)
        self.cfg["humanize_typing"] = bool(self.humanize_typing_var.get())

        project_name = self.project_var.get().strip()
        slot_name = self.prompt_slot_var.get().strip()
        for idx, project in enumerate(projects):
            if str(project.get("name") or "").strip() == project_name:
                self.cfg["project_index"] = idx
                break
        for idx, slot in enumerate(slots):
            if str(slot.get("name") or "").strip() == slot_name:
                self.cfg["prompt_slot_index"] = idx
                break

    def auto_save(self, reason: str = "") -> None:
        self._write_vars_to_config()
        save_config(self.base_dir, self.cfg)
        if reason:
            self.log(f"자동 저장: {reason}")
        self.refresh_summary_only()

    def manual_save(self) -> None:
        self._write_vars_to_config()
        path = save_config(self.base_dir, self.cfg)
        self.log(f"설정 저장: {path.name}")
        self.refresh_summary_only()

    def refresh_all(self) -> None:
        self._refresh_project_menu()
        self._refresh_prompt_menu()
        self.on_number_mode_changed()
        self.refresh_summary_only()
        self._render_queue()

    def refresh_summary_only(self) -> None:
        projects = self.cfg.get("project_profiles") or []
        project_idx = int(self.cfg.get("project_index", 0) or 0)
        project_name = str((projects[project_idx] or {}).get("name") or "-") if projects else "-"
        self.project_summary_var.set(f"프로젝트: {project_name}")
        slots = self.cfg.get("prompt_slots") or []
        slot_idx = int(self.cfg.get("prompt_slot_index", 0) or 0)
        if slots:
            slot_file = str((slots[slot_idx] or {}).get("file") or "")
            slot_path = self.base_dir / slot_file
            self.prompt_file_summary_var.set(
                summarize_prompt_file(
                    slot_path,
                    prefix=str(self.cfg.get("prompt_prefix") or "S"),
                    pad_width=int(self.cfg.get("prompt_pad_width", 3) or 3),
                    separator=str(self.cfg.get("prompt_separator") or "|||"),
                )
            )
        self._refresh_queue_summary()
        self._refresh_progress_display()
        self.root.title(f"Grok Worker - {self.cfg.get('worker_name', 'Grok_워커1')}")

    def _refresh_project_menu(self) -> None:
        menu = self.project_menu["menu"]
        menu.delete(0, "end")
        values = [str(project.get("name") or "") for project in self.cfg.get("project_profiles") or []]
        for value in values:
            menu.add_command(label=value, command=lambda v=value: self.project_var.set(v))
        if values and self.project_var.get() not in values:
            self.project_var.set(values[0])

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
        self.auto_save("번호 방식 변경")

    def project_changed(self) -> None:
        if self.project_var.get().strip():
            self.auto_save("프로젝트 선택 변경")

    def prompt_slot_changed(self) -> None:
        if self.prompt_slot_var.get().strip():
            self.auto_save("프롬프트 파일 선택 변경")

    def add_project(self) -> None:
        name = simpledialog.askstring("프로젝트 추가", "프로젝트 이름을 입력하세요:", parent=self.root)
        if not name:
            return
        url = simpledialog.askstring("프로젝트 URL", "프로젝트 URL을 입력하세요:", parent=self.root, initialvalue="https://grok.com/imagine")
        if not url:
            return
        self.cfg.setdefault("project_profiles", []).append({"name": name.strip(), "url": url.strip()})
        self.project_var.set(name.strip())
        self.auto_save("프로젝트 추가")
        self.refresh_all()

    def rename_project(self) -> None:
        current = self.project_var.get().strip()
        if not current:
            return
        new_name = simpledialog.askstring("프로젝트 이름 변경", "새 프로젝트 이름을 입력하세요:", parent=self.root, initialvalue=current)
        if not new_name:
            return
        for project in self.cfg.get("project_profiles") or []:
            if str(project.get("name") or "").strip() == current:
                project["name"] = new_name.strip()
                break
        self.project_var.set(new_name.strip())
        self.auto_save("프로젝트 이름 변경")
        self.refresh_all()

    def edit_project_url(self) -> None:
        current = self.project_var.get().strip()
        if not current:
            return
        project = self._current_project()
        url = simpledialog.askstring("URL 편집", "프로젝트 URL을 입력하세요:", parent=self.root, initialvalue=str(project.get("url") or ""))
        if not url:
            return
        project["url"] = url.strip()
        self.auto_save("프로젝트 URL 변경")

    def delete_project(self) -> None:
        current = self.project_var.get().strip()
        profiles = self.cfg.get("project_profiles") or []
        if len(profiles) <= 1:
            messagebox.showwarning("삭제 불가", "프로젝트는 최소 1개는 남아 있어야 합니다.", parent=self.root)
            return
        self.cfg["project_profiles"] = [project for project in profiles if str(project.get("name") or "").strip() != current]
        self.project_var.set(str((self.cfg["project_profiles"][0] or {}).get("name") or ""))
        self.auto_save("프로젝트 삭제")
        self.refresh_all()

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

    def choose_reference_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="레퍼런스 이미지 폴더 선택")
        if path:
            self.reference_image_dir_var.set(path)
            self.auto_save("레퍼런스 이미지 폴더 변경")

    def choose_download_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="저장 폴더 선택")
        if path:
            self.download_dir_var.set(path)
            self.auto_save("저장 폴더 변경")

    def choose_browser_profile_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="브라우저 프로필 폴더 선택")
        if path:
            self.browser_profile_var.set(path)
            self.auto_save("브라우저 프로필 변경")

    def create_new_profile(self) -> None:
        runtime_dir = (self.base_dir / "runtime").resolve()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        idx = 1
        while True:
            path = runtime_dir / f"browser_profile_{idx}"
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                self.browser_profile_var.set(str(path))
                self.auto_save("새 브라우저 프로필 생성")
                break
            idx += 1

    def rename_worker(self) -> None:
        current = self.worker_name_var.get().strip()
        new_name = simpledialog.askstring("워커 이름 변경", "새 워커 이름을 입력하세요:", parent=self.root, initialvalue=current)
        if not new_name:
            return
        self.worker_name_var.set(new_name.strip())
        self.auto_save("워커 이름 변경")

    def open_browser_window(self) -> None:
        self._write_vars_to_config()
        project = self._current_project()
        url = str(project.get("url") or self.cfg.get("grok_site_url") or "https://grok.com/imagine")
        profile_dir = str(self.cfg.get("browser_profile_dir") or (self.base_dir / "runtime" / "browser_profile_1"))
        self.browser.open_project(url, profile_dir)

    def start_run(self) -> None:
        self._write_vars_to_config()
        plan = GrokAutomationEngine(self.base_dir, self.cfg).build_plan()
        self.queue_items = [
            QueueItem(number=item.number, tag=item.tag, prompt=item.rendered_prompt, status="pending", message=item.body)
            for item in plan.items
        ]
        self.status_var.set("1차 UI 준비 완료 | 실제 Grok 자동화 연결 전")
        self.log(f"작업 준비: {plan.selection_summary}")
        if self.queue_items:
            self.log(f"예시 입력: {self.queue_items[0].prompt}")
        self._render_queue()
        self._refresh_progress_display()

    def stop_all(self) -> None:
        self.browser.stop()
        self.status_var.set("준비 완료")
        self.log("완전정지 요청")

    def pause_run(self) -> None:
        self.status_var.set("일시정지")
        self.log("일시정지")

    def resume_run(self) -> None:
        self.status_var.set("재개")
        self.log("재개")

    def clear_queue(self) -> None:
        self.queue_items = []
        self.status_var.set("준비 완료")
        self._render_queue()
        self._refresh_progress_display()
        self.log("대기열 초기화")

    def copy_failed_numbers(self) -> None:
        failed = [item.number for item in self.queue_items if item.status == "failed"]
        text = compress_numbers(failed, prefix="G")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log(f"실패 번호 복사: {text or '(없음)'}")

    def _render_queue(self) -> None:
        for child in self.queue_inner.winfo_children():
            child.destroy()
        columns = 3
        width = max(self.queue_canvas.winfo_width(), 960)
        card_width = max(250, (width - 36) // columns - 12)
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

    def log(self, message: str) -> None:
        line = str(message or "").strip()
        if not line:
            return
        self.log_lines.append(line)
        self.log_lines = self.log_lines[-400:]
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "\n".join(self.log_lines))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _current_project(self) -> dict:
        current = self.project_var.get().strip()
        for project in self.cfg.get("project_profiles") or []:
            if str(project.get("name") or "").strip() == current:
                return project
        return (self.cfg.get("project_profiles") or [{}])[0]

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

    def on_close(self) -> None:
        self._write_vars_to_config()
        save_config(self.base_dir, self.cfg)
        self.browser.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
