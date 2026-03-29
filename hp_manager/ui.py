from __future__ import annotations

import ctypes
import math
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from hp_manager.initiative import InitiativeTrackerWindow
from hp_manager.localization import Localizer, SUPPORTED_LOCALES
from hp_manager.models import AppState, Player, SPELL_SLOT_LEVELS
from hp_manager.paths import asset_path
from hp_manager.storage import load_state, save_state
from hp_manager.sync import ParseIssue, ParsedSyncData, SyncFetchError, fetch_google_doc_text, parse_sync_text


WINDOW_MIN_WIDTH = 1060
WINDOW_MIN_HEIGHT = 560
OVERLAY_SIZE = 220
TRANSPARENT_KEY = "#00ff00"
ICON_PATH = asset_path("app.ico")
OVERLAY_TITLE_HEIGHT = 30
WINDOWS_APP_ID = "LostPersona.HPManager"
SPELL_SLOT_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX"}
FONT_SIZE_OPTIONS = tuple(str(size) for size in range(12, 73, 2))
SPELL_CELL_SCALE_OPTIONS = ("80%", "100%", "120%", "140%", "160%", "180%", "200%")
COIN_COLORS = {
    "cc": ("#c98d6b", "#f8d3bb", "#774a35"),
    "sc": ("#c4cad0", "#eff2f6", "#69727b"),
    "gc": ("#f0bc25", "#fff4b3", "#8d6500"),
}
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1


def _hp_text_color(ratio: float) -> str:
    if ratio <= 0.25:
        return "#ff6b6b"
    if ratio <= 0.5:
        return "#ffc857"
    return "#74f28b"


def _hp_bar_color(ratio: float) -> str:
    if ratio <= 0.25:
        return "#d7263d"
    if ratio <= 0.5:
        return "#f2a900"
    return "#3ddc84"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        return


class PlayerWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        self.window.title("")
        self.window.geometry("360x170")
        self.window.minsize(320, 150)
        self.app.apply_topmost(self.window, self.app.state.overlay.player_windows_topmost)
        self.window.configure(bg="#171717")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_window_icon(self.window)

        self.name_label = tk.Label(self.window, bg="#171717", fg="#f2f2f2", font=("Segoe UI Semibold", 18), anchor="w")
        self.name_label.pack(fill="x", padx=18, pady=(18, 6))

        self.hp_label = tk.Label(self.window, bg="#171717", fg="#74f28b", font=("Consolas", 34, "bold"), anchor="center")
        self.hp_label.pack(fill="x", padx=18)

        self.temp_label = tk.Label(self.window, bg="#171717", fg="#b6d7ff", font=("Segoe UI", 12))
        self.temp_label.pack(fill="x", padx=18, pady=(6, 12))

        self.bar_canvas = tk.Canvas(self.window, height=22, bg="#252525", highlightthickness=0)
        self.bar_canvas.pack(fill="x", padx=18, pady=(0, 18))
        self.bar_id = self.bar_canvas.create_rectangle(0, 0, 0, 22, fill="#4ce06d", width=0)
        self.window.bind("<Configure>", self._refresh_bar)
        self.refresh(player)

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_player_window(self.player_id)

    def refresh(self, player: Player) -> None:
        self.window.title(self.app.t("player.window_title", name=player.name))
        self.name_label.config(text=player.name)
        self.hp_label.config(
            text=f"{player.current_hp} / {player.max_hp}",
            fg=_hp_text_color(player.hp_ratio),
            font=("Consolas", self.app.state.overlay.hp_font_size, "bold"),
        )
        self.temp_label.config(
            text=self.app.t("player.temp_hp", temp_hp=player.temp_hp),
            font=("Segoe UI", self.app.state.overlay.temp_hp_font_size),
        )
        self._refresh_bar(player=player)

    def _refresh_bar(self, _event: object | None = None, player: Player | None = None) -> None:
        current_player = player or self.app.player_by_id(self.player_id)
        if current_player is None:
            return
        width = max(1, self.bar_canvas.winfo_width())
        fill_width = int(width * current_player.hp_ratio)
        self.bar_canvas.coords(self.bar_id, 0, 0, fill_width, 22)
        self.bar_canvas.itemconfig(self.bar_id, fill=_hp_bar_color(current_player.hp_ratio))


class OverlayWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        width, height = self.app.overlay_dimensions(OVERLAY_SIZE)
        self.window.geometry(f"{width}x{height}+100+100")
        self.window.title(self.app.t("overlay.window_title", name=player.name))
        self.window.minsize(60, 60)
        self.app.apply_topmost(self.window, self.app.state.overlay.fill_windows_topmost)
        self.window.attributes("-alpha", 0.45)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_window_icon(self.window)

        try:
            self.window.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.window, bg=TRANSPARENT_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.fill_id = self.canvas.create_rectangle(0, height, width, height, fill="#ff2b2b", width=0)
        self.border_id = self.canvas.create_rectangle(2, 2, width - 2, height - 2, outline="#ff6b6b", width=2)
        self.title_id = self.canvas.create_text(
            width // 2,
            OVERLAY_TITLE_HEIGHT // 2,
            text=player.name,
            fill="#ffe2e2",
            font=("Segoe UI Semibold", 12),
        )

        self.window.bind("<MouseWheel>", self._resize_from_wheel)
        self.window.bind("<Key-plus>", lambda _event: self._resize(20))
        self.window.bind("<Key-minus>", lambda _event: self._resize(-20))
        self.window.bind("<Double-Button-1>", lambda _event: self.close())
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Configure>", self._on_resize)
        self.refresh(player)

    def _on_resize(self, _event: object | None = None) -> None:
        player = self.app.player_by_id(self.player_id)
        if player:
            self.refresh(player)

    def _resize_from_wheel(self, event: tk.Event) -> None:
        self._resize(20 if event.delta > 0 else -20)

    def _resize(self, delta: int) -> None:
        base = max(60, min(600, self.app.overlay_base_from_size(self.window.winfo_width(), self.window.winfo_height()) + delta))
        width, height = self.app.overlay_dimensions(base)
        self.window.geometry(f"{width}x{height}+{self.window.winfo_x()}+{self.window.winfo_y()}")

    def refresh(self, player: Player) -> None:
        self.window.title(self.app.t("overlay.window_title", name=player.name))
        width = max(40, self.canvas.winfo_width())
        height = max(40, self.canvas.winfo_height())
        title_space = OVERLAY_TITLE_HEIGHT if self.app.state.overlay.show_title else 0
        overlay_top = title_space
        overlay_height = max(20, height - title_space)
        missing_height = int(overlay_height * player.missing_ratio)
        self.canvas.coords(self.fill_id, 0, overlay_top + overlay_height - missing_height, width, overlay_top + overlay_height)
        self.canvas.coords(self.border_id, 2, overlay_top + 2, width - 2, overlay_top + overlay_height - 2)
        self.canvas.coords(self.title_id, width // 2, OVERLAY_TITLE_HEIGHT // 2)
        self.canvas.itemconfig(self.title_id, text=player.name, state="normal" if self.app.state.overlay.show_title else "hidden")

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_overlay_window(self.player_id)


class MoneyWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        self.window.geometry("420x180")
        self.window.minsize(320, 140)
        self.window.configure(bg="#141414")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_topmost(self.window, self.app.state.overlay.player_windows_topmost)
        self.app.apply_window_icon(self.window)

        self.title_label = tk.Label(self.window, bg="#141414", fg="#f2f2f2", font=("Segoe UI Semibold", 18))
        self.title_label.pack(pady=(18, 12))

        grid = tk.Frame(self.window, bg="#141414")
        grid.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.grid = grid
        self.icon_widgets: dict[str, tk.Widget] = {}
        self.value_labels: dict[str, tk.Label] = {}
        self.abbr_labels: dict[str, tk.Label] = {}

        for key in ("cc", "sc", "gc"):
            icon_widget = self.app.create_coin_widget(grid, key=key, size=42, background="#141414")
            value = tk.Label(grid, bg="#1b1b1b", fg="#f6e8a5", font=("Consolas", 24, "bold"), bd=1, relief="solid", anchor="w")
            name = tk.Label(grid, bg="#141414", fg="#d2d2d2", font=("Segoe UI Semibold", 11))
            self.icon_widgets[key] = icon_widget
            self.value_labels[key] = value
            self.abbr_labels[key] = name

        self._apply_layout()

        self.refresh(player)

    def _apply_layout(self) -> None:
        inline = self.app.state.overlay.money_layout == "inline"
        coin_order = self.app.money_coin_keys()
        for widget in [*self.icon_widgets.values(), *self.value_labels.values(), *self.abbr_labels.values()]:
            widget.grid_forget()

        if inline:
            for column in range(9):
                self.grid.columnconfigure(column, weight=0)
            self.grid.columnconfigure(1, weight=1)
            self.grid.columnconfigure(4, weight=1)
            self.grid.columnconfigure(7, weight=1)
            for idx, key in enumerate(coin_order):
                base_col = idx * 3
                self.icon_widgets[key].grid(row=0, column=base_col, sticky="w", padx=(0 if idx == 0 else 12, 8), pady=6)
                self.value_labels[key].grid(row=0, column=base_col + 1, sticky="ew", pady=6, ipadx=10, ipady=8)
                self.abbr_labels[key].grid(row=0, column=base_col + 2, sticky="w", padx=(8, 0), pady=6)
            self.window.minsize(560, 120)
            self.window.geometry(f"640x140+{self.window.winfo_x()}+{self.window.winfo_y()}")
        else:
            for column in range(3):
                self.grid.columnconfigure(column, weight=0)
            self.grid.columnconfigure(1, weight=1)
            for row, key in enumerate(coin_order):
                self.icon_widgets[key].grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
                self.value_labels[key].grid(row=row, column=1, sticky="ew", pady=6, ipadx=14, ipady=8)
                self.abbr_labels[key].grid(row=row, column=2, sticky="w", padx=(12, 0), pady=6)
            self.window.minsize(320, 140)
            self.window.geometry(f"420x180+{self.window.winfo_x()}+{self.window.winfo_y()}")

    def refresh(self, player: Player) -> None:
        self._apply_layout()
        self.window.title(self.app.t("money.window_title", name=player.name))
        self.title_label.config(text=self.app.t("money.window_title", name=player.name))
        money = player.money
        self.value_labels["cc"].config(text=str(money.cc))
        self.value_labels["sc"].config(text=str(money.sc))
        self.value_labels["gc"].config(text=str(money.gc))
        self.abbr_labels["cc"].config(text=self.app.t("money.cc"))
        self.abbr_labels["sc"].config(text=self.app.t("money.sc"))
        self.abbr_labels["gc"].config(text=self.app.t("money.gc"))
        for label in self.value_labels.values():
            label.config(font=("Consolas", self.app.state.overlay.money_font_size, "bold"))
        for key in ("cc", "sc", "gc"):
            self.app.refresh_coin_widget(self.icon_widgets[key], key=key, size=42, background="#141414")

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_money_window(self.player_id)


class MoneyEditorWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        self.window.geometry("360x220")
        self.window.minsize(320, 200)
        self.window.configure(bg="#101214")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_window_icon(self.window)

        self.title_label = ttk.Label(self.window, style="Header.TLabel")
        self.title_label.pack(anchor="w", padx=16, pady=(16, 12))

        content = ttk.Frame(self.window, padding=(16, 0, 16, 16))
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        self.content = content
        self.icon_widgets: dict[str, tk.Widget] = {}
        self.money_labels: dict[str, ttk.Label] = {}
        self.money_vars: dict[str, tk.StringVar] = {}
        self.money_entries: dict[str, ttk.Entry] = {}
        for key in ("cc", "sc", "gc"):
            icon_widget = self.app.create_coin_widget(content, key=key, size=32, background="#101214")
            label = ttk.Label(content)
            var = tk.StringVar()
            entry = ttk.Entry(content, textvariable=var, width=10)
            self.icon_widgets[key] = icon_widget
            self.money_labels[key] = label
            self.money_vars[key] = var
            self.money_entries[key] = entry

        button_row = ttk.Frame(content)
        button_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        self.save_button = ttk.Button(button_row, command=self.save)
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.close_button = ttk.Button(button_row, command=self.close)
        self.close_button.grid(row=0, column=1, sticky="ew")

        self._apply_layout()
        self.refresh(player)

    def _apply_layout(self) -> None:
        coin_order = self.app.money_coin_keys()
        self.content.columnconfigure(1, weight=0)
        self.content.columnconfigure(2, weight=1)
        for widget in [*self.icon_widgets.values(), *self.money_labels.values(), *self.money_entries.values()]:
            widget.grid_forget()
        for row, key in enumerate(coin_order):
            self.icon_widgets[key].grid(row=row, column=0, sticky="w", pady=6)
            self.money_labels[key].grid(row=row, column=1, sticky="w", padx=(10, 8), pady=6)
            self.money_entries[key].grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=6)

    def refresh(self, player: Player) -> None:
        self._apply_layout()
        self.window.title(self.app.t("money.editor_title", name=player.name))
        self.title_label.config(text=self.app.t("money.editor_title", name=player.name))
        self.money_labels["cc"].config(text=self.app.t("money.cc"))
        self.money_labels["sc"].config(text=self.app.t("money.sc"))
        self.money_labels["gc"].config(text=self.app.t("money.gc"))
        self.money_vars["cc"].set(str(player.money.cc))
        self.money_vars["sc"].set(str(player.money.sc))
        self.money_vars["gc"].set(str(player.money.gc))
        self.save_button.config(text=self.app.t("action.apply"))
        self.close_button.config(text=self.app.t("action.close"))
        for key in ("cc", "sc", "gc"):
            self.app.refresh_coin_widget(self.icon_widgets[key], key=key, size=32, background="#101214")

    def save(self) -> None:
        player = self.app.player_by_id(self.player_id)
        if player is None:
            self.close()
            return
        player.set_money(self.money_vars["cc"].get(), self.money_vars["sc"].get(), self.money_vars["gc"].get())
        self.app.persist_and_refresh(status=self.app.t("status.money_saved", name=player.name))

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_money_editor(self.player_id)


class SpellSlotsWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        self.window.geometry("840x260")
        self.window.minsize(420, 220)
        self.window.configure(bg="#090909")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_topmost(self.window, self.app.state.overlay.player_windows_topmost)
        self.app.apply_window_icon(self.window)

        self.title_label = tk.Label(self.window, bg="#090909", fg="#f0f0f0", font=("Segoe UI Semibold", 18))
        self.title_label.pack(anchor="w", padx=16, pady=(16, 10))

        board = tk.Frame(self.window, bg="#090909")
        board.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.board = board
        self.slot_titles: dict[int, tk.Label] = {}
        self.slot_cells: dict[int, tk.Frame] = {}
        self.slot_values: dict[int, tk.Label] = {}
        self.slot_pip_frames: dict[int, tk.Frame] = {}
        self.slot_pips: dict[int, list[tk.Canvas]] = {}

        for column, level in enumerate(SPELL_SLOT_LEVELS):
            board.columnconfigure(column, weight=1)
            title = tk.Label(
                board,
                bg="#0d0d0d",
                fg="#f4f4f4",
                font=("Segoe UI Semibold", 32),
                bd=2,
                relief="solid",
                highlightthickness=0,
            )
            title.grid(row=0, column=column, sticky="nsew", padx=4, pady=(0, 4), ipadx=8, ipady=20)
            cell = tk.Frame(
                board,
                bg="#040404",
                bd=2,
                relief="solid",
                highlightthickness=0,
            )
            cell.grid(row=1, column=column, sticky="nsew", padx=4, pady=(4, 0), ipadx=8, ipady=28)
            value = tk.Label(
                cell,
                bg="#040404",
                fg="#f3d28b",
                font=("Consolas", 24, "bold"),
                highlightthickness=0,
            )
            value.pack(expand=True, fill="both")
            pip_frame = tk.Frame(cell, bg="#040404")
            pips: list[tk.Canvas] = []
            for idx in range(4):
                pip = tk.Canvas(pip_frame, width=18, height=18, bg="#040404", bd=0, highlightthickness=0)
                pip.grid(row=idx // 2, column=idx % 2, padx=4, pady=4)
                pips.append(pip)
            self.slot_titles[level] = title
            self.slot_cells[level] = cell
            self.slot_values[level] = value
            self.slot_pip_frames[level] = pip_frame
            self.slot_pips[level] = pips

        self.refresh(player)

    def _apply_layout(self) -> None:
        visible_levels = self.app.visible_spell_levels()
        render_mode = self.app.state.overlay.spell_render_mode
        scale = (
            self.app.state.overlay.spell_cell_scale / 100
            if render_mode == "text"
            else self.app.state.overlay.spell_pip_scale / 100
        )
        title_padx = max(3, int(round(4 * scale)))
        title_pady = max(3, int(round(4 * scale)))
        title_ipadx = max(6, int(round(8 * scale)))
        title_ipady = max(10, int(round((10 + self.app.state.overlay.spell_level_font_size * 0.45) * scale)))
        value_padx = max(3, int(round(4 * scale)))
        value_pady = max(3, int(round(4 * scale)))
        value_ipadx = max(6, int(round(8 * scale)))
        value_ipady = max(12, int(round((12 + self.app.state.overlay.spell_font_size * 0.6) * scale))) if render_mode == "text" else max(10, int(round(12 * scale)))

        for column, level in enumerate(SPELL_SLOT_LEVELS):
            weight = 1 if level in visible_levels else 0
            self.board.columnconfigure(column, weight=weight)
            self.slot_titles[level].grid_forget()
            self.slot_cells[level].grid_forget()

        for column, level in enumerate(visible_levels):
            self.slot_titles[level].grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=title_padx,
                pady=(0, title_pady),
                ipadx=title_ipadx,
                ipady=title_ipady,
            )
            self.slot_cells[level].grid(
                row=1,
                column=column,
                sticky="nsew",
                padx=value_padx,
                pady=(value_pady, 0),
                ipadx=value_ipadx,
                ipady=value_ipady,
            )

        visible_count = len(visible_levels)
        if render_mode == "text":
            cell_width = max(
                96,
                int(round((self.app.state.overlay.spell_level_font_size * 1.8 + 18) * scale)),
                int(round((self.app.state.overlay.spell_font_size * 4.4 + 22) * scale)),
            )
            min_height = max(
                220,
                int(
                    round(
                        120
                        + (self.app.state.overlay.spell_level_font_size + self.app.state.overlay.spell_font_size)
                        * 2.2
                        * scale
                    )
                ),
            )
        else:
            pip_size = max(10, int(round(18 * scale)))
            cell_width = max(
                86,
                int(round((self.app.state.overlay.spell_level_font_size * 1.5 + 12) * scale)),
                int(round(pip_size * 2.8)),
            )
            min_height = max(
                210,
                int(round(120 + self.app.state.overlay.spell_level_font_size * 1.7 * scale + pip_size * 2.8)),
            )
        min_width = max(420, 24 + visible_count * cell_width)
        default_width = max(520, 32 + visible_count * int(cell_width * 1.12))
        default_height = max(min_height, int(round(min_height * 1.08)))
        self.window.minsize(min_width, min_height)
        current_width = self.window.winfo_width()
        current_height = self.window.winfo_height()
        if current_width < min_width or current_height < min_height:
            self.window.geometry(f"{default_width}x{default_height}+{self.window.winfo_x()}+{self.window.winfo_y()}")
        self.visible_levels = visible_levels

    def refresh(self, player: Player) -> None:
        self._apply_layout()
        self.window.title(self.app.t("spell.window_title", name=player.name))
        self.title_label.config(text=self.app.t("spell.window_title", name=player.name))
        render_mode = self.app.state.overlay.spell_render_mode
        pip_scale = self.app.state.overlay.spell_pip_scale / 100
        pip_size = max(10, int(round(18 * pip_scale)))
        for level in self.visible_levels:
            slot = player.spell_slots[level]
            self.slot_titles[level].config(
                text=SPELL_SLOT_ROMAN[level],
                bd=2,
                relief="solid",
                highlightbackground="#9d6b2f",
                font=("Segoe UI Semibold", self.app.state.overlay.spell_level_font_size),
            )
            self.slot_cells[level].config(highlightbackground="#9d6b2f")
            if render_mode == "text":
                self.slot_pip_frames[level].pack_forget()
                self.slot_values[level].config(
                    text=f"{slot.current} / {slot.maximum}",
                    font=("Consolas", self.app.state.overlay.spell_font_size, "bold"),
                )
                self.slot_values[level].pack(expand=True, fill="both")
            else:
                self.slot_values[level].pack_forget()
                self.slot_pip_frames[level].pack(expand=True)
                max_slots = max(0, min(4, slot.maximum))
                current_slots = max(0, min(max_slots, slot.current))
                for idx, pip in enumerate(self.slot_pips[level]):
                    pip.delete("all")
                    if idx >= max_slots:
                        pip.grid_remove()
                        continue
                    pip.grid()
                    pip.config(width=pip_size, height=pip_size)
                    fill = "#53f4ff" if idx < current_slots else "#223841"
                    outline = "#abfbff" if idx < current_slots else "#4b646d"
                    inset = max(2, pip_size // 8)
                    pip.create_rectangle(
                        inset,
                        inset,
                        pip_size - inset,
                        pip_size - inset,
                        fill=fill,
                        outline=outline,
                        width=2,
                    )

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_spell_window(self.player_id)


class SpellSlotsEditorWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        self.window.geometry("400x460")
        self.window.minsize(360, 420)
        self.window.configure(bg="#101214")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_window_icon(self.window)

        self.title_label = ttk.Label(self.window, style="Header.TLabel")
        self.title_label.pack(anchor="w", padx=16, pady=(16, 12))

        content = ttk.Frame(self.window, padding=(16, 0, 16, 16))
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)
        content.columnconfigure(2, weight=1)

        self.current_header = ttk.Label(content, style="Muted.TLabel")
        self.current_header.grid(row=0, column=1, sticky="w", padx=(12, 8))
        self.max_header = ttk.Label(content, style="Muted.TLabel")
        self.max_header.grid(row=0, column=2, sticky="w")

        self.level_vars: dict[int, tuple[tk.StringVar, tk.StringVar]] = {}
        self.level_labels: dict[int, ttk.Label] = {}
        for row, level in enumerate(SPELL_SLOT_LEVELS, start=1):
            level_label = ttk.Label(content)
            level_label.grid(row=row, column=0, sticky="w", pady=4)
            current_var = tk.StringVar()
            max_var = tk.StringVar()
            ttk.Entry(content, textvariable=current_var, width=8).grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=4)
            ttk.Entry(content, textvariable=max_var, width=8).grid(row=row, column=2, sticky="ew", pady=4)
            self.level_labels[level] = level_label
            self.level_vars[level] = (current_var, max_var)

        button_row = ttk.Frame(content)
        button_row.grid(row=len(SPELL_SLOT_LEVELS) + 1, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        self.save_button = ttk.Button(button_row, command=self.save)
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.close_button = ttk.Button(button_row, command=self.close)
        self.close_button.grid(row=0, column=1, sticky="ew")

        self.refresh(player)

    def refresh(self, player: Player) -> None:
        self.window.title(self.app.t("spell.editor_title", name=player.name))
        self.title_label.config(text=self.app.t("spell.editor_title", name=player.name))
        self.current_header.config(text=self.app.t("label.current"))
        self.max_header.config(text=self.app.t("label.max"))
        self.save_button.config(text=self.app.t("action.apply"))
        self.close_button.config(text=self.app.t("action.close"))
        for level in SPELL_SLOT_LEVELS:
            slot = player.spell_slots[level]
            current_var, max_var = self.level_vars[level]
            current_var.set(str(slot.current))
            max_var.set(str(slot.maximum))
            self.level_labels[level].config(text=self.app.t("spell.level_label", level=SPELL_SLOT_ROMAN[level]))

    def save(self) -> None:
        player = self.app.player_by_id(self.player_id)
        if player is None:
            self.close()
            return
        for level in SPELL_SLOT_LEVELS:
            current_var, max_var = self.level_vars[level]
            player.set_spell_slot(level, current_var.get(), max_var.get())
        self.app.persist_and_refresh(status=self.app.t("status.spell_slots_saved", name=player.name))

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_spell_editor(self.player_id)


class PlayerRow:
    def __init__(self, app: "HealthPointsApp", parent: ttk.Frame, player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.frame = ttk.Frame(parent, padding=(10, 10), style="Card.TFrame")
        self.frame.columnconfigure(0, weight=1)

        self.name_var = tk.StringVar(value=player.name)
        self.current_var = tk.StringVar(value=str(player.current_hp))
        self.max_var = tk.StringVar(value=str(player.max_hp))
        self.temp_var = tk.StringVar(value=str(player.temp_hp))
        self.delta_var = tk.StringVar(value="1")

        self.header_frame = ttk.Frame(self.frame, style="Card.TFrame")
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.columnconfigure(1, weight=1)
        self.header_frame.columnconfigure(2, weight=0)
        self.name_label = ttk.Label(self.header_frame, style="Muted.TLabel")
        self.name_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.name_entry = ttk.Entry(self.header_frame, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky="ew")
        self.name_value_label = ttk.Label(self.header_frame)
        self.name_value_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self.viewer_actions = ttk.Frame(self.header_frame, style="Card.TFrame")
        self.viewer_actions.grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.viewer_actions.columnconfigure(0, weight=1)
        self.viewer_actions.columnconfigure(1, weight=1)
        self.viewer_actions.columnconfigure(2, weight=1)
        self.viewer_actions.columnconfigure(3, weight=1)

        self.summary_label = ttk.Label(self.frame, anchor="w")
        self.summary_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.stats_frame = ttk.Frame(self.frame, style="Card.TFrame")
        self.stats_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            self.stats_frame.columnconfigure(column, weight=1)

        self.current_label = ttk.Label(self.stats_frame, style="Muted.TLabel")
        self.current_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.max_label = ttk.Label(self.stats_frame, style="Muted.TLabel")
        self.max_label.grid(row=0, column=1, sticky="w", padx=8)
        self.temp_label = ttk.Label(self.stats_frame, style="Muted.TLabel")
        self.temp_label.grid(row=0, column=2, sticky="w", padx=8)
        self.step_label = ttk.Label(self.stats_frame, style="Muted.TLabel")
        self.step_label.grid(row=0, column=3, sticky="w", padx=(8, 0))

        self.current_entry = ttk.Entry(self.stats_frame, textvariable=self.current_var, width=8)
        self.current_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.max_entry = ttk.Entry(self.stats_frame, textvariable=self.max_var, width=8)
        self.max_entry.grid(row=1, column=1, sticky="ew", padx=8)
        self.temp_entry = ttk.Entry(self.stats_frame, textvariable=self.temp_var, width=8)
        self.temp_entry.grid(row=1, column=2, sticky="ew", padx=8)
        self.delta_entry = ttk.Entry(self.stats_frame, textvariable=self.delta_var, width=6)
        self.delta_entry.grid(row=1, column=3, sticky="ew", padx=(8, 0))

        self.actions_primary = ttk.Frame(self.frame, style="Card.TFrame")
        self.actions_primary.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for column in range(3):
            self.actions_primary.columnconfigure(column, weight=1)

        self.actions_secondary = ttk.Frame(self.frame, style="Card.TFrame")
        self.actions_secondary.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        for column in range(3):
            self.actions_secondary.columnconfigure(column, weight=1)

        self.damage_button = ttk.Button(self.actions_primary, command=self.damage)
        self.damage_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.heal_button = ttk.Button(self.actions_primary, command=self.heal)
        self.heal_button.grid(row=0, column=1, sticky="ew", padx=8)
        self.save_button = ttk.Button(self.actions_primary, command=self.apply_edits)
        self.save_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.window_button = ttk.Button(self.viewer_actions, command=self.toggle_player_window)
        self.window_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.overlay_button = ttk.Button(self.viewer_actions, command=self.toggle_overlay)
        self.overlay_button.grid(row=0, column=1, sticky="ew", padx=8)
        self.spell_window_button = ttk.Button(self.viewer_actions, command=self.toggle_spell_window)
        self.spell_window_button.grid(row=0, column=2, sticky="ew", padx=8)
        self.money_window_button = ttk.Button(self.viewer_actions, command=self.toggle_money_window)
        self.money_window_button.grid(row=0, column=3, sticky="ew")

        self.money_edit_button = ttk.Button(self.actions_secondary, command=self.edit_money)
        self.money_edit_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.spell_edit_button = ttk.Button(self.actions_secondary, command=self.edit_spell_slots)
        self.spell_edit_button.grid(row=0, column=1, sticky="ew", padx=8)
        self.remove_button = ttk.Button(self.actions_secondary, command=self.remove_player)
        self.remove_button.grid(row=0, column=2, sticky="ew")

        self.refresh(player)

    def apply_edits(self) -> None:
        player = self.app.player_by_id(self.player_id)
        if player is None:
            return
        player.name = self.app.localized_player_name(self.name_var.get().strip() or player.name)
        player.set_max_hp(self.max_var.get())
        player.set_current_hp(self.current_var.get())
        player.set_temp_hp(self.temp_var.get())
        self.app.persist_and_refresh()

    def damage(self) -> None:
        player = self.app.player_by_id(self.player_id)
        if player is None:
            return
        player.apply_damage(self.delta_var.get())
        self.app.persist_and_refresh()

    def heal(self) -> None:
        player = self.app.player_by_id(self.player_id)
        if player is None:
            return
        player.apply_healing(self.delta_var.get())
        self.app.persist_and_refresh()

    def toggle_player_window(self) -> None:
        self.app.toggle_player_window(self.player_id)

    def toggle_overlay(self) -> None:
        self.app.toggle_overlay(self.player_id)

    def toggle_spell_window(self) -> None:
        self.app.toggle_spell_window(self.player_id)

    def toggle_money_window(self) -> None:
        self.app.toggle_money_window(self.player_id)

    def edit_spell_slots(self) -> None:
        self.app.open_spell_editor(self.player_id)

    def edit_money(self) -> None:
        self.app.open_money_editor(self.player_id)

    def remove_player(self) -> None:
        self.app.remove_player(self.player_id)

    def refresh(self, player: Player) -> None:
        sync_mode = self.app.sync_mode_active()
        self.name_var.set(player.name)
        self.current_var.set(str(player.current_hp))
        self.max_var.set(str(player.max_hp))
        self.temp_var.set(str(player.temp_hp))
        self.name_label.config(text=self.app.t("label.name"))
        self.name_value_label.config(text=player.name)
        self.current_label.config(text=self.app.t("label.current"))
        self.max_label.config(text=self.app.t("label.max"))
        self.temp_label.config(text=self.app.t("label.temp"))
        self.step_label.config(text=self.app.t("label.step"))
        self.summary_label.config(
            text=self.app.t(
                "player.summary",
                current_hp=player.current_hp,
                max_hp=player.max_hp,
                temp_hp=player.temp_hp,
            ),
            foreground=_hp_text_color(player.hp_ratio),
        )

        if sync_mode:
            self.name_label.grid_remove()
            self.name_entry.grid_remove()
            self.name_value_label.grid()
            self.stats_frame.grid_remove()
            self.actions_primary.grid_remove()
            self.actions_secondary.grid()
            self.money_edit_button.grid_remove()
            self.spell_edit_button.grid_remove()
            self.remove_button.grid(row=0, column=0, columnspan=3, sticky="ew")
        else:
            self.name_value_label.grid_remove()
            self.name_label.grid()
            self.name_entry.grid()
            self.stats_frame.grid()
            self.actions_primary.grid()
            self.actions_secondary.grid()
            self.money_edit_button.grid()
            self.spell_edit_button.grid()
            self.remove_button.grid(row=0, column=2, columnspan=1, sticky="ew")

        self.window_button.config(
            text=self.app.t("action.hide_window") if self.player_id in self.app.player_windows else self.app.t("action.player_window")
        )
        self.overlay_button.config(
            text=self.app.t("action.hide_overlay") if self.player_id in self.app.overlay_windows else self.app.t("action.overlay")
        )
        self.spell_window_button.config(
            text=self.app.t("action.hide_spell_window")
            if self.player_id in self.app.spell_windows
            else self.app.t("action.spell_window")
        )
        self.money_window_button.config(
            text=self.app.t("action.hide_money_window")
            if self.player_id in self.app.money_windows
            else self.app.t("action.money_window")
        )
        self.save_button.config(text=self.app.t("action.apply"))
        self.remove_button.config(text=self.app.t("action.remove"))
        self.damage_button.config(text=self.app.t("action.damage"))
        self.heal_button.config(text=self.app.t("action.heal"))
        self.money_edit_button.config(text=self.app.t("action.edit_money"))
        self.spell_edit_button.config(text=self.app.t("action.edit_spell_slots"))

    def destroy(self) -> None:
        self.frame.destroy()


class HealthPointsApp:
    def __init__(self) -> None:
        _set_windows_app_id()
        self.root = tk.Tk()
        self.apply_window_icon(self.root)
        self.root.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.root.geometry("1200x720")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.state: AppState = load_state()
        self.localizer = Localizer(self.state.locale)
        self.player_rows: dict[str, PlayerRow] = {}
        self.player_windows: dict[str, PlayerWindow] = {}
        self.overlay_windows: dict[str, OverlayWindow] = {}
        self.money_windows: dict[str, MoneyWindow] = {}
        self.money_editors: dict[str, MoneyEditorWindow] = {}
        self.spell_windows: dict[str, SpellSlotsWindow] = {}
        self.spell_editors: dict[str, SpellSlotsEditorWindow] = {}
        self.initiative_tracker_window: InitiativeTrackerWindow | None = None

        self.status_var = tk.StringVar(value=self.t("status.ready"))
        self.add_name_var = tk.StringVar()
        self.add_current_var = tk.StringVar(value="10")
        self.add_max_var = tk.StringVar(value="10")
        self.add_temp_var = tk.StringVar(value="0")
        self.sync_enabled_var = tk.BooleanVar(value=self.state.sync.enabled)
        self.sync_source_var = tk.StringVar(value=self.state.sync.source)
        self.sync_poll_var = tk.StringVar(value=str(self.state.sync.poll_seconds))
        self.sync_existing_only_var = tk.BooleanVar(value=self.state.sync.existing_only)
        self.locale_display_var = tk.StringVar(value=self.localizer.locale_name(self.state.locale))
        self.overlay_ratio_var = tk.StringVar(value=self.state.overlay.aspect_ratio)
        self.money_layout_var = tk.StringVar(value=self.money_layout_label_for_code(self.state.overlay.money_layout))
        self.money_order_var = tk.StringVar(value=self.money_order_label_for_code(self.state.overlay.money_order))
        self.spell_display_count_var = tk.StringVar(value=str(self.state.overlay.spell_display_count))
        self.spell_render_mode_var = tk.StringVar(value=self.spell_render_mode_label_for_code(self.state.overlay.spell_render_mode))
        self.hp_font_size_var = tk.StringVar(value=str(self.state.overlay.hp_font_size))
        self.temp_hp_font_size_var = tk.StringVar(value=str(self.state.overlay.temp_hp_font_size))
        self.money_font_size_var = tk.StringVar(value=str(self.state.overlay.money_font_size))
        self.spell_level_font_size_var = tk.StringVar(value=str(self.state.overlay.spell_level_font_size))
        self.spell_font_size_var = tk.StringVar(value=str(self.state.overlay.spell_font_size))
        self.spell_cell_scale_var = tk.StringVar(value=self.spell_cell_scale_display(self.state.overlay.spell_cell_scale))
        self.spell_pip_scale_var = tk.StringVar(value=self.spell_cell_scale_display(self.state.overlay.spell_pip_scale))
        self.overlay_show_title_var = tk.BooleanVar(value=self.state.overlay.show_title)
        self.player_windows_topmost_var = tk.BooleanVar(value=self.state.overlay.player_windows_topmost)
        self.fill_windows_topmost_var = tk.BooleanVar(value=self.state.overlay.fill_windows_topmost)
        self.layout_mode = ""
        self.sync_after_id: str | None = None
        self.sync_result_after_id: str | None = None
        self.sync_fetch_in_progress = False
        self.sync_result_queue: queue.Queue[tuple[str, object, bool]] = queue.Queue()
        self.coin_image_cache: dict[tuple[str, int], tk.PhotoImage] = {}
        self.native_icon_handles: list[int] = []

        self._configure_style()
        self._build_layout()
        self.refresh_locale()
        self.refresh_all()
        self.refresh_sync_schedule()

    def t(self, key: str, **kwargs: object) -> str:
        return self.localizer.text(key, **kwargs)

    def localized_player_name(self, name: str) -> str:
        return (name or "").strip() or self.t("player.default_name")

    def apply_window_icon(self, window: tk.Misc) -> None:
        if not ICON_PATH.exists():
            return
        try:
            icon_path = str(ICON_PATH.resolve())
            window.iconbitmap(icon_path)
            window.iconbitmap(default=icon_path)
        except tk.TclError:
            pass

        if sys.platform == "win32":
            window.after_idle(lambda: self._apply_native_window_icon(window, icon_path))

    def _apply_native_window_icon(self, window: tk.Misc, icon_path: str) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = window.winfo_id()
        except tk.TclError:
            return
        if not hwnd:
            return

        try:
            user32 = ctypes.windll.user32
            icon_handle = user32.LoadImageW(None, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
        except (AttributeError, OSError):
            return

        if not icon_handle:
            return

        try:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, icon_handle)
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, icon_handle)
            self.native_icon_handles.append(int(icon_handle))
        except (AttributeError, OSError):
            return

    def sync_mode_active(self) -> bool:
        return bool(self.state.sync.enabled)

    def open_initiative_tracker(self) -> None:
        if self.initiative_tracker_window is None:
            self.initiative_tracker_window = InitiativeTrackerWindow(self)
        else:
            try:
                self.initiative_tracker_window.window.deiconify()
                self.initiative_tracker_window.window.lift()
                self.initiative_tracker_window.window.focus_force()
            except tk.TclError:
                self.initiative_tracker_window = InitiativeTrackerWindow(self)
                return
        self.initiative_tracker_window.refresh()

    def unregister_initiative_tracker(self) -> None:
        self.initiative_tracker_window = None

    def apply_topmost(self, window: tk.Misc, enabled: bool) -> None:
        try:
            window.attributes("-topmost", enabled)
        except tk.TclError:
            return

    def _coin_asset_path(self, key: str) -> str:
        return str(asset_path("coins", f"{key}.png"))

    def get_coin_image(self, key: str, size: int) -> tk.PhotoImage | None:
        cache_key = (key, size)
        if cache_key in self.coin_image_cache:
            return self.coin_image_cache[cache_key]

        coin_path = asset_path("coins", f"{key}.png")
        if not coin_path.exists():
            return None

        try:
            image = tk.PhotoImage(file=str(coin_path))
        except tk.TclError:
            return None

        scale = max(1, math.ceil(max(image.width() / max(1, size), image.height() / max(1, size))))
        if scale > 1:
            image = image.subsample(scale, scale)

        self.coin_image_cache[cache_key] = image
        return image

    def create_coin_widget(self, parent: tk.Misc, key: str, size: int, background: str) -> tk.Widget:
        image = self.get_coin_image(key, size)
        if image is not None:
            label = tk.Label(parent, image=image, bg=background, bd=0, highlightthickness=0)
            label.image = image
            label.coin_key = key
            label.coin_size = size
            label.coin_background = background
            return label

        base, highlight, outline = COIN_COLORS[key]
        canvas = tk.Canvas(parent, width=size, height=size, bg=background, highlightthickness=0, bd=0)
        inset = max(2, size // 10)
        inner = max(inset + 3, size // 4)
        canvas.create_oval(2, 2, size - 2, size - 2, fill=base, outline=outline, width=2)
        canvas.create_oval(inset, inset, size - inset, size - inset, outline=highlight, width=2)
        canvas.create_oval(inner, inner, size - inner, size - inner, fill=highlight, outline=outline, width=1)
        canvas.create_text(size // 2, size // 2, text=self.t(f"money.{key}"), fill=outline, font=("Segoe UI Semibold", max(8, size // 5)))
        canvas.coin_key = key
        canvas.coin_size = size
        canvas.coin_background = background
        return canvas

    def refresh_coin_widget(self, widget: tk.Widget, key: str, size: int, background: str) -> None:
        image = self.get_coin_image(key, size)
        if isinstance(widget, tk.Label):
            if image is not None:
                widget.config(image=image, bg=background)
                widget.image = image
            else:
                widget.config(image="", text=self.t(f"money.{key}"), bg=background, fg=COIN_COLORS[key][2], font=("Segoe UI Semibold", max(8, size // 5)))
            return

        if isinstance(widget, tk.Canvas):
            widget.delete("all")
            widget.config(width=size, height=size, bg=background)
            if image is not None:
                widget.create_image(size // 2, size // 2, image=image)
                widget.image = image
            else:
                base, highlight, outline = COIN_COLORS[key]
                inset = max(2, size // 10)
                inner = max(inset + 3, size // 4)
                widget.create_oval(2, 2, size - 2, size - 2, fill=base, outline=outline, width=2)
                widget.create_oval(inset, inset, size - inset, size - inset, outline=highlight, width=2)
                widget.create_oval(inner, inner, size - inner, size - inner, fill=highlight, outline=outline, width=1)
                widget.create_text(
                    size // 2,
                    size // 2,
                    text=self.t(f"money.{key}"),
                    fill=outline,
                    font=("Segoe UI Semibold", max(8, size // 5)),
                )

    def right_panel_visible(self) -> bool:
        return bool(self.state.sync.visible or self.state.overlay.panel_visible)

    def overlay_ratio_label_for_code(self, code: str) -> str:
        normalized = code if code in {"1:1", "4:3", "3:4"} else "1:1"
        return self.t(f"overlay.aspect.{normalized}")

    def overlay_ratio_code_from_label(self, label: str) -> str:
        for code in ("1:1", "4:3", "3:4"):
            if label == self.overlay_ratio_label_for_code(code):
                return code
        return "1:1"

    def money_layout_label_for_code(self, code: str) -> str:
        normalized = code if code in {"stacked", "inline"} else "stacked"
        return self.t(f"money.layout.{normalized}")

    def money_layout_code_from_label(self, label: str) -> str:
        for code in ("stacked", "inline"):
            if label == self.money_layout_label_for_code(code):
                return code
        return "stacked"

    def money_order_label_for_code(self, code: str) -> str:
        normalized = code if code in {"cc_sc_gc", "gc_sc_cc"} else "cc_sc_gc"
        return self.t(f"money.order.{normalized}")

    def money_order_code_from_label(self, label: str) -> str:
        for code in ("cc_sc_gc", "gc_sc_cc"):
            if label == self.money_order_label_for_code(code):
                return code
        return "cc_sc_gc"

    def money_coin_keys(self) -> tuple[str, str, str]:
        if self.state.overlay.money_order == "gc_sc_cc":
            return ("gc", "sc", "cc")
        return ("cc", "sc", "gc")

    def spell_render_mode_label_for_code(self, code: str) -> str:
        normalized = code if code in {"text", "pips"} else "text"
        return self.t(f"spell.render.{normalized}")

    def spell_render_mode_code_from_label(self, label: str) -> str:
        for code in ("text", "pips"):
            if label == self.spell_render_mode_label_for_code(code):
                return code
        return "text"

    def visible_spell_levels(self) -> tuple[int, ...]:
        count = max(1, min(len(SPELL_SLOT_LEVELS), int(self.state.overlay.spell_display_count)))
        return SPELL_SLOT_LEVELS[:count]

    def spell_cell_scale_display(self, value: int) -> str:
        return f"{max(80, min(200, int(value)))}%"

    def spell_cell_scale_from_label(self, value: str) -> int:
        cleaned = value.strip().removesuffix("%")
        try:
            return max(80, min(200, int(cleaned)))
        except ValueError:
            return 100

    def refresh_spell_mode_controls(self) -> None:
        text_mode = self.state.overlay.spell_render_mode == "text"
        if text_mode:
            self.spell_font_size_label.grid()
            self.spell_font_size_combo.grid()
            self.spell_cell_scale_text_label.grid()
            self.spell_cell_scale_combo.grid()
            self.spell_pip_scale_label.grid_remove()
            self.spell_pip_scale_combo.grid_remove()
        else:
            self.spell_font_size_label.grid_remove()
            self.spell_font_size_combo.grid_remove()
            self.spell_cell_scale_text_label.grid_remove()
            self.spell_cell_scale_combo.grid_remove()
            self.spell_pip_scale_label.grid()
            self.spell_pip_scale_combo.grid()

    def overlay_dimensions(self, base_size: int) -> tuple[int, int]:
        base = max(60, min(600, int(base_size)))
        if self.state.overlay.aspect_ratio == "4:3":
            width = base
            height = max(45, int(base * 3 / 4))
        elif self.state.overlay.aspect_ratio == "3:4":
            width = max(45, int(base * 3 / 4))
            height = base
        else:
            width = base
            height = base
        if self.state.overlay.show_title:
            height += OVERLAY_TITLE_HEIGHT
        return width, height

    def overlay_base_from_size(self, width: int, height: int) -> int:
        content_height = max(20, height - (OVERLAY_TITLE_HEIGHT if self.state.overlay.show_title else 0))
        if self.state.overlay.aspect_ratio == "4:3":
            return max(width, int(content_height * 4 / 3))
        if self.state.overlay.aspect_ratio == "3:4":
            return max(height, int(width * 4 / 3), content_height)
        return max(width, content_height)

    def _configure_style(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.root.configure(bg="#101214")
        style.configure("TFrame", background="#101214")
        style.configure("Card.TFrame", background="#171a1f")
        style.configure("TLabel", background="#101214", foreground="#f0f3f6")
        style.configure("Muted.TLabel", background="#101214", foreground="#a8b3bf")
        style.configure("CardTitle.TLabel", background="#171a1f", foreground="#f0f3f6", font=("Segoe UI Semibold", 12))
        style.configure("Header.TLabel", background="#101214", foreground="#f0f3f6", font=("Segoe UI Semibold", 18))
        style.configure("TButton", padding=(10, 6))
        style.configure("TEntry", padding=(6, 4))
        style.configure("Section.TLabelframe", background="#101214", foreground="#f0f3f6")
        style.configure("Section.TLabelframe.Label", background="#101214", foreground="#f0f3f6", font=("Segoe UI Semibold", 11))

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(1, weight=1)
        self.container = container

        self.title_label = ttk.Label(container, style="Header.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")

        top_right = ttk.Frame(container)
        top_right.grid(row=0, column=1, sticky="e")
        top_right.columnconfigure(0, weight=1)

        self.subtitle_label = ttk.Label(top_right, style="Muted.TLabel")
        self.subtitle_label.grid(row=0, column=0, columnspan=2, sticky="e")
        self.language_label = ttk.Label(top_right, style="Muted.TLabel")
        self.language_label.grid(row=1, column=0, sticky="e", pady=(8, 0), padx=(0, 8))
        self.language_combo = ttk.Combobox(top_right, state="readonly", width=16, textvariable=self.locale_display_var)
        self.language_combo.grid(row=1, column=1, sticky="e", pady=(8, 0))
        self.language_combo.bind("<<ComboboxSelected>>", self.change_locale)
        self.sync_toggle_button = ttk.Button(top_right, command=self.toggle_sync_visibility)
        self.sync_toggle_button.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.settings_toggle_button = ttk.Button(top_right, command=self.toggle_settings_visibility)
        self.settings_toggle_button.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.initiative_toggle_button = ttk.Button(top_right, command=self.open_initiative_tracker)
        self.initiative_toggle_button.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))

        left = ttk.Frame(container)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        self.left_panel = left

        right = ttk.Frame(container)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=0)
        right.columnconfigure(0, weight=1)
        self.right_panel = right

        self._build_add_player_card(left)
        self._build_players_card(left)
        self._build_sync_card(right)
        self._build_overlay_settings_card(right)
        self._build_status_bar(container)
        self.container.bind("<Configure>", self._on_container_configure)
        self._update_main_layout()

    def _build_add_player_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.grid(row=0, column=0, sticky="ew")
        self.add_player_card = card
        for column in range(4):
            card.columnconfigure(column, weight=1)

        self.add_player_title_label = ttk.Label(card, style="CardTitle.TLabel")
        self.add_player_title_label.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        self.add_name_label = ttk.Label(card)
        self.add_name_label.grid(row=1, column=0, sticky="w")
        self.add_current_label = ttk.Label(card)
        self.add_current_label.grid(row=1, column=1, sticky="w")
        self.add_max_label = ttk.Label(card)
        self.add_max_label.grid(row=1, column=2, sticky="w")
        self.add_temp_label = ttk.Label(card)
        self.add_temp_label.grid(row=1, column=3, sticky="w")

        ttk.Entry(card, textvariable=self.add_name_var).grid(row=2, column=0, sticky="ew", padx=(0, 8))
        ttk.Entry(card, textvariable=self.add_current_var, width=8).grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Entry(card, textvariable=self.add_max_var, width=8).grid(row=2, column=2, sticky="ew", padx=4)
        ttk.Entry(card, textvariable=self.add_temp_var, width=8).grid(row=2, column=3, sticky="ew", padx=4)
        self.add_player_button = ttk.Button(card, command=self.add_player)
        self.add_player_button.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 0))

    def _build_players_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, style="Section.TLabelframe", padding=10)
        card.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)
        self.players_card = card

        header = ttk.Frame(card)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        self.players_header_label = ttk.Label(header, style="Muted.TLabel")
        self.players_header_label.grid(row=0, column=0, sticky="w")

        self.canvas = tk.Canvas(card, bg="#101214", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.rows_frame = ttk.Frame(self.canvas)
        self.rows_window = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", self._on_rows_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _build_sync_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, style="Section.TLabelframe", padding=14)
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(1, weight=1)
        card.rowconfigure(5, weight=1)
        self.sync_card = card

        self.sync_enable_check = ttk.Checkbutton(card, variable=self.sync_enabled_var, command=self.save_sync_settings)
        self.sync_enable_check.grid(row=0, column=0, columnspan=2, sticky="w")
        self.sync_existing_only_check = ttk.Checkbutton(card, variable=self.sync_existing_only_var, command=self.save_sync_settings)
        self.sync_existing_only_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.sync_source_label = ttk.Label(card)
        self.sync_source_label.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(card, textvariable=self.sync_source_var).grid(row=2, column=1, sticky="ew", pady=(12, 0))
        self.sync_poll_label = ttk.Label(card)
        self.sync_poll_label.grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(card, textvariable=self.sync_poll_var, width=8).grid(row=3, column=1, sticky="w", pady=(12, 0))
        self.sync_help_label = ttk.Label(card, style="Muted.TLabel")
        self.sync_help_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 8))

        self.sync_text = tk.Text(
            card,
            height=12,
            wrap="word",
            bg="#141922",
            fg="#f0f3f6",
            insertbackground="#f0f3f6",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.sync_text.grid(row=5, column=0, columnspan=2, sticky="nsew")

        button_row = ttk.Frame(card)
        button_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.fetch_doc_button = ttk.Button(button_row, command=self.fetch_doc_now)
        self.fetch_doc_button.pack(side="left")
        self.apply_sync_button = ttk.Button(button_row, command=self.apply_sync_text)
        self.apply_sync_button.pack(side="left", padx=(8, 0))
        self.load_example_button = ttk.Button(button_row, command=self.load_sync_example)
        self.load_example_button.pack(side="left", padx=(8, 0))

    def _build_overlay_settings_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, style="Section.TLabelframe", padding=14)
        card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        card.columnconfigure(1, weight=1)
        self.overlay_settings_card = card

        self.overlay_ratio_label = ttk.Label(card)
        self.overlay_ratio_label.grid(row=0, column=0, sticky="w")
        self.overlay_ratio_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.overlay_ratio_var)
        self.overlay_ratio_combo.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.overlay_ratio_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.overlay_title_check = ttk.Checkbutton(card, variable=self.overlay_show_title_var, command=self.save_overlay_settings)
        self.overlay_title_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.money_layout_label = ttk.Label(card)
        self.money_layout_label.grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.money_layout_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.money_layout_var)
        self.money_layout_combo.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.money_layout_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.money_order_label = ttk.Label(card)
        self.money_order_label.grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.money_order_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.money_order_var)
        self.money_order_combo.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.money_order_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.spell_display_count_label = ttk.Label(card)
        self.spell_display_count_label.grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.spell_display_count_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.spell_display_count_var)
        self.spell_display_count_combo.grid(row=4, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.spell_display_count_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.spell_render_mode_label = ttk.Label(card)
        self.spell_render_mode_label.grid(row=5, column=0, sticky="w", pady=(12, 0))
        self.spell_render_mode_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.spell_render_mode_var)
        self.spell_render_mode_combo.grid(row=5, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.spell_render_mode_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.hp_font_size_label = ttk.Label(card)
        self.hp_font_size_label.grid(row=6, column=0, sticky="w", pady=(12, 0))
        self.hp_font_size_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.hp_font_size_var)
        self.hp_font_size_combo.grid(row=6, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.hp_font_size_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.temp_hp_font_size_label = ttk.Label(card)
        self.temp_hp_font_size_label.grid(row=7, column=0, sticky="w", pady=(12, 0))
        self.temp_hp_font_size_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.temp_hp_font_size_var)
        self.temp_hp_font_size_combo.grid(row=7, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.temp_hp_font_size_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.money_font_size_label = ttk.Label(card)
        self.money_font_size_label.grid(row=8, column=0, sticky="w", pady=(12, 0))
        self.money_font_size_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.money_font_size_var)
        self.money_font_size_combo.grid(row=8, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.money_font_size_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.spell_level_font_size_label = ttk.Label(card)
        self.spell_level_font_size_label.grid(row=9, column=0, sticky="w", pady=(12, 0))
        self.spell_level_font_size_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.spell_level_font_size_var)
        self.spell_level_font_size_combo.grid(row=9, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.spell_level_font_size_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.spell_font_size_label = ttk.Label(card)
        self.spell_font_size_label.grid(row=10, column=0, sticky="w", pady=(12, 0))
        self.spell_font_size_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.spell_font_size_var)
        self.spell_font_size_combo.grid(row=10, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.spell_font_size_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.spell_cell_scale_text_label = ttk.Label(card)
        self.spell_cell_scale_text_label.grid(row=11, column=0, sticky="w", pady=(12, 0))
        self.spell_cell_scale_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.spell_cell_scale_var)
        self.spell_cell_scale_combo.grid(row=11, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.spell_cell_scale_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.spell_pip_scale_label = ttk.Label(card)
        self.spell_pip_scale_label.grid(row=12, column=0, sticky="w", pady=(12, 0))
        self.spell_pip_scale_combo = ttk.Combobox(card, state="readonly", width=18, textvariable=self.spell_pip_scale_var)
        self.spell_pip_scale_combo.grid(row=12, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        self.spell_pip_scale_combo.bind("<<ComboboxSelected>>", self.save_overlay_settings)

        self.window_behavior_label = ttk.Label(card)
        self.window_behavior_label.grid(row=13, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.player_windows_topmost_check = ttk.Checkbutton(
            card,
            variable=self.player_windows_topmost_var,
            command=self.save_overlay_settings,
        )
        self.player_windows_topmost_check.grid(row=14, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.fill_windows_topmost_check = ttk.Checkbutton(
            card,
            variable=self.fill_windows_topmost_var,
            command=self.save_overlay_settings,
        )
        self.fill_windows_topmost_check.grid(row=15, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, textvariable=self.status_var, style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def _on_rows_configure(self, _event: object | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.rows_window, width=event.width)

    def _on_container_configure(self, event: tk.Event) -> None:
        self._update_main_layout(event.width)

    def _update_main_layout(self, width: int | None = None) -> None:
        current_width = width or self.container.winfo_width() or self.root.winfo_width()
        mode = "stacked" if current_width < 1380 else "wide"
        self.layout_mode = mode
        self.left_panel.grid_forget()
        self.right_panel.grid_forget()
        show_right_panel = self.right_panel_visible()

        if mode == "wide":
            self.container.columnconfigure(0, weight=3 if show_right_panel else 1)
            self.container.columnconfigure(1, weight=2 if show_right_panel else 0)
            self.container.rowconfigure(1, weight=1)
            self.container.rowconfigure(2, weight=0)
            self.left_panel.grid(
                row=1,
                column=0,
                columnspan=1 if show_right_panel else 2,
                sticky="nsew",
                padx=(0, 16 if show_right_panel else 0),
                pady=(16, 0),
            )
            if show_right_panel:
                self.right_panel.grid(row=1, column=1, sticky="nsew", pady=(16, 0))
        else:
            self.container.columnconfigure(0, weight=1)
            self.container.columnconfigure(1, weight=0)
            self.container.rowconfigure(1, weight=4)
            self.container.rowconfigure(2, weight=1 if show_right_panel else 0)
            self.left_panel.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="nsew",
                pady=(16, 8 if show_right_panel else 0),
            )
            if show_right_panel:
                self.right_panel.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

    def toggle_settings_visibility(self) -> None:
        self.state.overlay.panel_visible = not self.state.overlay.panel_visible
        self.refresh_locale()
        self._update_main_layout()
        save_state(self.state)
        self.status_var.set(self.t("status.settings_shown") if self.state.overlay.panel_visible else self.t("status.settings_hidden"))

    def save_overlay_settings(self, _event: tk.Event | None = None) -> None:
        self.state.overlay.aspect_ratio = self.overlay_ratio_code_from_label(self.overlay_ratio_var.get())
        self.state.overlay.money_layout = self.money_layout_code_from_label(self.money_layout_var.get())
        self.state.overlay.money_order = self.money_order_code_from_label(self.money_order_var.get())
        self.state.overlay.spell_display_count = max(1, min(9, int(self.spell_display_count_var.get() or "6")))
        self.state.overlay.spell_render_mode = self.spell_render_mode_code_from_label(self.spell_render_mode_var.get())
        self.state.overlay.hp_font_size = max(12, min(72, int(self.hp_font_size_var.get() or "34")))
        self.state.overlay.temp_hp_font_size = max(12, min(72, int(self.temp_hp_font_size_var.get() or "22")))
        self.state.overlay.money_font_size = max(12, min(72, int(self.money_font_size_var.get() or "24")))
        self.state.overlay.spell_level_font_size = max(12, min(72, int(self.spell_level_font_size_var.get() or "32")))
        self.state.overlay.spell_font_size = max(12, min(72, int(self.spell_font_size_var.get() or "24")))
        self.state.overlay.spell_cell_scale = self.spell_cell_scale_from_label(self.spell_cell_scale_var.get())
        self.state.overlay.spell_pip_scale = self.spell_cell_scale_from_label(self.spell_pip_scale_var.get())
        self.state.overlay.show_title = self.overlay_show_title_var.get()
        self.state.overlay.player_windows_topmost = self.player_windows_topmost_var.get()
        self.state.overlay.fill_windows_topmost = self.fill_windows_topmost_var.get()
        save_state(self.state)
        self.refresh_spell_mode_controls()
        self.refresh_player_windows()
        self.refresh_overlay_windows()
        self.refresh_money_window()
        self.refresh_money_editors()
        self.refresh_spell_windows()
        self.status_var.set(self.t("status.overlay_settings_saved"))

    def refresh_player_windows(self) -> None:
        for player_id, player_window in list(self.player_windows.items()):
            player = self.player_by_id(player_id)
            if player is None:
                continue
            self.apply_topmost(player_window.window, self.state.overlay.player_windows_topmost)
            player_window.refresh(player)

    def refresh_overlay_windows(self) -> None:
        for player_id, overlay in list(self.overlay_windows.items()):
            player = self.player_by_id(player_id)
            if player is None:
                continue
            self.apply_topmost(overlay.window, self.state.overlay.fill_windows_topmost)
            base = self.overlay_base_from_size(overlay.window.winfo_width(), overlay.window.winfo_height())
            width, height = self.overlay_dimensions(base)
            overlay.window.geometry(f"{width}x{height}+{overlay.window.winfo_x()}+{overlay.window.winfo_y()}")
            overlay.refresh(player)

    def refresh_money_window(self) -> None:
        for player_id, money_window in list(self.money_windows.items()):
            player = self.player_by_id(player_id)
            if player is None:
                continue
            self.apply_topmost(money_window.window, self.state.overlay.player_windows_topmost)
            money_window.refresh(player)

    def refresh_spell_windows(self) -> None:
        for player_id, spell_window in list(self.spell_windows.items()):
            player = self.player_by_id(player_id)
            if player is None:
                continue
            self.apply_topmost(spell_window.window, self.state.overlay.player_windows_topmost)
            spell_window.refresh(player)

    def refresh_spell_editors(self) -> None:
        for player_id, editor in list(self.spell_editors.items()):
            player = self.player_by_id(player_id)
            if player is None:
                editor.close()
                continue
            editor.refresh(player)

    def refresh_money_editors(self) -> None:
        for player_id, editor in list(self.money_editors.items()):
            player = self.player_by_id(player_id)
            if player is None:
                editor.close()
                continue
            editor.refresh(player)

    def toggle_money_window(self, player_id: str) -> None:
        if player_id in self.money_windows:
            self.close_money_window(player_id)
        else:
            player = self.player_by_id(player_id)
            if player:
                self.money_windows[player_id] = MoneyWindow(self, player)
        self.refresh_all()

    def close_money_window(self, player_id: str) -> None:
        money_window = self.money_windows.pop(player_id, None)
        if money_window and money_window.window.winfo_exists():
            money_window.window.destroy()

    def unregister_money_window(self, player_id: str) -> None:
        self.money_windows.pop(player_id, None)
        self.refresh_all()

    def open_money_editor(self, player_id: str) -> None:
        if self.sync_mode_active():
            return
        if player_id in self.money_editors:
            editor = self.money_editors[player_id]
            if editor.window.winfo_exists():
                editor.window.lift()
                return
        player = self.player_by_id(player_id)
        if player:
            self.money_editors[player_id] = MoneyEditorWindow(self, player)

    def close_money_editor(self, player_id: str) -> None:
        editor = self.money_editors.pop(player_id, None)
        if editor and editor.window.winfo_exists():
            editor.window.destroy()

    def unregister_money_editor(self, player_id: str) -> None:
        self.money_editors.pop(player_id, None)

    def toggle_spell_window(self, player_id: str) -> None:
        if player_id in self.spell_windows:
            self.close_spell_window(player_id)
        else:
            player = self.player_by_id(player_id)
            if player:
                self.spell_windows[player_id] = SpellSlotsWindow(self, player)
        self.refresh_all()

    def close_spell_window(self, player_id: str) -> None:
        spell_window = self.spell_windows.pop(player_id, None)
        if spell_window and spell_window.window.winfo_exists():
            spell_window.window.destroy()

    def unregister_spell_window(self, player_id: str) -> None:
        self.spell_windows.pop(player_id, None)
        self.refresh_all()

    def open_spell_editor(self, player_id: str) -> None:
        if self.sync_mode_active():
            return
        if player_id in self.spell_editors:
            editor = self.spell_editors[player_id]
            if editor.window.winfo_exists():
                editor.window.lift()
                return
        player = self.player_by_id(player_id)
        if player:
            self.spell_editors[player_id] = SpellSlotsEditorWindow(self, player)

    def close_spell_editor(self, player_id: str) -> None:
        editor = self.spell_editors.pop(player_id, None)
        if editor and editor.window.winfo_exists():
            editor.window.destroy()

    def unregister_spell_editor(self, player_id: str) -> None:
        self.spell_editors.pop(player_id, None)

    def toggle_sync_visibility(self) -> None:
        self.state.sync.visible = not self.state.sync.visible
        self.refresh_locale()
        self._update_main_layout()
        save_state(self.state)
        self.status_var.set(self.t("status.sync_shown") if self.state.sync.visible else self.t("status.sync_hidden"))

    def player_by_id(self, player_id: str) -> Player | None:
        for player in self.state.players:
            if player.player_id == player_id:
                return player
        return None

    def _find_player_by_name(self, name: str) -> Player | None:
        normalized = name.strip().lower()
        for player in self.state.players:
            if player.name.strip().lower() == normalized:
                return player
        return None

    def format_parse_issues(self, issues: list[ParseIssue]) -> list[str]:
        return [self.t("dialog.parse_issues.message", line_number=issue.line_number, line=issue.line) for issue in issues]

    def change_locale(self, _event: tk.Event | None = None) -> None:
        selected = self.locale_display_var.get()
        locale = self.state.locale
        for code in SUPPORTED_LOCALES:
            if selected in {code, self.localizer.locale_name(code)}:
                locale = code
                break

        self.localizer.set_locale(locale)
        self.state.locale = locale
        self.locale_display_var.set(self.localizer.locale_name(locale))
        self.refresh_locale()
        self.refresh_all()
        self.save_sync_settings()
        save_state(self.state)
        self.status_var.set(self.t("status.language_changed", language=self.localizer.locale_name(locale)))

    def refresh_locale(self) -> None:
        self.root.title(self.t("app.title"))
        self.title_label.config(text=self.t("app.header"))
        self.subtitle_label.config(text=self.t("app.subtitle"))
        self.language_label.config(text=self.t("language.label"))
        self.language_combo.config(values=[self.localizer.locale_name(code) for code in SUPPORTED_LOCALES])
        self.locale_display_var.set(self.localizer.locale_name(self.state.locale))

        self.add_player_title_label.config(text=self.t("card.add_player"))
        self.add_name_label.config(text=self.t("label.name"))
        self.add_current_label.config(text=self.t("label.current"))
        self.add_max_label.config(text=self.t("label.max"))
        self.add_temp_label.config(text=self.t("label.temp"))
        self.add_player_button.config(text=self.t("action.add_to_dashboard"))

        self.players_card.config(text=self.t("card.players"))
        self.players_header_label.config(text=self.t("players.header"))

        self.sync_card.config(text=self.t("card.sync"))
        self.sync_enable_check.config(text=self.t("sync.enable"))
        self.sync_existing_only_check.config(text=self.t("sync.only_existing"))
        self.sync_source_label.config(text=self.t("label.source"))
        self.sync_poll_label.config(text=self.t("label.poll_seconds"))
        self.sync_help_label.config(text=self.t("sync.help"))
        self.sync_existing_only_var.set(self.state.sync.existing_only)
        self.fetch_doc_button.config(text=self.t("action.fetch_doc"))
        self.apply_sync_button.config(text=self.t("action.apply_parsed_lines"))
        self.load_example_button.config(text=self.t("action.load_example"))
        self.sync_toggle_button.config(
            text=self.t("action.hide_sync") if self.state.sync.visible else self.t("action.show_sync")
        )
        self.settings_toggle_button.config(
            text=self.t("action.hide_settings") if self.state.overlay.panel_visible else self.t("action.show_settings")
        )
        self.initiative_toggle_button.config(text=self.t("action.open_initiative_tracker"))
        self.overlay_settings_card.config(text=self.t("card.overlay_settings"))
        self.overlay_ratio_label.config(text=self.t("label.overlay_ratio"))
        self.money_layout_label.config(text=self.t("label.money_layout"))
        self.money_order_label.config(text=self.t("label.money_order"))
        self.spell_display_count_label.config(text=self.t("label.spell_display_count"))
        self.spell_render_mode_label.config(text=self.t("label.spell_render_mode"))
        self.hp_font_size_label.config(text=self.t("label.hp_font_size"))
        self.temp_hp_font_size_label.config(text=self.t("label.temp_hp_font_size"))
        self.money_font_size_label.config(text=self.t("label.money_font_size"))
        self.spell_level_font_size_label.config(text=self.t("label.spell_level_font_size"))
        self.spell_font_size_label.config(text=self.t("label.spell_font_size"))
        self.spell_cell_scale_text_label.config(text=self.t("label.spell_cell_scale"))
        self.spell_pip_scale_label.config(text=self.t("label.spell_pip_scale"))
        self.window_behavior_label.config(text=self.t("label.window_behavior"))
        self.overlay_ratio_combo.config(
            values=[
                self.t("overlay.aspect.1:1"),
                self.t("overlay.aspect.4:3"),
                self.t("overlay.aspect.3:4"),
            ]
        )
        self.overlay_ratio_combo.set(self.t(f"overlay.aspect.{self.state.overlay.aspect_ratio}"))
        self.money_layout_combo.config(
            values=[
                self.t("money.layout.stacked"),
                self.t("money.layout.inline"),
            ]
        )
        self.money_layout_combo.set(self.t(f"money.layout.{self.state.overlay.money_layout}"))
        self.money_order_combo.config(
            values=[
                self.t("money.order.cc_sc_gc"),
                self.t("money.order.gc_sc_cc"),
            ]
        )
        self.money_order_combo.set(self.t(f"money.order.{self.state.overlay.money_order}"))
        self.spell_display_count_combo.config(values=[str(level) for level in SPELL_SLOT_LEVELS])
        self.spell_display_count_combo.set(str(self.state.overlay.spell_display_count))
        self.spell_render_mode_combo.config(
            values=[
                self.t("spell.render.text"),
                self.t("spell.render.pips"),
            ]
        )
        self.spell_render_mode_combo.set(self.t(f"spell.render.{self.state.overlay.spell_render_mode}"))
        self.hp_font_size_combo.config(values=FONT_SIZE_OPTIONS)
        self.hp_font_size_combo.set(str(self.state.overlay.hp_font_size))
        self.temp_hp_font_size_combo.config(values=FONT_SIZE_OPTIONS)
        self.temp_hp_font_size_combo.set(str(self.state.overlay.temp_hp_font_size))
        self.money_font_size_combo.config(values=FONT_SIZE_OPTIONS)
        self.money_font_size_combo.set(str(self.state.overlay.money_font_size))
        self.spell_level_font_size_combo.config(values=FONT_SIZE_OPTIONS)
        self.spell_level_font_size_combo.set(str(self.state.overlay.spell_level_font_size))
        self.spell_font_size_combo.config(values=FONT_SIZE_OPTIONS)
        self.spell_font_size_combo.set(str(self.state.overlay.spell_font_size))
        self.spell_cell_scale_combo.config(values=SPELL_CELL_SCALE_OPTIONS)
        self.spell_cell_scale_combo.set(self.spell_cell_scale_display(self.state.overlay.spell_cell_scale))
        self.spell_pip_scale_combo.config(values=SPELL_CELL_SCALE_OPTIONS)
        self.spell_pip_scale_combo.set(self.spell_cell_scale_display(self.state.overlay.spell_pip_scale))
        self.overlay_title_check.config(text=self.t("overlay.show_title"))
        self.overlay_show_title_var.set(self.state.overlay.show_title)
        self.player_windows_topmost_check.config(text=self.t("overlay.player_windows_topmost"))
        self.fill_windows_topmost_check.config(text=self.t("overlay.fill_windows_topmost"))
        self.player_windows_topmost_var.set(self.state.overlay.player_windows_topmost)
        self.fill_windows_topmost_var.set(self.state.overlay.fill_windows_topmost)
        if self.state.sync.visible:
            self.sync_card.grid()
        else:
            self.sync_card.grid_remove()
        if self.state.overlay.panel_visible:
            self.overlay_settings_card.grid()
        else:
            self.overlay_settings_card.grid_remove()
        self.refresh_spell_mode_controls()
        if self.initiative_tracker_window is not None:
            self.initiative_tracker_window.refresh()
        self.refresh_sync_mode_visibility()

    def refresh_sync_mode_visibility(self) -> None:
        if self.sync_mode_active():
            self.add_player_card.grid_remove()
            for player_id in list(self.money_editors):
                self.close_money_editor(player_id)
            for player_id in list(self.spell_editors):
                self.close_spell_editor(player_id)
        else:
            self.add_player_card.grid()

    def add_player(self) -> None:
        player = Player(
            name=self.localized_player_name(self.add_name_var.get()),
            current_hp=self.add_current_var.get(),
            max_hp=self.add_max_var.get(),
            temp_hp=self.add_temp_var.get(),
        )
        self.state.players.append(player)
        self.add_name_var.set("")
        self.add_current_var.set(str(player.max_hp))
        self.add_max_var.set(str(player.max_hp))
        self.add_temp_var.set("0")
        self.persist_and_refresh(status=self.t("status.added", name=player.name))

    def remove_player(self, player_id: str) -> None:
        player = self.player_by_id(player_id)
        if player is None:
            return
        self.close_player_window(player_id)
        self.close_overlay(player_id)
        self.close_money_window(player_id)
        self.close_money_editor(player_id)
        self.close_spell_window(player_id)
        self.close_spell_editor(player_id)
        self.state.players = [item for item in self.state.players if item.player_id != player_id]
        row = self.player_rows.pop(player_id, None)
        if row:
            row.destroy()
        self.persist_and_refresh(status=self.t("status.removed", name=player.name))

    def toggle_player_window(self, player_id: str) -> None:
        if player_id in self.player_windows:
            self.close_player_window(player_id)
        else:
            player = self.player_by_id(player_id)
            if player:
                self.player_windows[player_id] = PlayerWindow(self, player)
        self.refresh_all()

    def close_player_window(self, player_id: str) -> None:
        window = self.player_windows.pop(player_id, None)
        if window and window.window.winfo_exists():
            window.window.destroy()

    def unregister_player_window(self, player_id: str) -> None:
        self.player_windows.pop(player_id, None)
        self.refresh_all()

    def toggle_overlay(self, player_id: str) -> None:
        if player_id in self.overlay_windows:
            self.close_overlay(player_id)
        else:
            player = self.player_by_id(player_id)
            if player:
                self.overlay_windows[player_id] = OverlayWindow(self, player)
        self.refresh_all()

    def close_overlay(self, player_id: str) -> None:
        overlay = self.overlay_windows.pop(player_id, None)
        if overlay and overlay.window.winfo_exists():
            overlay.window.destroy()

    def unregister_overlay_window(self, player_id: str) -> None:
        self.overlay_windows.pop(player_id, None)
        self.refresh_all()

    def save_sync_settings(self, refresh_schedule: bool = True) -> None:
        self.state.sync.enabled = self.sync_enabled_var.get()
        self.state.sync.source = self.sync_source_var.get().strip()
        self.state.sync.existing_only = self.sync_existing_only_var.get()
        try:
            self.state.sync.poll_seconds = max(5, int(self.sync_poll_var.get()))
        except ValueError:
            self.state.sync.poll_seconds = 15
            self.sync_poll_var.set("15")
        self.refresh_sync_mode_visibility()
        self.refresh_all()
        if refresh_schedule:
            self.refresh_sync_schedule()

    def refresh_sync_schedule(self) -> None:
        if self.sync_after_id is not None:
            self.root.after_cancel(self.sync_after_id)
            self.sync_after_id = None

        if self.state.sync.enabled and self.state.sync.source.strip():
            delay_ms = max(5, self.state.sync.poll_seconds) * 1000
            self.sync_after_id = self.root.after(delay_ms, self._poll_sync_source)

    def _schedule_sync_result_processing(self) -> None:
        if self.sync_result_after_id is None:
            self.sync_result_after_id = self.root.after(100, self._process_sync_results)

    def _process_sync_results(self) -> None:
        self.sync_result_after_id = None
        handled_result = False

        while True:
            try:
                result_type, payload, auto = self.sync_result_queue.get_nowait()
            except queue.Empty:
                break

            handled_result = True
            if result_type == "success":
                self._handle_fetch_success(str(payload), auto)
            elif result_type == "sync_error":
                message_key, context = payload if isinstance(payload, tuple) else ("error.sync.unknown", {})
                context_dict = context if isinstance(context, dict) else {}
                self._handle_fetch_failure(self.t(str(message_key), **context_dict), auto)
            else:
                self._handle_fetch_failure(self.t("error.sync.unknown", message=str(payload)), auto)

        if self.sync_fetch_in_progress or not self.sync_result_queue.empty():
            self._schedule_sync_result_processing()
        elif not handled_result:
            self.sync_result_after_id = None

    def _poll_sync_source(self) -> None:
        self.sync_after_id = None
        self.fetch_doc_now(auto=True)

    def fetch_doc_now(self, auto: bool = False) -> None:
        self.save_sync_settings(refresh_schedule=not auto)
        source = self.state.sync.source.strip()
        if not source:
            if not auto:
                self.status_var.set(self.t("status.sync_source_missing"))
            return

        if self.sync_fetch_in_progress:
            if auto:
                self.refresh_sync_schedule()
            return

        self.sync_fetch_in_progress = True
        if not auto:
            self.status_var.set(self.t("status.fetching_doc"))

        worker = threading.Thread(target=self._fetch_doc_worker, args=(source, auto), daemon=True)
        worker.start()
        self._schedule_sync_result_processing()

    def _fetch_doc_worker(self, source: str, auto: bool) -> None:
        try:
            text = fetch_google_doc_text(source)
        except SyncFetchError as exc:
            self.sync_result_queue.put(("sync_error", (exc.message_key, exc.context), auto))
            return
        except Exception as exc:
            self.sync_result_queue.put(("unknown_error", str(exc), auto))
            return

        self.sync_result_queue.put(("success", text, auto))

    def _handle_fetch_success(self, text: str, auto: bool) -> None:
        self.sync_fetch_in_progress = False
        self.sync_text.delete("1.0", "end")
        self.sync_text.insert("1.0", text)
        parsed = parse_sync_text(text)
        applied, skipped = self._apply_parsed_data(parsed)
        self.persist_and_refresh()
        if auto:
            self.refresh_sync_schedule()

        if parsed.issues:
            if skipped:
                self.status_var.set(
                    self.t(
                        "status.sync_applied_with_issues_skipped",
                        applied=applied,
                        skipped=skipped,
                        issues=len(parsed.issues),
                    )
                )
            else:
                self.status_var.set(self.t("status.sync_applied_with_issues", applied=applied, issues=len(parsed.issues)))
            if not auto:
                messagebox.showwarning(self.t("dialog.parse_issues.title"), "\n".join(self.format_parse_issues(parsed.issues)))
        else:
            if skipped:
                self.status_var.set(self.t("status.doc_fetched_skipped", applied=applied, skipped=skipped))
            else:
                self.status_var.set(self.t("status.doc_fetched", applied=applied))

    def _handle_fetch_failure(self, message: str, auto: bool) -> None:
        self.sync_fetch_in_progress = False
        if auto:
            self.refresh_sync_schedule()
        self.status_var.set(self.t("status.fetch_failed", message=message))
        if not auto:
            messagebox.showwarning(self.t("dialog.fetch_failed.title"), message)

    def apply_sync_text(self) -> None:
        self.save_sync_settings()
        parsed = parse_sync_text(self.sync_text.get("1.0", "end"))
        applied, skipped = self._apply_parsed_data(parsed)

        self.persist_and_refresh()
        if parsed.issues:
            if skipped:
                self.status_var.set(
                    self.t(
                        "status.sync_applied_with_issues_skipped",
                        applied=applied,
                        skipped=skipped,
                        issues=len(parsed.issues),
                    )
                )
            else:
                self.status_var.set(self.t("status.sync_applied_with_issues", applied=applied, issues=len(parsed.issues)))
            messagebox.showwarning(self.t("dialog.parse_issues.title"), "\n".join(self.format_parse_issues(parsed.issues)))
        else:
            if skipped:
                self.status_var.set(self.t("status.sync_applied_skipped", applied=applied, skipped=skipped))
            else:
                self.status_var.set(self.t("status.sync_applied", applied=applied))

    def _apply_parsed_data(self, parsed: ParsedSyncData) -> tuple[int, int]:
        applied = 0
        skipped_names: set[str] = set()
        for line in parsed.hp_lines:
            match = self._find_player_by_name(line.name)
            if match is None:
                if self.state.sync.existing_only:
                    skipped_names.add(line.name.casefold())
                    continue
                self.state.players.append(
                    Player(
                        name=line.name,
                        current_hp=line.current_hp,
                        max_hp=line.max_hp,
                        temp_hp=line.temp_hp,
                    )
                )
            else:
                match.name = line.name
                match.set_max_hp(line.max_hp)
                match.set_current_hp(line.current_hp)
                match.set_temp_hp(line.temp_hp)
            applied += 1

        for section in parsed.money_sections:
            match = self._find_player_by_name(section.name)
            if match is None:
                skipped_names.add(section.name.casefold())
                continue
            match.set_money(section.money.get("cc", 0), section.money.get("sc", 0), section.money.get("gc", 0))
            applied += 1

        for section in parsed.spell_sections:
            match = self._find_player_by_name(section.name)
            if match is None:
                skipped_names.add(section.name.casefold())
                continue
            match.replace_spell_slots(section.slots)
            applied += 1

        return applied, len(skipped_names)

    def load_sync_example(self) -> None:
        if self.state.locale == "ru":
            example = (
                ">>>\n"
                "Имя: Аэла Свифт\n"
                "Здоровье: 18/24\n"
                "Монеты: 4 зм 3 см 1 мм\n"
                "\n"
                "Имя: Борин Спенсер\n"
                "Монеты: 5 зм 0 см 2 мм\n"
                "Здоровье: 7/31 (5)\n"
                "\n"
                "Имя: Сайра Вейл\n"
                "Здоровье: 2/16\n"
                "Монеты: 12 мм 7 см 42 зм\n"
                "Ячейки заклинаний:\n"
                "1: 4/4\n"
                "2: 3/3\n"
                "3: 2/3\n"
                "4: 1/1\n"
                "5: 0/0\n"
                "6: 0/0\n"
                "7: 0/0\n"
                "8: 0/0\n"
                "9: 0/0\n"
                ">>>\n"
            )
        else:
            example = (
                ">>>\n"
                "Name: Aela Swift\n"
                "Health: 18/24\n"
                "Coins: 4 gc 3 sc 1 cc\n"
                "\n"
                "Name: Borin Spencer\n"
                "Coins: 5 gc 0 sc 2 cc\n"
                "Health: 7/31 (5)\n"
                "\n"
                "Name: Cyra Vale\n"
                "Health: 2/16\n"
                "Coins: 12 cc 7 sc 42 gc\n"
                "Spell Slots:\n"
                "1: 4/4\n"
                "2: 3/3\n"
                "3: 2/3\n"
                "4: 1/1\n"
                "5: 0/0\n"
                "6: 0/0\n"
                "7: 0/0\n"
                "8: 0/0\n"
                "9: 0/0\n"
                ">>>\n"
            )
        self.sync_text.delete("1.0", "end")
        self.sync_text.insert("1.0", example)
        self.status_var.set(self.t("status.example_loaded"))

    def persist_and_refresh(self, status: str | None = None) -> None:
        self.save_sync_settings()
        save_state(self.state)
        self.refresh_all()
        if status:
            self.status_var.set(status)

    def refresh_all(self) -> None:
        existing_ids = {player.player_id for player in self.state.players}
        for stale_id in list(self.player_rows):
            if stale_id not in existing_ids:
                self.player_rows.pop(stale_id).destroy()
        for stale_id in list(self.player_windows):
            if stale_id not in existing_ids:
                self.close_player_window(stale_id)
        for stale_id in list(self.overlay_windows):
            if stale_id not in existing_ids:
                self.close_overlay(stale_id)
        for stale_id in list(self.money_windows):
            if stale_id not in existing_ids:
                self.close_money_window(stale_id)
        for stale_id in list(self.money_editors):
            if stale_id not in existing_ids:
                self.close_money_editor(stale_id)
        for stale_id in list(self.spell_windows):
            if stale_id not in existing_ids:
                self.close_spell_window(stale_id)
        for stale_id in list(self.spell_editors):
            if stale_id not in existing_ids:
                self.close_spell_editor(stale_id)

        for player in self.state.players:
            row = self.player_rows.get(player.player_id)
            if row is None:
                row = PlayerRow(self, self.rows_frame, player)
                row.frame.pack(fill="x", pady=4)
                self.player_rows[player.player_id] = row
            row.refresh(player)

            if player.player_id in self.player_windows:
                self.player_windows[player.player_id].refresh(player)
            if player.player_id in self.overlay_windows:
                self.overlay_windows[player.player_id].refresh(player)
            if player.player_id in self.money_windows:
                self.money_windows[player.player_id].refresh(player)
            if player.player_id in self.money_editors:
                self.money_editors[player.player_id].refresh(player)
            if player.player_id in self.spell_windows:
                self.spell_windows[player.player_id].refresh(player)
            if player.player_id in self.spell_editors:
                self.spell_editors[player.player_id].refresh(player)

        self.refresh_money_window()
        self.refresh_money_editors()
        self._on_rows_configure()
        if self.initiative_tracker_window is not None:
            self.initiative_tracker_window.refresh()

    def on_close(self) -> None:
        self.state.sync.enabled = self.sync_enabled_var.get()
        self.state.sync.source = self.sync_source_var.get().strip()
        self.state.sync.existing_only = self.sync_existing_only_var.get()
        try:
            self.state.sync.poll_seconds = max(5, int(self.sync_poll_var.get()))
        except ValueError:
            self.state.sync.poll_seconds = 15
        if self.sync_after_id is not None:
            self.root.after_cancel(self.sync_after_id)
            self.sync_after_id = None
        if self.sync_result_after_id is not None:
            self.root.after_cancel(self.sync_result_after_id)
            self.sync_result_after_id = None
        if self.initiative_tracker_window is not None:
            self.initiative_tracker_window.close()
        save_state(self.state)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    app = HealthPointsApp()
    app.run()
