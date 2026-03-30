from __future__ import annotations

import math
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from hp_manager.models import InitiativeCombatant
from hp_manager.paths import bundled_portraits_dir, user_portraits_dir

if TYPE_CHECKING:
    from hp_manager.ui import HealthPointsApp


PORTRAIT_EXTENSIONS = {".png", ".gif", ".ppm", ".pgm"}
TRANSPARENT_KEY = "#00ff00"


def _safe_int(value: str | int, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _relative_to(path: Path, base: Path) -> Path | None:
    try:
        return path.resolve().relative_to(base.resolve())
    except ValueError:
        return None


class InitiativeObsWindow:
    def __init__(self, tracker: "InitiativeTrackerWindow") -> None:
        self.tracker = tracker
        self.window = tk.Toplevel(tracker.window)
        self.window.geometry("980x260")
        self.window.minsize(520, 220)
        self.window.configure(bg="#0e1014")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.tracker.app.apply_window_icon(self.window)
        self.tracker.app.apply_topmost(self.window, self.tracker.app.state.initiative.obs_topmost)
        self.tracker.app.enable_transparent_background(self.window)

        self.header = tk.Frame(self.window, bg="#0e1014")
        self.header.pack(fill="x", padx=18, pady=(16, 10))

        self.round_label = tk.Label(self.header, bg="#0e1014", fg="#f4f5f7", font=("Segoe UI Semibold", 20))
        self.round_label.pack(side="left")
        self.current_label = tk.Label(self.header, bg="#0e1014", fg="#b6c2d0", font=("Segoe UI", 14))
        self.current_label.pack(side="right")

        self.cards_frame = tk.Frame(self.window, bg="#0e1014")
        self.cards_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.refresh()

    def _required_width(self, combatants: list[InitiativeCombatant], current_initiative: int | None) -> int:
        if not combatants:
            return 520
        side_padding = 36
        card_gap = 10
        card_widths = []
        for combatant in combatants:
            is_same_turn = current_initiative is not None and combatant.initiative == current_initiative
            portrait_size = 132 if is_same_turn else 112
            card_widths.append(portrait_size + 28)
        return max(520, side_padding + sum(card_widths) + card_gap * max(0, len(card_widths) - 1))

    def refresh(self) -> None:
        state = self.tracker.app.state.initiative
        background_visible = state.obs_background
        base_bg = "#0e1014" if background_visible else TRANSPARENT_KEY
        self.window.title(self.tracker.t("initiative.obs_title"))
        current = self.tracker.current_combatant()
        current_initiative = current.initiative if current is not None and state.started else None
        required_width = self._required_width(state.combatants, current_initiative)
        self.window.minsize(required_width, 220)
        current_width = self.window.winfo_width()
        if current_width <= 1:
            current_width = self.window.winfo_reqwidth()
        if current_width < required_width:
            self.window.geometry(f"{required_width}x{max(220, self.window.winfo_height())}+{self.window.winfo_x()}+{self.window.winfo_y()}")
        self.window.configure(bg=base_bg)
        self.header.configure(bg=base_bg)
        self.cards_frame.configure(bg=base_bg)
        self.round_label.config(text=self.tracker.t("initiative.round_label", round_number=state.round_number))
        if current is not None and state.started:
            self.current_label.config(text=self.tracker.t("initiative.current_turn", name=current.name))
        else:
            self.current_label.config(text=self.tracker.t("initiative.not_started"))
        self.round_label.config(bg=base_bg)
        self.current_label.config(bg=base_bg)
        self.tracker.app.apply_topmost(self.window, state.obs_topmost)

        for child in self.cards_frame.winfo_children():
            child.destroy()

        combatants = state.combatants
        if not combatants:
            empty = tk.Label(
                self.cards_frame,
                bg="#12161d",
                fg="#b6c2d0",
                text=self.tracker.t("initiative.empty_obs"),
                font=("Segoe UI", 14),
                padx=24,
                pady=24,
            )
            empty.pack(fill="both", expand=True)
            return

        for index, combatant in enumerate(combatants):
            is_current = state.started and index == state.current_turn_index
            is_same_turn = current_initiative is not None and combatant.initiative == current_initiative
            card_bg = "#25241e" if is_current else "#22211b" if is_same_turn else "#171c24"
            outline = "#e4c16a" if is_current else "#c79761" if is_same_turn else "#2b3440"
            portrait_size = 132 if is_same_turn else 112
            top_padding = 0 if is_same_turn else 20
            card = tk.Frame(
                self.cards_frame,
                bg=card_bg,
                highlightthickness=2,
                highlightbackground=outline,
            )
            card.pack(side="left", fill="y", padx=(0, 10), pady=(top_padding, 0))

            portrait = self.tracker.create_portrait_widget(card, combatant.portrait_ref, size=portrait_size, background=card["bg"])
            portrait.pack(padx=12, pady=(12, 10 if is_same_turn else 12))

            name_label = tk.Label(
                card,
                bg=card["bg"],
                fg="#f4f5f7",
                text=combatant.name,
                font=("Segoe UI Semibold", 13 if is_same_turn else 12),
                width=14,
                anchor="center",
            )
            name_label.pack(fill="x", padx=10, pady=(0, 14 if is_same_turn else 18))

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.tracker.unregister_obs_window()


class InitiativeCombatantRow:
    def __init__(self, tracker: "InitiativeTrackerWindow", parent: ttk.Frame, combatant: InitiativeCombatant) -> None:
        self.tracker = tracker
        self.combatant_id = combatant.combatant_id
        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=10)
        self.frame.columnconfigure(1, weight=1)

        self.portrait_container = tk.Frame(self.frame, bg="#171a1f")
        self.portrait_container.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 10))

        self.name_var = tk.StringVar(value=combatant.name)
        self.initiative_var = tk.StringVar(value=str(combatant.initiative))

        self.status_label = ttk.Label(self.frame, style="Muted.TLabel")
        self.status_label.grid(row=0, column=1, sticky="w")

        edit_row = ttk.Frame(self.frame)
        edit_row.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        edit_row.columnconfigure(0, weight=1)

        self.name_entry = ttk.Entry(edit_row, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.initiative_entry = ttk.Entry(edit_row, textvariable=self.initiative_var, width=8)
        self.initiative_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.apply_button = ttk.Button(edit_row, command=self.apply_edits)
        self.apply_button.grid(row=0, column=2, sticky="ew")

        actions = ttk.Frame(self.frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for column in range(5):
            actions.columnconfigure(column, weight=1)

        self.assign_button = ttk.Button(actions, command=self.assign_selected_portrait)
        self.assign_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.clear_button = ttk.Button(actions, command=self.clear_portrait)
        self.clear_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.up_button = ttk.Button(actions, command=self.move_up)
        self.up_button.grid(row=0, column=2, sticky="ew", padx=4)
        self.down_button = ttk.Button(actions, command=self.move_down)
        self.down_button.grid(row=0, column=3, sticky="ew", padx=4)
        self.remove_button = ttk.Button(actions, command=self.remove)
        self.remove_button.grid(row=0, column=4, sticky="ew", padx=(4, 0))

        self.name_entry.bind("<Return>", lambda _event: self.apply_edits())
        self.initiative_entry.bind("<Return>", lambda _event: self.apply_edits())
        self.refresh(combatant)

    def _render_portrait(self, combatant: InitiativeCombatant) -> None:
        for child in self.portrait_container.winfo_children():
            child.destroy()
        widget = self.tracker.create_portrait_widget(self.portrait_container, combatant.portrait_ref, size=72, background="#171a1f")
        widget.pack()

    def apply_edits(self) -> None:
        combatant = self.tracker.combatant_by_id(self.combatant_id)
        if combatant is None:
            return
        combatant.name = self.tracker.app.localized_player_name(self.name_var.get())
        combatant.initiative = _safe_int(self.initiative_var.get(), combatant.initiative)
        self.tracker.persist(self.tracker.t("initiative.status.updated", name=combatant.name))

    def assign_selected_portrait(self) -> None:
        combatant = self.tracker.combatant_by_id(self.combatant_id)
        if combatant is None:
            return
        selected = self.tracker.selected_portrait_ref()
        if not selected:
            self.tracker.set_status(self.tracker.t("initiative.status.no_portrait_selected"))
            return
        combatant.portrait_ref = selected
        self.tracker.persist(self.tracker.t("initiative.status.portrait_assigned", name=combatant.name))

    def clear_portrait(self) -> None:
        combatant = self.tracker.combatant_by_id(self.combatant_id)
        if combatant is None:
            return
        combatant.portrait_ref = ""
        self.tracker.persist(self.tracker.t("initiative.status.portrait_cleared", name=combatant.name))

    def move_up(self) -> None:
        self.tracker.move_combatant(self.combatant_id, -1)

    def move_down(self) -> None:
        self.tracker.move_combatant(self.combatant_id, 1)

    def remove(self) -> None:
        self.tracker.remove_combatant(self.combatant_id)

    def refresh(self, combatant: InitiativeCombatant) -> None:
        self._render_portrait(combatant)
        self.name_var.set(combatant.name)
        self.initiative_var.set(str(combatant.initiative))
        state = self.tracker.app.state.initiative
        index = self.tracker.combatant_index(self.combatant_id)
        is_current = state.started and index == state.current_turn_index
        self.status_label.config(
            text=self.tracker.t("initiative.current_marker") if is_current else self.tracker.t("initiative.ready_marker")
        )
        self.apply_button.config(text=self.tracker.t("action.apply"))
        self.assign_button.config(text=self.tracker.t("initiative.action.use_selected_portrait"))
        self.clear_button.config(text=self.tracker.t("initiative.action.clear_portrait"))
        self.up_button.config(text=self.tracker.t("initiative.action.move_up"))
        self.down_button.config(text=self.tracker.t("initiative.action.move_down"))
        self.remove_button.config(text=self.tracker.t("action.remove"))

    def destroy(self) -> None:
        self.frame.destroy()


class InitiativeTrackerWindow:
    def __init__(self, app: "HealthPointsApp") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.geometry("1280x760")
        self.window.minsize(980, 620)
        self.window.configure(bg="#101214")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.app.apply_window_icon(self.window)

        self.status_var = tk.StringVar(value=self.t("initiative.status.ready"))
        self.search_var = tk.StringVar()
        self.add_name_var = tk.StringVar()
        self.add_initiative_var = tk.StringVar(value="0")
        player_names = [player.name for player in self.app.state.players] or [""]
        self.source_player_var = tk.StringVar(value=player_names[0])
        self.obs_topmost_var = tk.BooleanVar(value=self.app.state.initiative.obs_topmost)
        self.obs_background_var = tk.BooleanVar(value=self.app.state.initiative.obs_background)

        self.row_widgets: dict[str, InitiativeCombatantRow] = {}
        self.obs_window: InitiativeObsWindow | None = None
        self.portrait_cache: dict[tuple[str, int], tk.PhotoImage] = {}
        self.portrait_library: list[tuple[str, str]] = []
        self.library_refs_by_index: list[str] = []

        self._build_layout()
        self.refresh_library()
        self.refresh()

    def t(self, key: str, **kwargs: object) -> str:
        return self.app.t(key, **kwargs)

    def close(self) -> None:
        if self.obs_window is not None:
            self.obs_window.close()
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.unregister_initiative_tracker()

    def unregister_obs_window(self) -> None:
        self.obs_window = None
        self.refresh()

    def _build_layout(self) -> None:
        container = ttk.Frame(self.window, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(2, weight=1)
        self.container = container

        self.title_label = ttk.Label(container, style="Header.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(container, style="Muted.TLabel")
        self.subtitle_label.grid(row=0, column=1, sticky="e")

        top_left = ttk.Frame(container)
        top_left.grid(row=1, column=0, sticky="ew", pady=(16, 12), padx=(0, 8))
        top_left.columnconfigure(1, weight=1)
        top_left.columnconfigure(4, weight=1)

        self.add_name_label = ttk.Label(top_left)
        self.add_name_label.grid(row=0, column=0, sticky="w")
        self.add_name_entry = ttk.Entry(top_left, textvariable=self.add_name_var)
        self.add_name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 12))
        self.add_initiative_label = ttk.Label(top_left)
        self.add_initiative_label.grid(row=0, column=2, sticky="w")
        self.add_initiative_entry = ttk.Entry(top_left, textvariable=self.add_initiative_var, width=8)
        self.add_initiative_entry.grid(row=0, column=3, sticky="ew", padx=(8, 12))
        self.add_button = ttk.Button(top_left, command=self.add_combatant)
        self.add_button.grid(row=0, column=4, sticky="ew")

        player_row = ttk.Frame(top_left)
        player_row.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(10, 0))
        player_row.columnconfigure(1, weight=1)
        self.from_players_label = ttk.Label(player_row)
        self.from_players_label.grid(row=0, column=0, sticky="w")
        self.source_player_combo = ttk.Combobox(player_row, state="readonly", textvariable=self.source_player_var)
        self.source_player_combo.grid(row=0, column=1, sticky="ew", padx=(8, 12))
        self.add_from_player_button = ttk.Button(player_row, command=self.add_from_player)
        self.add_from_player_button.grid(row=0, column=2, sticky="ew")

        top_right = ttk.Frame(container)
        top_right.grid(row=1, column=1, sticky="ew", pady=(16, 12), padx=(8, 0))
        for column in range(6):
            top_right.columnconfigure(column, weight=1)

        self.start_button = ttk.Button(top_right, command=self.start_encounter)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.previous_button = ttk.Button(top_right, command=self.previous_turn)
        self.previous_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.next_button = ttk.Button(top_right, command=self.next_turn)
        self.next_button.grid(row=0, column=2, sticky="ew", padx=6)
        self.reset_button = ttk.Button(top_right, command=self.reset_encounter)
        self.reset_button.grid(row=0, column=3, sticky="ew", padx=6)
        self.clear_button = ttk.Button(top_right, command=self.clear_encounter)
        self.clear_button.grid(row=0, column=4, sticky="ew", padx=6)
        self.obs_button = ttk.Button(top_right, command=self.toggle_obs_window)
        self.obs_button.grid(row=0, column=5, sticky="ew", padx=(6, 0))

        self.obs_topmost_check = ttk.Checkbutton(top_right, variable=self.obs_topmost_var, command=self.toggle_obs_topmost)
        self.obs_topmost_check.grid(row=1, column=0, columnspan=6, sticky="w", pady=(10, 0))
        self.obs_background_check = ttk.Checkbutton(top_right, variable=self.obs_background_var, command=self.toggle_obs_background)
        self.obs_background_check.grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))

        self.encounter_card = ttk.LabelFrame(container, style="Section.TLabelframe", padding=10)
        self.encounter_card.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        self.encounter_card.columnconfigure(0, weight=1)
        self.encounter_card.rowconfigure(1, weight=1)

        self.encounter_header = ttk.Label(self.encounter_card, style="Muted.TLabel")
        self.encounter_header.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.canvas = tk.Canvas(self.encounter_card, bg="#101214", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.encounter_card, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.rows_frame = ttk.Frame(self.canvas)
        self.rows_window = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", self._on_rows_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.library_card = ttk.LabelFrame(container, style="Section.TLabelframe", padding=10)
        self.library_card.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
        self.library_card.columnconfigure(0, weight=1)
        self.library_card.rowconfigure(4, weight=1)

        self.search_label = ttk.Label(self.library_card)
        self.search_label.grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(self.library_card, textvariable=self.search_var)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        search_entry.bind("<KeyRelease>", lambda _event: self.refresh_library())

        self.preview_container = tk.Frame(self.library_card, bg="#101214")
        self.preview_container.grid(row=2, column=0, sticky="ew")
        self.preview_title = ttk.Label(self.library_card, style="Muted.TLabel")
        self.preview_title.grid(row=3, column=0, sticky="w", pady=(10, 6))

        list_frame = ttk.Frame(self.library_card)
        list_frame.grid(row=4, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.library_list = tk.Listbox(
            list_frame,
            bg="#141922",
            fg="#e7ebef",
            selectbackground="#243142",
            activestyle="none",
            highlightthickness=0,
        )
        self.library_list.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.library_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.library_list.configure(yscrollcommand=list_scroll.set)
        self.library_list.bind("<<ListboxSelect>>", lambda _event: self.refresh_library_preview())
        self.library_list.bind("<Double-Button-1>", lambda _event: self.assign_selected_to_new())

        library_actions = ttk.Frame(self.library_card)
        library_actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            library_actions.columnconfigure(column, weight=1)

        self.import_button = ttk.Button(library_actions, command=self.import_portraits)
        self.import_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.delete_button = ttk.Button(library_actions, command=self.delete_selected_portrait)
        self.delete_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.refresh_button = ttk.Button(library_actions, command=self.refresh_library)
        self.refresh_button.grid(row=0, column=2, sticky="ew", padx=6)
        self.use_selected_button = ttk.Button(library_actions, command=self.assign_selected_to_new)
        self.use_selected_button.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        self.status_label = ttk.Label(container, style="Muted.TLabel", textvariable=self.status_var)
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def _on_rows_configure(self, _event: object | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.rows_window, width=event.width)

    def set_status(self, status: str) -> None:
        self.status_var.set(status)

    def persist(self, status: str | None = None) -> None:
        self.app.persist_and_refresh(status=status)
        if status:
            self.status_var.set(status)

    def refresh_player_source_options(self) -> None:
        values = [player.name for player in self.app.state.players]
        self.source_player_combo.config(values=values)
        if values and self.source_player_var.get() not in values:
            self.source_player_var.set(values[0])
        elif not values:
            self.source_player_var.set("")

    def refresh(self) -> None:
        self.window.title(self.t("initiative.window_title"))
        self.title_label.config(text=self.t("initiative.header"))
        self.subtitle_label.config(text=self.t("initiative.subtitle"))
        self.add_name_label.config(text=self.t("label.name"))
        self.add_initiative_label.config(text=self.t("initiative.label.initiative"))
        self.add_button.config(text=self.t("initiative.action.add_combatant"))
        self.from_players_label.config(text=self.t("initiative.label.from_players"))
        self.add_from_player_button.config(text=self.t("initiative.action.add_from_players"))
        self.start_button.config(text=self.t("initiative.action.start"))
        self.previous_button.config(text=self.t("initiative.action.previous_turn"))
        self.next_button.config(text=self.t("initiative.action.next_turn"))
        self.reset_button.config(text=self.t("initiative.action.reset"))
        self.clear_button.config(text=self.t("initiative.action.clear"))
        self.obs_button.config(
            text=self.t("initiative.action.hide_obs") if self.obs_window is not None else self.t("initiative.action.show_obs")
        )
        self.obs_topmost_check.config(text=self.t("initiative.obs_topmost"))
        self.obs_background_check.config(text=self.t("initiative.obs_background"))
        self.obs_topmost_var.set(self.app.state.initiative.obs_topmost)
        self.obs_background_var.set(self.app.state.initiative.obs_background)
        self.encounter_card.config(text=self.t("initiative.card.encounter"))
        self.encounter_header.config(text=self.encounter_summary_text())
        self.library_card.config(text=self.t("initiative.card.library"))
        self.search_label.config(text=self.t("initiative.label.search"))
        self.preview_title.config(text=self.t("initiative.label.preview"))
        self.import_button.config(text=self.t("initiative.action.import_portraits"))
        self.delete_button.config(text=self.t("initiative.action.delete_portrait"))
        self.refresh_button.config(text=self.t("initiative.action.refresh_library"))
        self.use_selected_button.config(text=self.t("initiative.action.use_for_new"))

        self.refresh_player_source_options()
        combatants = self.app.state.initiative.combatants
        existing_ids = {combatant.combatant_id for combatant in combatants}
        for stale_id in list(self.row_widgets):
            if stale_id not in existing_ids:
                self.row_widgets.pop(stale_id).destroy()

        for combatant in combatants:
            row = self.row_widgets.get(combatant.combatant_id)
            if row is None:
                row = InitiativeCombatantRow(self, self.rows_frame, combatant)
                row.frame.pack(fill="x", pady=4)
                self.row_widgets[combatant.combatant_id] = row
            row.refresh(combatant)

        if self.obs_window is not None:
            self.obs_window.refresh()

        self.refresh_library_preview()
        self._on_rows_configure()

    def encounter_summary_text(self) -> str:
        state = self.app.state.initiative
        current = self.current_combatant()
        if state.started and current is not None:
            return self.t(
                "initiative.encounter_summary_started",
                count=len(state.combatants),
                round_number=state.round_number,
                current=current.name,
            )
        return self.t("initiative.encounter_summary_idle", count=len(state.combatants))

    def current_combatant(self) -> InitiativeCombatant | None:
        state = self.app.state.initiative
        if not state.combatants:
            return None
        index = max(0, min(state.current_turn_index, len(state.combatants) - 1))
        return state.combatants[index]

    def combatant_by_id(self, combatant_id: str) -> InitiativeCombatant | None:
        for combatant in self.app.state.initiative.combatants:
            if combatant.combatant_id == combatant_id:
                return combatant
        return None

    def combatant_index(self, combatant_id: str) -> int:
        for index, combatant in enumerate(self.app.state.initiative.combatants):
            if combatant.combatant_id == combatant_id:
                return index
        return -1

    def selected_portrait_ref(self) -> str:
        selection = self.library_list.curselection()
        if not selection:
            return ""
        index = selection[0]
        if 0 <= index < len(self.library_refs_by_index):
            return self.library_refs_by_index[index]
        return ""

    def refresh_library(self) -> None:
        selected = self.selected_portrait_ref()
        search = self.search_var.get().strip().lower()
        self.portrait_library = []

        bundle_dir = bundled_portraits_dir()
        if bundle_dir.exists():
            for path in sorted(bundle_dir.rglob("*")):
                if path.suffix.lower() not in PORTRAIT_EXTENSIONS or not path.is_file():
                    continue
                relative = _relative_to(path, bundle_dir)
                if relative is None:
                    continue
                ref = f"bundle:{relative.as_posix()}"
                label = f"{relative.stem} ({relative.parent.as_posix()})" if relative.parent != Path(".") else relative.stem
                self.portrait_library.append((label, ref))

        user_dir = user_portraits_dir()
        user_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(user_dir.rglob("*")):
            if path.suffix.lower() not in PORTRAIT_EXTENSIONS or not path.is_file():
                continue
            relative = _relative_to(path, user_dir)
            if relative is None:
                continue
            ref = f"user:{relative.as_posix()}"
            label = f"{relative.stem} ({relative.parent.as_posix()})" if relative.parent != Path(".") else relative.stem
            self.portrait_library.append((label, ref))

        self.library_list.delete(0, "end")
        self.library_refs_by_index = []
        selected_index = None
        filtered = sorted(self.portrait_library, key=lambda item: item[0].lower())
        for label, ref in filtered:
            if search and search not in label.lower():
                continue
            self.library_list.insert("end", label)
            self.library_refs_by_index.append(ref)
            if ref == selected:
                selected_index = len(self.library_refs_by_index) - 1

        if selected_index is not None:
            self.library_list.selection_set(selected_index)
            self.library_list.see(selected_index)
        elif self.library_refs_by_index:
            self.library_list.selection_set(0)
        self.refresh_library_preview()

    def resolve_portrait_path(self, portrait_ref: str) -> Path | None:
        if not portrait_ref:
            return None
        kind, _, value = portrait_ref.partition(":")
        if not value:
            return None
        relative = Path(value)
        if kind == "bundle":
            path = bundled_portraits_dir().joinpath(relative)
        elif kind == "user":
            path = user_portraits_dir().joinpath(relative)
        else:
            return None
        return path if path.exists() else None

    def get_portrait_image(self, portrait_ref: str, size: int) -> tk.PhotoImage | None:
        if not portrait_ref:
            return None
        cache_key = (portrait_ref, size)
        if cache_key in self.portrait_cache:
            return self.portrait_cache[cache_key]
        image_path = self.resolve_portrait_path(portrait_ref)
        if image_path is None:
            return None
        try:
            image = tk.PhotoImage(file=str(image_path))
        except tk.TclError:
            return None
        scale = max(1, math.ceil(max(image.width() / max(1, size), image.height() / max(1, size))))
        if scale > 1:
            image = image.subsample(scale, scale)
        self.portrait_cache[cache_key] = image
        return image

    def create_portrait_widget(self, parent: tk.Misc, portrait_ref: str, size: int, background: str) -> tk.Widget:
        image = self.get_portrait_image(portrait_ref, size)
        if image is not None:
            label = tk.Label(parent, image=image, bg=background, bd=0, highlightthickness=0)
            label.image = image
            return label
        canvas = tk.Canvas(parent, width=size, height=size, bg=background, highlightthickness=0, bd=0)
        canvas.create_rectangle(2, 2, size - 2, size - 2, fill="#1e2530", outline="#394455", width=2)
        canvas.create_text(
            size // 2,
            size // 2,
            text=self.t("initiative.no_portrait"),
            width=max(40, size - 16),
            fill="#d0dae8",
            font=("Segoe UI Semibold", max(10, size // 8)),
        )
        return canvas

    def refresh_library_preview(self) -> None:
        for child in self.preview_container.winfo_children():
            child.destroy()
        selected = self.selected_portrait_ref()
        if not selected:
            label = ttk.Label(self.preview_container, text=self.t("initiative.no_portrait_selected"))
            label.pack(anchor="w")
            return
        widget = self.create_portrait_widget(self.preview_container, selected, size=170, background="#101214")
        widget.pack(anchor="w")

    def assign_selected_to_new(self) -> None:
        selected = self.selected_portrait_ref()
        if not selected:
            self.set_status(self.t("initiative.status.no_portrait_selected"))
            return
        self.set_status(self.t("initiative.status.selected_portrait_ready"))

    def import_portraits(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.window,
            title=self.t("initiative.dialog.import_title"),
            filetypes=[
                (self.t("initiative.dialog.image_files"), "*.png *.gif *.ppm *.pgm"),
                (self.t("initiative.dialog.all_files"), "*.*"),
            ],
        )
        if not paths:
            return
        target_dir = user_portraits_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        imported = 0
        for raw_path in paths:
            source = Path(raw_path)
            if source.suffix.lower() not in PORTRAIT_EXTENSIONS or not source.exists():
                continue
            target = target_dir.joinpath(source.name)
            counter = 1
            while target.exists():
                target = target_dir.joinpath(f"{source.stem}_{counter}{source.suffix}")
                counter += 1
            shutil.copy2(source, target)
            imported += 1
        self.portrait_cache.clear()
        self.refresh_library()
        if imported:
            self.persist(self.t("initiative.status.imported_portraits", count=imported))

    def delete_selected_portrait(self) -> None:
        selected = self.selected_portrait_ref()
        if not selected:
            self.set_status(self.t("initiative.status.no_portrait_selected"))
            return
        if not selected.startswith("user:"):
            messagebox.showinfo(self.t("initiative.dialog.delete_title"), self.t("initiative.dialog.delete_readonly"))
            return
        if not messagebox.askyesno(self.t("initiative.dialog.delete_title"), self.t("initiative.dialog.delete_confirm")):
            return
        path = self.resolve_portrait_path(selected)
        if path is None:
            self.refresh_library()
            return
        try:
            path.unlink()
        except OSError:
            messagebox.showwarning(self.t("initiative.dialog.delete_title"), self.t("initiative.dialog.delete_failed"))
            return
        for combatant in self.app.state.initiative.combatants:
            if combatant.portrait_ref == selected:
                combatant.portrait_ref = ""
        self.portrait_cache.clear()
        self.refresh_library()
        self.persist(self.t("initiative.status.deleted_portrait"))

    def add_combatant(self) -> None:
        name = self.app.localized_player_name(self.add_name_var.get())
        initiative = _safe_int(self.add_initiative_var.get(), 0)
        portrait_ref = self.selected_portrait_ref()
        combatant = InitiativeCombatant(name=name, initiative=initiative, portrait_ref=portrait_ref)
        self.app.state.initiative.combatants.append(combatant)
        self.add_name_var.set("")
        self.add_initiative_var.set("0")
        self.persist(self.t("initiative.status.added", name=combatant.name))

    def add_from_player(self) -> None:
        source_name = self.source_player_var.get().strip()
        if not source_name:
            self.set_status(self.t("initiative.status.no_player_selected"))
            return
        initiative = _safe_int(self.add_initiative_var.get(), 0)
        portrait_ref = self.selected_portrait_ref()
        combatant = InitiativeCombatant(name=source_name, initiative=initiative, portrait_ref=portrait_ref)
        self.app.state.initiative.combatants.append(combatant)
        self.persist(self.t("initiative.status.added", name=combatant.name))

    def _remember_current(self) -> str:
        current = self.current_combatant()
        return current.combatant_id if current is not None else ""

    def _restore_current(self, current_id: str) -> None:
        state = self.app.state.initiative
        if not state.combatants:
            state.started = False
            state.current_turn_index = 0
            state.round_number = 1
            return
        if not state.started:
            state.current_turn_index = 0
            state.round_number = 1
            return
        for index, combatant in enumerate(state.combatants):
            if combatant.combatant_id == current_id:
                state.current_turn_index = index
                return
        state.current_turn_index = min(state.current_turn_index, len(state.combatants) - 1)

    def move_combatant(self, combatant_id: str, delta: int) -> None:
        state = self.app.state.initiative
        index = self.combatant_index(combatant_id)
        if index < 0:
            return
        target = index + delta
        if target < 0 or target >= len(state.combatants):
            return
        current_id = self._remember_current()
        state.combatants[index], state.combatants[target] = state.combatants[target], state.combatants[index]
        self._restore_current(current_id)
        self.persist(self.t("initiative.status.reordered"))

    def remove_combatant(self, combatant_id: str) -> None:
        state = self.app.state.initiative
        combatant = self.combatant_by_id(combatant_id)
        if combatant is None:
            return
        current_id = self._remember_current()
        state.combatants = [item for item in state.combatants if item.combatant_id != combatant_id]
        self._restore_current("" if current_id == combatant_id else current_id)
        self.persist(self.t("initiative.status.removed", name=combatant.name))

    def start_encounter(self) -> None:
        state = self.app.state.initiative
        if not state.combatants:
            self.set_status(self.t("initiative.status.no_combatants"))
            return
        state.combatants = sorted(enumerate(state.combatants), key=lambda item: (-item[1].initiative, item[0]))
        state.combatants = [combatant for _, combatant in state.combatants]
        state.started = True
        state.current_turn_index = 0
        state.round_number = 1
        self.persist(self.t("initiative.status.started"))

    def next_turn(self) -> None:
        state = self.app.state.initiative
        if not state.combatants:
            self.set_status(self.t("initiative.status.no_combatants"))
            return
        if not state.started:
            self.start_encounter()
            return
        if state.current_turn_index >= len(state.combatants) - 1:
            state.current_turn_index = 0
            state.round_number += 1
        else:
            state.current_turn_index += 1
        current = self.current_combatant()
        self.persist(self.t("initiative.status.turn_advanced", name=current.name if current else ""))

    def previous_turn(self) -> None:
        state = self.app.state.initiative
        if not state.combatants:
            self.set_status(self.t("initiative.status.no_combatants"))
            return
        if not state.started:
            self.start_encounter()
            return
        if state.current_turn_index <= 0:
            state.current_turn_index = len(state.combatants) - 1
            state.round_number = max(1, state.round_number - 1)
        else:
            state.current_turn_index -= 1
        current = self.current_combatant()
        self.persist(self.t("initiative.status.turn_rewound", name=current.name if current else ""))

    def reset_encounter(self) -> None:
        state = self.app.state.initiative
        state.started = False
        state.current_turn_index = 0
        state.round_number = 1
        self.persist(self.t("initiative.status.reset"))

    def clear_encounter(self) -> None:
        if not messagebox.askyesno(self.t("initiative.dialog.clear_title"), self.t("initiative.dialog.clear_confirm")):
            return
        self.app.state.initiative.combatants.clear()
        self.app.state.initiative.started = False
        self.app.state.initiative.current_turn_index = 0
        self.app.state.initiative.round_number = 1
        self.persist(self.t("initiative.status.cleared"))

    def toggle_obs_topmost(self) -> None:
        self.app.state.initiative.obs_topmost = self.obs_topmost_var.get()
        if self.obs_window is not None:
            self.obs_window.refresh()
        self.persist(self.t("initiative.status.obs_settings_saved"))

    def toggle_obs_background(self) -> None:
        self.app.state.initiative.obs_background = self.obs_background_var.get()
        if self.obs_window is not None:
            self.obs_window.refresh()
        self.persist(self.t("initiative.status.obs_settings_saved"))

    def toggle_obs_window(self) -> None:
        if self.obs_window is not None:
            self.obs_window.close()
        else:
            self.obs_window = InitiativeObsWindow(self)
        self.refresh()
