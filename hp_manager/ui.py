from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from hp_manager.localization import Localizer, SUPPORTED_LOCALES
from hp_manager.models import AppState, Player
from hp_manager.paths import asset_path
from hp_manager.storage import load_state, save_state
from hp_manager.sync import ParseIssue, ParsedSyncLine, SyncFetchError, fetch_google_doc_text, parse_sync_text


WINDOW_MIN_WIDTH = 1060
WINDOW_MIN_HEIGHT = 560
OVERLAY_SIZE = 220
TRANSPARENT_KEY = "#00ff00"
ICON_PATH = asset_path("app.ico")
OVERLAY_TITLE_HEIGHT = 30


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


class PlayerWindow:
    def __init__(self, app: "HealthPointsApp", player: Player) -> None:
        self.app = app
        self.player_id = player.player_id
        self.window = tk.Toplevel(app.root)
        self.window.title("")
        self.window.geometry("360x170")
        self.window.minsize(320, 150)
        self.window.attributes("-topmost", True)
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
        self.hp_label.config(text=f"{player.current_hp} / {player.max_hp}", fg=_hp_text_color(player.hp_ratio))
        self.temp_label.config(text=self.app.t("player.temp_hp", temp_hp=player.temp_hp))
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
        self.window.attributes("-topmost", True)
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
        for column in range(2):
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
        self.overlay_button.grid(row=0, column=1, sticky="ew")

        self.remove_button = ttk.Button(self.actions_secondary, command=self.remove_player)
        self.remove_button.grid(row=0, column=0, columnspan=2, sticky="ew")

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
            self.actions_secondary.grid_remove()
        else:
            self.name_value_label.grid_remove()
            self.name_label.grid()
            self.name_entry.grid()
            self.stats_frame.grid()
            self.actions_primary.grid()
            self.actions_secondary.grid()

        self.window_button.config(
            text=self.app.t("action.hide_window") if self.player_id in self.app.player_windows else self.app.t("action.player_window")
        )
        self.overlay_button.config(
            text=self.app.t("action.hide_overlay") if self.player_id in self.app.overlay_windows else self.app.t("action.overlay")
        )
        self.save_button.config(text=self.app.t("action.apply"))
        self.remove_button.config(text=self.app.t("action.remove"))
        self.damage_button.config(text=self.app.t("action.damage"))
        self.heal_button.config(text=self.app.t("action.heal"))

    def destroy(self) -> None:
        self.frame.destroy()


class HealthPointsApp:
    def __init__(self) -> None:
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

        self.status_var = tk.StringVar(value=self.t("status.ready"))
        self.add_name_var = tk.StringVar()
        self.add_current_var = tk.StringVar(value="10")
        self.add_max_var = tk.StringVar(value="10")
        self.add_temp_var = tk.StringVar(value="0")
        self.sync_enabled_var = tk.BooleanVar(value=self.state.sync.enabled)
        self.sync_source_var = tk.StringVar(value=self.state.sync.source)
        self.sync_poll_var = tk.StringVar(value=str(self.state.sync.poll_seconds))
        self.locale_display_var = tk.StringVar(value=self.localizer.locale_name(self.state.locale))
        self.overlay_ratio_var = tk.StringVar(value=self.state.overlay.aspect_ratio)
        self.overlay_show_title_var = tk.BooleanVar(value=self.state.overlay.show_title)
        self.layout_mode = ""
        self.sync_after_id: str | None = None
        self.sync_fetch_in_progress = False

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
            window.iconbitmap(default=str(ICON_PATH.resolve()))
        except tk.TclError:
            return

    def sync_mode_active(self) -> bool:
        return bool(self.state.sync.enabled)

    def right_panel_visible(self) -> bool:
        return bool(self.state.sync.visible or self.state.overlay.panel_visible)

    def overlay_ratio_label_for_code(self, code: str) -> str:
        normalized = code if code in {"1:1", "4:3"} else "1:1"
        return self.t(f"overlay.aspect.{normalized}")

    def overlay_ratio_code_from_label(self, label: str) -> str:
        for code in ("1:1", "4:3"):
            if label == self.overlay_ratio_label_for_code(code):
                return code
        return "1:1"

    def overlay_dimensions(self, base_size: int) -> tuple[int, int]:
        base = max(60, min(600, int(base_size)))
        if self.state.overlay.aspect_ratio == "4:3":
            width = base
            height = max(45, int(base * 3 / 4))
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
        card.rowconfigure(4, weight=1)
        self.sync_card = card

        self.sync_enable_check = ttk.Checkbutton(card, variable=self.sync_enabled_var, command=self.save_sync_settings)
        self.sync_enable_check.grid(row=0, column=0, columnspan=2, sticky="w")
        self.sync_source_label = ttk.Label(card)
        self.sync_source_label.grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(card, textvariable=self.sync_source_var).grid(row=1, column=1, sticky="ew", pady=(12, 0))
        self.sync_poll_label = ttk.Label(card)
        self.sync_poll_label.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(card, textvariable=self.sync_poll_var, width=8).grid(row=2, column=1, sticky="w", pady=(12, 0))
        self.sync_help_label = ttk.Label(card, style="Muted.TLabel")
        self.sync_help_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 8))

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
        self.sync_text.grid(row=4, column=0, columnspan=2, sticky="nsew")

        button_row = ttk.Frame(card)
        button_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
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
        self.state.overlay.show_title = self.overlay_show_title_var.get()
        save_state(self.state)
        self.refresh_overlay_windows()

    def refresh_overlay_windows(self) -> None:
        for player_id, overlay in list(self.overlay_windows.items()):
            player = self.player_by_id(player_id)
            if player is None:
                continue
            base = self.overlay_base_from_size(overlay.window.winfo_width(), overlay.window.winfo_height())
            width, height = self.overlay_dimensions(base)
            overlay.window.geometry(f"{width}x{height}+{overlay.window.winfo_x()}+{overlay.window.winfo_y()}")
            overlay.refresh(player)

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
        self.sync_source_label.config(text=self.t("label.source"))
        self.sync_poll_label.config(text=self.t("label.poll_seconds"))
        self.sync_help_label.config(text=self.t("sync.help"))
        self.fetch_doc_button.config(text=self.t("action.fetch_doc"))
        self.apply_sync_button.config(text=self.t("action.apply_parsed_lines"))
        self.load_example_button.config(text=self.t("action.load_example"))
        self.sync_toggle_button.config(
            text=self.t("action.hide_sync") if self.state.sync.visible else self.t("action.show_sync")
        )
        self.settings_toggle_button.config(
            text=self.t("action.hide_settings") if self.state.overlay.panel_visible else self.t("action.show_settings")
        )
        self.overlay_settings_card.config(text=self.t("card.overlay_settings"))
        self.overlay_ratio_label.config(text=self.t("label.overlay_ratio"))
        self.overlay_ratio_combo.config(
            values=[
                self.t("overlay.aspect.1:1"),
                self.t("overlay.aspect.4:3"),
            ]
        )
        self.overlay_ratio_combo.set(self.t(f"overlay.aspect.{self.state.overlay.aspect_ratio}"))
        self.overlay_title_check.config(text=self.t("overlay.show_title"))
        self.overlay_show_title_var.set(self.state.overlay.show_title)
        if self.state.sync.visible:
            self.sync_card.grid()
        else:
            self.sync_card.grid_remove()
        if self.state.overlay.panel_visible:
            self.overlay_settings_card.grid()
        else:
            self.overlay_settings_card.grid_remove()
        self.refresh_sync_mode_visibility()

    def refresh_sync_mode_visibility(self) -> None:
        if self.sync_mode_active():
            self.add_player_card.grid_remove()
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

    def save_sync_settings(self) -> None:
        self.state.sync.enabled = self.sync_enabled_var.get()
        self.state.sync.source = self.sync_source_var.get().strip()
        try:
            self.state.sync.poll_seconds = max(5, int(self.sync_poll_var.get()))
        except ValueError:
            self.state.sync.poll_seconds = 15
            self.sync_poll_var.set("15")
        self.refresh_sync_mode_visibility()
        self.refresh_all()
        self.refresh_sync_schedule()

    def refresh_sync_schedule(self) -> None:
        if self.sync_after_id is not None:
            self.root.after_cancel(self.sync_after_id)
            self.sync_after_id = None

        if self.state.sync.enabled and self.state.sync.source.strip():
            delay_ms = max(5, self.state.sync.poll_seconds) * 1000
            self.sync_after_id = self.root.after(delay_ms, self._poll_sync_source)

    def _poll_sync_source(self) -> None:
        self.sync_after_id = None
        self.fetch_doc_now(auto=True)

    def fetch_doc_now(self, auto: bool = False) -> None:
        self.save_sync_settings()
        source = self.state.sync.source.strip()
        if not source:
            if not auto:
                self.status_var.set(self.t("status.sync_source_missing"))
            return

        if self.sync_fetch_in_progress:
            return

        self.sync_fetch_in_progress = True
        if not auto:
            self.status_var.set(self.t("status.fetching_doc"))

        worker = threading.Thread(target=self._fetch_doc_worker, args=(source, auto), daemon=True)
        worker.start()

    def _fetch_doc_worker(self, source: str, auto: bool) -> None:
        try:
            text = fetch_google_doc_text(source)
        except SyncFetchError as exc:
            self.root.after(0, lambda: self._handle_fetch_failure(self.t(exc.message_key, **exc.context), auto))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._handle_fetch_failure(self.t("error.sync.unknown", message=str(exc)), auto))
            return

        self.root.after(0, lambda: self._handle_fetch_success(text, auto))

    def _handle_fetch_success(self, text: str, auto: bool) -> None:
        self.sync_fetch_in_progress = False
        self.sync_text.delete("1.0", "end")
        self.sync_text.insert("1.0", text)
        parsed, errors = parse_sync_text(text)
        applied = self._apply_parsed_lines(parsed)
        self.persist_and_refresh()

        if errors:
            self.status_var.set(self.t("status.sync_applied_with_issues", applied=applied, issues=len(errors)))
            if not auto:
                messagebox.showwarning(self.t("dialog.parse_issues.title"), "\n".join(self.format_parse_issues(errors)))
        else:
            self.status_var.set(self.t("status.doc_fetched", applied=applied))

    def _handle_fetch_failure(self, message: str, auto: bool) -> None:
        self.sync_fetch_in_progress = False
        self.status_var.set(self.t("status.fetch_failed", message=message))
        if not auto:
            messagebox.showwarning(self.t("dialog.fetch_failed.title"), message)

    def apply_sync_text(self) -> None:
        self.save_sync_settings()
        parsed, errors = parse_sync_text(self.sync_text.get("1.0", "end"))
        applied = self._apply_parsed_lines(parsed)

        self.persist_and_refresh()
        if errors:
            self.status_var.set(self.t("status.sync_applied_with_issues", applied=applied, issues=len(errors)))
            messagebox.showwarning(self.t("dialog.parse_issues.title"), "\n".join(self.format_parse_issues(errors)))
        else:
            self.status_var.set(self.t("status.sync_applied", applied=applied))

    def _apply_parsed_lines(self, parsed_lines: list[ParsedSyncLine]) -> int:
        applied = 0
        for line in parsed_lines:
            match = self._find_player_by_name(line.name)
            if match is None:
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
        return applied

    def load_sync_example(self) -> None:
        example = "Aela Swift: 18/24\nBorin Spencer: 7/31 (5)\nCyra Vale: 2/16\n"
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

        self._on_rows_configure()

    def on_close(self) -> None:
        self.state.sync.enabled = self.sync_enabled_var.get()
        self.state.sync.source = self.sync_source_var.get().strip()
        try:
            self.state.sync.poll_seconds = max(5, int(self.sync_poll_var.get()))
        except ValueError:
            self.state.sync.poll_seconds = 15
        if self.sync_after_id is not None:
            self.root.after_cancel(self.sync_after_id)
            self.sync_after_id = None
        save_state(self.state)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    app = HealthPointsApp()
    app.run()
