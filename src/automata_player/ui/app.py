"""악보를 고르고 연주를 시작하는 창.

배포용 실행 파일은 인자 없이 이 창을 연다.
tkinter만 쓰므로 따로 설치할 화면 라이브러리가 없다.
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, ttk

from automata_player.cli import format_score
from automata_player.i18n import (
    LANGUAGES,
    LANGUAGE_LABELS,
    get_language,
    instrument_detail,
    instrument_name,
    language_code,
    language_label,
    load_language,
    save_language,
    set_language,
    t,
)
from automata_player.instruments import Instrument, get_instrument, list_instruments
from automata_player.model import AutomataError, Score
from automata_player.playability import assess
from automata_player.score import load_score
from automata_player.ui.session import PlayRequest, PlaySession, live_backend_name


def _enable_dpi() -> None:
    """고해상도 화면에서 창이 흐려지지 않게 한다. 창을 만들기 전에 호출해야 한다."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            return


def run_gui() -> int:
    load_language()
    _enable_dpi()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.session = PlaySession()
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._closed = False
        self._loaded_path = ""
        self._score: Score | None = None
        self._blocked = False
        self._suggestion: int | None = None
        self._minimized_for_play = False
        self._instruments = list(list_instruments())

        root.title("AutomataPlayer")
        root.minsize(680, 540)
        root.geometry("760x600")
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.path_var = tk.StringVar()
        self.summary_var = tk.StringVar(value=t("choose_score"))
        self.instrument_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="preview")
        self.realtime_var = tk.BooleanVar(value=False)
        self.speed_var = tk.StringVar(value="1.0")
        self.transpose_var = tk.StringVar(value="0")
        self.countdown_var = tk.StringVar(value="3")
        self.part_var = tk.StringVar(value=t("all_parts"))
        self.status_var = tk.StringVar(value=t("ready"))
        self._status_key = "ready"
        self.warning_var = tk.StringVar()
        self._i18n: list[tuple[tk.Widget, str]] = []
        self._log_is_intro = True

        self._build()
        self._select_instrument(0)
        self.transpose_var.trace_add("write", lambda *_args: self._refresh_playability())
        self.part_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_playability())
        self._apply_language()
        self._after_id = root.after(50, self.drain)

    def _build(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Warn.TLabel", foreground="#9a3412")
        family = "Malgun Gothic"
        available = set(tkfont.families(self.root))
        if family not in available:
            family = "Segoe UI" if "Segoe UI" in available else "TkDefaultFont"
        tkfont.nametofont("TkDefaultFont").configure(family=family, size=10)
        tkfont.nametofont("TkTextFont").configure(family=family, size=10)
        self._title_font = (family, 16, "bold")

        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(8, weight=1)

        ttk.Label(outer, text="AutomataPlayer", font=self._title_font).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        language_box = ttk.Frame(outer)
        language_box.grid(row=0, column=2, sticky="e")
        self.language_caption = ttk.Label(language_box, text=t("language"))
        self.language_caption.grid(row=0, column=0, padx=(0, 8))
        self.language_var = tk.StringVar(value=language_label(get_language()))
        self.language_combo = ttk.Combobox(
            language_box,
            textvariable=self.language_var,
            state="readonly",
            width=10,
            values=tuple(LANGUAGE_LABELS[code] for code in LANGUAGES),
        )
        self.language_combo.grid(row=0, column=1)
        self.language_combo.bind("<<ComboboxSelected>>", self._change_language)
        self.subtitle_label = ttk.Label(outer, text=t("subtitle"), justify="left", anchor="w")
        self.subtitle_label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        self.score_caption = ttk.Label(outer, text=t("score"))
        self.score_caption.grid(row=2, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(outer, textvariable=self.path_var)
        entry.grid(row=2, column=1, sticky="ew")
        entry.bind("<Return>", self._on_path_commit)
        entry.bind("<FocusOut>", self._on_path_commit)
        self.browse_button = ttk.Button(outer, text=t("browse"), command=self.browse)
        self.browse_button.grid(row=2, column=2, padx=(8, 0))

        self.summary_label = ttk.Label(outer, textvariable=self.summary_var, justify="left", anchor="w")
        self.summary_label.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 8))

        self.instrument_caption = ttk.Label(outer, text=t("instrument"))
        self.instrument_caption.grid(row=4, column=0, sticky="nw", padx=(0, 8))
        instrument_box = ttk.Frame(outer)
        instrument_box.grid(row=4, column=1, columnspan=2, sticky="ew")
        instrument_box.columnconfigure(0, weight=1)
        self.instrument_combo = ttk.Combobox(
            instrument_box,
            textvariable=self.instrument_var,
            state="readonly",
            values=tuple(self._instrument_label(item) for item in self._instruments),
        )
        self.instrument_combo.grid(row=0, column=0, sticky="ew")
        self.instrument_combo.bind("<<ComboboxSelected>>", self._on_instrument)
        self.detail_label = ttk.Label(instrument_box, textvariable=self.detail_var, justify="left", anchor="w")
        self.detail_label.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        options = ttk.Frame(outer)
        options.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        self.run_caption = ttk.Label(options, text=t("run"))
        self.run_caption.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.preview_radio = ttk.Radiobutton(options, text=t("preview"), value="preview", variable=self.mode_var)
        self.preview_radio.grid(row=0, column=1, sticky="w")
        self._live_key = "live" if sys.platform == "win32" else "live_pynput"
        self.live_radio = ttk.Radiobutton(options, text=t(self._live_key), value="live", variable=self.mode_var)
        self.live_radio.grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.realtime_check = ttk.Checkbutton(
            options, text=t("realtime"), variable=self.realtime_var
        )
        self.realtime_check.grid(row=0, column=3, sticky="w", padx=(12, 0))

        numbers = ttk.Frame(options)
        numbers.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._number_field(numbers, 0, "speed", self.speed_var, 0.25, 3, 0.05)
        self._number_field(numbers, 1, "transpose", self.transpose_var, -24, 24, 1)
        self.countdown_spin = self._number_field(numbers, 2, "countdown", self.countdown_var, 0, 15, 1)
        self.mode_var.trace_add("write", self._sync_mode)
        self._sync_mode()
        self.part_caption = ttk.Label(numbers, text=t("part"))
        self.part_caption.grid(row=0, column=6, sticky="w", padx=(16, 8))
        self.part_combo = ttk.Combobox(
            numbers, textvariable=self.part_var, state="readonly", width=18, values=(t("all_parts"),)
        )
        self.part_combo.grid(row=0, column=7, sticky="w")

        self.warning_label = ttk.Label(
            outer,
            textvariable=self.warning_var,
            style="Warn.TLabel",
            justify="left",
            anchor="w",
        )
        self.warning_label.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        self.play_button = ttk.Button(buttons, text=t("play"), command=self.start_play)
        self.play_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ttk.Button(buttons, text=t("stop"), command=self.stop_play, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 12))
        self.apply_transpose = ttk.Button(
            buttons, text=t("apply"), command=self.apply_suggestion, state="disabled"
        )
        self.apply_transpose.grid(row=0, column=2, sticky="w", padx=(0, 12))
        ttk.Label(buttons, textvariable=self.status_var).grid(row=0, column=3, sticky="w")

        log_frame = ttk.Frame(outer)
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=12, wrap="word", font=(family, 10))
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.outer = outer
        self.instrument_box = instrument_box
        outer.bind("<Configure>", self._fit_text)
        instrument_box.bind("<Configure>", self._fit_text)
        self.root.after_idle(self._fit_text)

    def _number_field(
        self,
        parent: ttk.Frame,
        column: int,
        key: str,
        variable: tk.StringVar,
        low: float,
        high: float,
        step: float,
    ) -> ttk.Spinbox:
        label = ttk.Label(parent, text=t(key))
        label.grid(row=0, column=column * 2, sticky="w", padx=(0 if column == 0 else 16, 8))
        self._i18n.append((label, key))
        spin = ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=low,
            to=high,
            increment=step,
            width=6,
        )
        spin.grid(row=0, column=column * 2 + 1, sticky="w")
        return spin

    def _sync_mode(self, *_args: object) -> None:
        live = self.mode_var.get() == "live"
        if live:
            self.realtime_check.state(["disabled"])
            self.countdown_spin.state(["!disabled"])
        else:
            self.realtime_check.state(["!disabled"])
            self.countdown_spin.state(["disabled"])

    def browse(self) -> None:
        current = self.path_var.get().strip()
        initial = str(Path(current).parent) if current else str(Path.cwd())
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=t("browse_title"),
            initialdir=initial,
            filetypes=(
                ("MuseScore", "*.mscz *.mscx"),
                (t("all_files"), "*.*"),
            ),
        )
        if selected:
            self.load_path(selected)

    def load_path(self, path: str) -> None:
        cleaned = path.strip()
        self.path_var.set(cleaned)
        if not cleaned:
            self.summary_var.set(t("choose_score"))
            self._set_parts(())
            self._loaded_path = ""
            self._score = None
            self._refresh_playability()
            return
        try:
            score = load_score(cleaned)
        except AutomataError as exc:
            self.summary_var.set(t("error", message=exc))
            self._set_parts(())
            self._loaded_path = ""
            self._score = None
            self._refresh_playability()
            return
        self._loaded_path = str(Path(cleaned))
        self._score = score
        self.summary_var.set(format_score(score))
        self._set_parts(tuple(f"{part.index + 1}. {part.name}" for part in score.parts))
        self._refresh_playability()

    def start_play(self) -> None:
        if self.session.running():
            return
        path = self.path_var.get().strip()
        if not path:
            self._append(t("choose_score"))
            return
        try:
            speed = float(self.speed_var.get())
            transpose = int(float(self.transpose_var.get()))
            countdown = float(self.countdown_var.get())
        except ValueError:
            self._append(t("bad_number"))
            return
        if speed <= 0:
            self._append(t("bad_speed"))
            return
        self._refresh_playability()
        if self._blocked:
            self._append(self.warning_var.get())
            return

        preview = self.mode_var.get() != "live"
        request = PlayRequest(
            path=path,
            instrument_id=self._instrument_id(),
            backend="dry-run" if preview else live_backend_name(),
            speed=speed,
            transpose=transpose,
            countdown=0.0 if preview else max(0.0, countdown),
            parts=self._selected_parts(),
            immediate=preview and not self.realtime_var.get(),
        )
        self.play_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self._set_status("playing")
        if not preview:
            self._minimized_for_play = True
            self.root.iconify()
        try:
            self.session.start(
                request,
                lambda text: self._queue.put(("log", text)),
                lambda _stopped: self._queue.put(("done", None)),
            )
        except AutomataError as exc:
            self._append(t("error", message=exc))
            self._set_idle()

    def apply_suggestion(self) -> None:
        if self._suggestion is None:
            return
        self.transpose_var.set(str(self._suggestion))

    def stop_play(self) -> None:
        self.session.stop()
        self._set_status("stopping")

    def close(self) -> None:
        self._closed = True
        self.session.stop()
        thread = self.session.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.root.destroy()

    def drain(self) -> None:
        if self._closed:
            return
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._append(str(payload))
                elif kind == "done":
                    self._set_idle()
                    if self._minimized_for_play:
                        self._minimized_for_play = False
                        self.root.deiconify()
        except queue.Empty:
            pass
        if not self._closed:
            self._after_id = self.root.after(50, self.drain)

    def _on_path_commit(self, _event: object = None) -> None:
        path = self.path_var.get().strip()
        if path and path != self._loaded_path:
            self.load_path(path)

    def _on_instrument(self, _event: object = None) -> None:
        label = self.instrument_var.get()
        for index, instrument in enumerate(self._instruments):
            if label == self._instrument_label(instrument):
                self._select_instrument(index)
                return

    def _select_instrument(self, index: int) -> None:
        instrument = self._instruments[index]
        self.instrument_var.set(self._instrument_label(instrument))
        state = t("verified") if instrument.verified else t("unverified")
        touch = t("touch_hold") if instrument.sustains else t("touch_tap")
        sentences = instrument_detail(instrument).replace(". ", ".\n")
        self.detail_var.set(
            t(
                "detail_line",
                range=instrument.range_label,
                count=len(instrument.keys),
                touch=touch,
                state=state,
            )
            + "\n"
            + sentences
        )
        self._refresh_playability()

    def _instrument_id(self) -> str:
        label = self.instrument_var.get()
        for instrument in self._instruments:
            if label == self._instrument_label(instrument) or label == instrument.id:
                return instrument.id
        return label

    def _instrument_label(self, instrument: Instrument) -> str:
        return f"{instrument_name(instrument)} ({instrument.id})"

    def _selected_parts(self) -> tuple[str, ...]:
        value = self.part_var.get().strip()
        if not value or value == t("all_parts"):
            return ()
        number, dot, _name = value.partition(".")
        if dot and number.strip().isdigit():
            return (number.strip(),)
        return (value,)

    def _fit_text(self, event: tk.Event | None = None) -> None:
        """설명 글의 줄바꿈을 지금 창 너비에 맞춘다."""
        if event is not None and event.widget not in {self.outer, self.instrument_box}:
            return
        outer_width = self.outer.winfo_width()
        if outer_width <= 160:
            return
        self.summary_label.configure(wraplength=outer_width)
        self.subtitle_label.configure(wraplength=outer_width)
        self.warning_label.configure(wraplength=outer_width)
        gutter = self.instrument_caption.winfo_width() + 24
        self.detail_label.configure(wraplength=max(200, outer_width - gutter))

    def _refresh_playability(self) -> None:
        if not hasattr(self, "play_button"):
            return
        if self._score is None:
            self._blocked = False
            self._suggestion = None
            self.warning_var.set("")
            self.apply_transpose.state(["disabled"])
            if not self.session.running():
                self.play_button.state(["!disabled"])
            return
        try:
            transpose = int(float(self.transpose_var.get()))
        except ValueError:
            return
        try:
            score = self._score.select_parts(list(self._selected_parts()))
            instrument = get_instrument(self._instrument_id())
        except AutomataError:
            return
        check = assess(score.notes, instrument, transpose)
        if check.ok:
            self._blocked = False
            self._suggestion = None
            self.warning_var.set("")
            self.apply_transpose.state(["disabled"])
            if not self.session.running():
                self.play_button.state(["!disabled"])
            return
        self._blocked = True
        self._suggestion = check.suggestion
        self.warning_var.set(check.notice)
        if not self.session.running():
            self.play_button.state(["disabled"])
        if check.suggestion is None:
            self.apply_transpose.state(["disabled"])
        else:
            self.apply_transpose.state(["!disabled"])

    def _set_parts(self, names: tuple[str, ...]) -> None:
        values = (t("all_parts"), *names)
        self.part_combo["values"] = values
        self.part_var.set(t("all_parts"))

    def _append(self, text: str) -> None:
        self._log_is_intro = False
        self.log_text.insert("end", text + "\n")
        line_count = int(self.log_text.index("end-1c").split(".", 1)[0])
        if line_count > 2000:
            self.log_text.delete("1.0", f"{line_count - 2000}.0")
        self.log_text.see("end")

    def _set_idle(self) -> None:
        self.play_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        if self.session.running():
            return
        if self._status_key == "stopping":
            self._set_status("stopped")
        else:
            self._set_status("ready")

    def _set_status(self, key: str) -> None:
        self._status_key = key
        self.status_var.set(t(key))

    def _change_language(self, _event: object = None) -> None:
        instrument_id = self._instrument_id()
        selected = self.part_var.get()
        keep_part = None if selected == t("all_parts") else selected
        set_language(language_code(self.language_var.get()))
        save_language()
        self._apply_language(instrument_id, keep_part)

    def _apply_language(self, instrument_id: str | None = None, selected_part: str | None = None) -> None:
        if instrument_id is None:
            instrument_id = self._instrument_id()
        self.language_var.set(language_label(get_language()))
        self.language_caption.configure(text=t("language"))
        self.subtitle_label.configure(text=t("subtitle"))
        self.score_caption.configure(text=t("score"))
        self.browse_button.configure(text=t("browse"))
        self.instrument_caption.configure(text=t("instrument"))
        self.run_caption.configure(text=t("run"))
        self.preview_radio.configure(text=t("preview"))
        self.live_radio.configure(text=t(self._live_key))
        self.realtime_check.configure(text=t("realtime"))
        for widget, key in self._i18n:
            widget.configure(text=t(key))
        self.part_caption.configure(text=t("part"))
        self.play_button.configure(text=t("play"))
        self.stop_button.configure(text=t("stop"))
        self.apply_transpose.configure(text=t("apply"))
        self.status_var.set(t(self._status_key))

        if self._score is None and self.path_var.get().strip():
            self.load_path(self.path_var.get())
        names: tuple[str, ...] = ()
        if self._score is not None:
            names = tuple(f"{part.index + 1}. {part.name}" for part in self._score.parts)
            self.summary_var.set(format_score(self._score))
        elif not self.path_var.get().strip():
            self.summary_var.set(t("choose_score"))
        values = (t("all_parts"), *names)
        self.part_combo["values"] = values
        if selected_part and selected_part in values:
            self.part_var.set(selected_part)
        else:
            self.part_var.set(t("all_parts"))

        self.instrument_combo["values"] = tuple(
            self._instrument_label(item) for item in self._instruments
        )
        chosen = 0
        for index, instrument in enumerate(self._instruments):
            if instrument.id == instrument_id or instrument_id in instrument.aliases:
                chosen = index
                break
        self._select_instrument(chosen)
        if self._log_is_intro:
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", t("help") + "\n")
        self._fit_text()
