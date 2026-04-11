from __future__ import annotations

import math
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from hp_manager.models import InitiativeCombatant, InitiativeLibraryEntry
from hp_manager.paths import bundled_portraits_dir, user_portraits_dir
from hp_manager.storage import save_state

if TYPE_CHECKING:
    from hp_manager.ui import HealthPointsApp


PORTRAIT_EXTENSIONS = {".png", ".gif", ".ppm", ".pgm"}
TRANSPARENT_KEY = "#010203"
OBS_SLOT_OPTIONS = tuple(str(value) for value in range(4, 13))
INITIATIVE_COMPACT_BREAKPOINT = 1220
INITIATIVE_OBS_CARD_GAP = 3


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
        self.card_widgets: list[dict[str, tk.Widget]] = []
        self.empty_label: tk.Label | None = None
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
        self.cards_frame.grid_rowconfigure(0, weight=1)
        self.cards_frame.grid_columnconfigure(0, weight=1)

        self.cards_strip = tk.Frame(self.cards_frame, bg="#0e1014")
        self.cards_strip.grid(row=0, column=0)

        self.refresh()

    def _ensure_card_widgets(self, count: int) -> None:
        while len(self.card_widgets) < count:
            card = tk.Frame(self.cards_strip, highlightthickness=2)
            portrait_host = tk.Frame(card, bd=0, highlightthickness=0)
            portrait_host.pack(padx=12, pady=(12, 12))
            name_canvas = tk.Canvas(card, highlightthickness=0, bd=0)
            name_canvas.pack(fill="x", padx=10, pady=(0, 18))
            self.card_widgets.append(
                {
                    "card": card,
                    "portrait_host": portrait_host,
                    "name_label": name_canvas,
                    "portrait_widget": None,
                    "portrait_signature": None,
                }
            )

    def _hide_empty_state(self) -> None:
        if self.empty_label is not None:
            self.empty_label.grid_remove()

    def _show_empty_state(self, background: str) -> None:
        if self.empty_label is None:
            self.empty_label = tk.Label(
                self.cards_frame,
                fg="#b6c2d0",
                font=("Segoe UI", 14),
                padx=24,
                pady=24,
            )
        self.empty_label.config(
            bg=background,
            text=self.tracker.t("initiative.empty_obs"),
        )
        self.cards_strip.grid_remove()
        self.empty_label.grid(row=0, column=0, sticky="nsew")

    def _render_card(
        self,
        slot: dict[str, tk.Widget],
        combatant: InitiativeCombatant,
        is_current: bool,
        is_same_turn: bool,
        background_visible: bool,
        base_bg: str,
    ) -> None:
        card = slot["card"]
        portrait_host = slot["portrait_host"]
        name_canvas = slot["name_label"]
        portrait_widget = slot["portrait_widget"]
        if background_visible:
            card_bg = "#25241e" if is_current else "#22211b" if is_same_turn else "#171c24"
            outline = "#e4c16a" if is_current else "#c79761" if is_same_turn else "#2b3440"
            highlight = 2
            card_gap = INITIATIVE_OBS_CARD_GAP
            portrait_padx = 12
            portrait_pady = (12, 10 if is_same_turn else 12)
            name_padx = 10
            top_padding = 0 if is_same_turn else 20
        else:
            card_bg = base_bg
            outline = base_bg
            highlight = 0
            card_gap = INITIATIVE_OBS_CARD_GAP
            portrait_padx = 0
            portrait_pady = (0, 4)
            name_padx = 0
            top_padding = 0
        portrait_size = 132 if is_same_turn else 112
        card_width = portrait_size + portrait_padx * 2
        name_width = max(24, card_width - name_padx * 2)
        name_height = 44 if background_visible else 38

        card.configure(bg=card_bg, highlightbackground=outline, highlightthickness=highlight)
        portrait_host.configure(bg=card_bg)
        name_canvas.config(
            bg=card_bg,
            width=name_width,
            height=name_height,
        )
        name_canvas.delete("all")
        name_canvas.create_text(
            name_width // 2,
            2,
            anchor="n",
            fill="#f4f5f7",
            text=combatant.name,
            font=("Segoe UI Semibold", 13 if is_same_turn else 12),
            width=name_width,
            justify="center",
        )

        if card.winfo_manager():
            card.pack_configure(side="left", fill="y", padx=(0, card_gap), pady=(top_padding, 0))
        else:
            card.pack(side="left", fill="y", padx=(0, card_gap), pady=(top_padding, 0))
        portrait_host.pack_configure(padx=portrait_padx, pady=portrait_pady)
        name_canvas.pack_configure(padx=name_padx, pady=(0, 0))

        portrait_signature = (combatant.portrait_ref, portrait_size, card_bg)
        if portrait_signature != slot["portrait_signature"] or portrait_widget is None:
            portrait = self.tracker.refresh_portrait_widget(
                portrait_widget,
                portrait_host,
                combatant.portrait_ref,
                size=portrait_size,
                background=card_bg,
            )
            if portrait is not portrait_widget or not portrait.winfo_manager():
                portrait.pack()
            slot["portrait_widget"] = portrait
            slot["portrait_signature"] = portrait_signature

    def _fixed_width(self, slot_count: int) -> int:
        side_padding = 36
        slot_width = 132 + 24
        return side_padding + slot_width * slot_count + INITIATIVE_OBS_CARD_GAP * (slot_count - 1)

    def _visible_combatants(self, state: object) -> list[tuple[int, InitiativeCombatant]]:
        combatants = self.tracker.app.state.initiative.combatants
        if not combatants:
            return []
        slot_count = self.tracker.app.state.initiative.obs_visible_slots
        if len(combatants) <= slot_count:
            return list(enumerate(combatants))

        start_index = 0
        if self.tracker.app.state.initiative.started:
            start_index = max(0, min(self.tracker.app.state.initiative.current_turn_index, len(combatants) - 1))

        ordered: list[tuple[int, InitiativeCombatant]] = []
        for offset in range(min(slot_count, len(combatants))):
            actual_index = (start_index + offset) % len(combatants)
            ordered.append((actual_index, combatants[actual_index]))
        return ordered

    def _required_height(self, combatants: list[InitiativeCombatant], current_initiative: int | None) -> int:
        if not combatants:
            return 220
        largest_portrait = max(
            132 if current_initiative is not None and combatant.initiative == current_initiative else 112
            for combatant in combatants
        )
        header_block = 72
        card_vertical_space = largest_portrait + 64
        return max(220, header_block + card_vertical_space + 18)

    def refresh(self) -> None:
        state = self.tracker.app.state.initiative
        background_visible = state.obs_background
        base_bg = "#0e1014" if background_visible else TRANSPARENT_KEY
        self.window.title(self.tracker.t("initiative.obs_title"))
        current = self.tracker.current_combatant()
        current_initiative = current.initiative if current is not None and state.started else None
        required_height = self._required_height(state.combatants, current_initiative)
        min_width = self._fixed_width(state.obs_visible_slots)
        self.window.minsize(min_width, required_height)
        current_width = self.window.winfo_width()
        current_height = self.window.winfo_height()
        if current_width <= 1:
            current_width = self.window.winfo_reqwidth()
        if current_height <= 1:
            current_height = self.window.winfo_reqheight()
        target_width = self._fixed_width(state.obs_visible_slots)
        target_height = max(required_height, current_height)
        if target_width != current_width or target_height != current_height:
            self.window.geometry(f"{target_width}x{target_height}+{self.window.winfo_x()}+{self.window.winfo_y()}")
        self.window.configure(bg=base_bg)
        self.header.configure(bg=base_bg)
        self.cards_frame.configure(bg=base_bg)
        self.cards_strip.configure(bg=base_bg)
        self.round_label.config(text=self.tracker.t("initiative.round_label", round_number=state.round_number))
        if current is not None and state.started:
            self.current_label.config(text=self.tracker.t("initiative.current_turn", name=current.name))
        else:
            self.current_label.config(text=self.tracker.t("initiative.not_started"))
        self.round_label.config(bg=base_bg)
        self.current_label.config(bg=base_bg)
        self.tracker.app.apply_topmost(self.window, state.obs_topmost)

        visible_combatants = self._visible_combatants(state)
        if not visible_combatants:
            for slot in self.card_widgets:
                slot["card"].pack_forget()
            self._show_empty_state(base_bg)
            return

        self._hide_empty_state()
        self.cards_strip.grid()
        self._ensure_card_widgets(len(visible_combatants))

        for slot_index, (actual_index, combatant) in enumerate(visible_combatants):
            is_current = state.started and actual_index == state.current_turn_index
            is_same_turn = current_initiative is not None and combatant.initiative == current_initiative
            self._render_card(
                self.card_widgets[slot_index],
                combatant,
                is_current=is_current,
                is_same_turn=is_same_turn,
                background_visible=background_visible,
                base_bg=base_bg,
            )

        for slot in self.card_widgets[len(visible_combatants) :]:
            slot["card"].pack_forget()

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.tracker.unregister_obs_window()


class InitiativeCombatantRow:
    def __init__(self, tracker: "InitiativeTrackerWindow", parent: ttk.Frame, combatant: InitiativeCombatant) -> None:
        self.tracker = tracker
        self.combatant_id = combatant.combatant_id
        self._portrait_ref = ""
        self._initiative_apply_after_id: str | None = None
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
        self.name_entry.bind("<FocusOut>", lambda _event: self.apply_edits())
        self.initiative_entry.bind("<KeyRelease>", lambda _event: self.schedule_initiative_apply())
        self.initiative_entry.bind("<Return>", lambda _event: self.apply_initiative_edits())
        self.initiative_entry.bind("<FocusOut>", lambda _event: self.apply_initiative_edits())
        self.refresh(combatant)

    def _render_portrait(self, combatant: InitiativeCombatant) -> None:
        if combatant.portrait_ref == self._portrait_ref:
            return
        existing = self.portrait_container.winfo_children()
        widget = existing[0] if existing else None
        widget = self.tracker.refresh_portrait_widget(widget, self.portrait_container, combatant.portrait_ref, size=72, background="#171a1f")
        if not widget.winfo_manager():
            widget.pack()
        self._portrait_ref = combatant.portrait_ref

    def apply_edits(self) -> None:
        combatant = self.tracker.combatant_by_id(self.combatant_id)
        if combatant is None:
            return
        name = self.tracker.app.localized_player_name(self.name_var.get())
        initiative = _safe_int(self.initiative_var.get(), combatant.initiative)
        if combatant.name == name and combatant.initiative == initiative:
            return
        combatant.name = name
        combatant.initiative = initiative
        self.tracker.persist(self.tracker.t("initiative.status.updated", name=combatant.name))

    def schedule_initiative_apply(self) -> None:
        if self._initiative_apply_after_id is not None:
            self.frame.after_cancel(self._initiative_apply_after_id)
        self._initiative_apply_after_id = self.frame.after(300, self.apply_initiative_edits)

    def apply_initiative_edits(self) -> None:
        if self._initiative_apply_after_id is not None:
            pending_job = self._initiative_apply_after_id
            self._initiative_apply_after_id = None
            try:
                self.frame.after_cancel(pending_job)
            except tk.TclError:
                pass
        combatant = self.tracker.combatant_by_id(self.combatant_id)
        if combatant is None:
            return
        initiative = _safe_int(self.initiative_var.get(), combatant.initiative)
        if combatant.initiative == initiative:
            return
        combatant.initiative = initiative
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
        if self.name_var.get() != combatant.name:
            self.name_var.set(combatant.name)
        initiative_text = str(combatant.initiative)
        if self.initiative_var.get() != initiative_text:
            self.initiative_var.set(initiative_text)
        state = self.tracker.app.state.initiative
        index = self.tracker.combatant_index(self.combatant_id)
        is_current = state.started and index == state.current_turn_index
        marker = self.tracker.t("initiative.current_marker") if is_current else self.tracker.t("initiative.ready_marker")
        status = f"{index + 1}. {marker}" if index >= 0 else marker
        if combatant.initiative != 0:
            initiative_badge = self.tracker.t("initiative.initiative_badge", initiative=combatant.initiative)
            status = f"{status} - {initiative_badge}"
        self.status_label.config(text=status)
        self.assign_button.config(text=self.tracker.t("initiative.action.use_selected_portrait"))
        self.clear_button.config(text=self.tracker.t("initiative.action.clear_portrait"))
        self.up_button.config(text=self.tracker.t("initiative.action.move_up"))
        self.down_button.config(text=self.tracker.t("initiative.action.move_down"))
        self.remove_button.config(text=self.tracker.t("action.remove"))

    def destroy(self) -> None:
        if self._initiative_apply_after_id is not None:
            self.frame.after_cancel(self._initiative_apply_after_id)
            self._initiative_apply_after_id = None
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
        self.show_hp_player_import_var = tk.BooleanVar(value=self.app.state.initiative.show_hp_player_import)
        self.obs_topmost_var = tk.BooleanVar(value=self.app.state.initiative.obs_topmost)
        self.obs_background_var = tk.BooleanVar(value=self.app.state.initiative.obs_background)
        self.obs_visible_slots_var = tk.StringVar(value=str(self.app.state.initiative.obs_visible_slots))

        self.row_widgets: dict[str, InitiativeCombatantRow] = {}
        self.obs_window: InitiativeObsWindow | None = None
        self.portrait_cache: dict[tuple[str, int], tk.PhotoImage] = {}
        self.combatant_library_refs_by_index: list[str] = []
        self.portrait_library: list[tuple[str, str]] = []
        self.library_refs_by_index: list[str] = []
        self._row_order_signature: tuple[str, ...] = ()
        self._combatant_library_signature: tuple[object, ...] | None = None
        self._preview_signature: tuple[object, ...] | None = None
        self._layout_mode = ""

        self._build_layout()
        self.refresh_library()
        self.window.bind("<Configure>", self._on_window_resize)
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

        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.header = header

        self.title_label = ttk.Label(header, style="Header.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(header, style="Muted.TLabel")
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        top_left = ttk.LabelFrame(container, style="Section.TLabelframe", padding=10)
        self.top_left = top_left

        self.add_helper_label = ttk.Label(top_left, style="Muted.TLabel")
        self.add_name_label = ttk.Label(top_left)
        self.add_name_entry = ttk.Entry(top_left, textvariable=self.add_name_var)
        self.add_initiative_label = ttk.Label(top_left)
        self.add_initiative_entry = ttk.Entry(top_left, textvariable=self.add_initiative_var, width=8)
        self.add_button = ttk.Button(top_left, command=self.add_combatant)
        self.save_to_library_button = ttk.Button(top_left, command=self.save_current_to_library)

        player_row = ttk.Frame(top_left)
        self.player_row = player_row
        self.from_players_label = ttk.Label(player_row)
        self.source_player_combo = ttk.Combobox(player_row, state="readonly", textvariable=self.source_player_var)
        self.add_from_player_button = ttk.Button(player_row, command=self.add_from_player)
        self.save_from_player_to_library_button = ttk.Button(player_row, command=self.save_selected_player_to_library)

        top_right = ttk.Frame(container)
        self.top_right = top_right

        self.start_button = ttk.Button(top_right, command=self.start_encounter)
        self.previous_button = ttk.Button(top_right, command=self.previous_turn)
        self.next_button = ttk.Button(top_right, command=self.next_turn)
        self.reset_button = ttk.Button(top_right, command=self.reset_encounter)
        self.clear_button = ttk.Button(top_right, command=self.clear_encounter)
        self.obs_button = ttk.Button(top_right, command=self.toggle_obs_window)
        self.action_buttons = [
            self.start_button,
            self.previous_button,
            self.next_button,
            self.reset_button,
            self.clear_button,
            self.obs_button,
        ]

        self.turn_panel = ttk.LabelFrame(top_right, style="Section.TLabelframe", padding=10)
        self.turn_panel.columnconfigure(0, weight=1)
        self.turn_panel.columnconfigure(1, weight=0)
        self.turn_round_label = ttk.Label(self.turn_panel, style="Muted.TLabel")
        self.turn_round_label.grid(row=0, column=0, sticky="w")
        self.turn_count_label = ttk.Label(self.turn_panel, style="Muted.TLabel")
        self.turn_count_label.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.turn_current_label = ttk.Label(self.turn_panel, style="Header.TLabel")
        self.turn_current_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.turn_hint_label = ttk.Label(top_right, style="Muted.TLabel")
        self.obs_topmost_check = ttk.Checkbutton(top_right, variable=self.obs_topmost_var, command=self.toggle_obs_topmost)
        self.obs_background_check = ttk.Checkbutton(top_right, variable=self.obs_background_var, command=self.toggle_obs_background)
        self.show_hp_player_import_check = ttk.Checkbutton(
            top_right,
            variable=self.show_hp_player_import_var,
            command=self.toggle_hp_player_import_visibility,
        )
        self.obs_visible_slots_label = ttk.Label(top_right)
        self.obs_visible_slots_combo = ttk.Combobox(
            top_right,
            state="readonly",
            values=OBS_SLOT_OPTIONS,
            textvariable=self.obs_visible_slots_var,
            width=6,
        )
        self.obs_visible_slots_combo.bind("<<ComboboxSelected>>", lambda _event: self.change_obs_visible_slots())

        self.encounter_card = ttk.LabelFrame(container, style="Section.TLabelframe", padding=10)
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

        self.side_panel = ttk.Frame(container)
        self.side_panel.columnconfigure(0, weight=1)
        self.side_panel.rowconfigure(0, weight=1)
        self.side_panel.rowconfigure(1, weight=2)

        self.roster_card = ttk.LabelFrame(self.side_panel, style="Section.TLabelframe", padding=10)
        self.roster_card.columnconfigure(0, weight=1)
        self.roster_card.rowconfigure(1, weight=1)

        self.roster_header = ttk.Label(self.roster_card, style="Muted.TLabel")
        self.roster_header.grid(row=0, column=0, sticky="w", pady=(0, 10))

        roster_list_frame = ttk.Frame(self.roster_card)
        roster_list_frame.grid(row=1, column=0, sticky="nsew")
        roster_list_frame.columnconfigure(0, weight=1)
        roster_list_frame.rowconfigure(0, weight=1)

        self.roster_list = tk.Listbox(
            roster_list_frame,
            bg="#141922",
            fg="#e7ebef",
            selectbackground="#243142",
            activestyle="none",
            highlightthickness=0,
        )
        self.roster_list.grid(row=0, column=0, sticky="nsew")
        roster_scroll = ttk.Scrollbar(roster_list_frame, orient="vertical", command=self.roster_list.yview)
        roster_scroll.grid(row=0, column=1, sticky="ns")
        self.roster_list.configure(yscrollcommand=roster_scroll.set)
        self.roster_list.bind("<Double-Button-1>", lambda _event: self.add_selected_library_combatant())

        roster_actions = ttk.Frame(self.roster_card)
        self.roster_actions = roster_actions
        self.add_selected_library_button = ttk.Button(roster_actions, command=self.add_selected_library_combatant)
        self.set_library_portrait_button = ttk.Button(roster_actions, command=self.assign_selected_portrait_to_library_entry)
        self.delete_library_entry_button = ttk.Button(roster_actions, command=self.delete_selected_library_entry)
        self.roster_action_buttons = [
            self.add_selected_library_button,
            self.set_library_portrait_button,
            self.delete_library_entry_button,
        ]

        self.library_card = ttk.LabelFrame(self.side_panel, style="Section.TLabelframe", padding=10)
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
        self.library_actions = library_actions

        self.import_button = ttk.Button(library_actions, command=self.import_portraits)
        self.delete_button = ttk.Button(library_actions, command=self.delete_selected_portrait)
        self.refresh_button = ttk.Button(library_actions, command=self.refresh_library)
        self.use_selected_button = ttk.Button(library_actions, command=self.assign_selected_to_new)
        self.library_action_buttons = [
            self.import_button,
            self.delete_button,
            self.refresh_button,
            self.use_selected_button,
        ]

        self.status_label = ttk.Label(container, style="Muted.TLabel", textvariable=self.status_var)
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self._apply_responsive_layout(self.window.winfo_width())

    def _on_rows_configure(self, _event: object | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.rows_window, width=event.width)

    def _on_window_resize(self, event: tk.Event) -> None:
        if event.widget is self.window:
            self._apply_responsive_layout(event.width)

    def _layout_add_controls(self, compact: bool) -> None:
        self.add_helper_label.grid_forget()
        self.add_name_label.grid_forget()
        self.add_name_entry.grid_forget()
        self.add_initiative_label.grid_forget()
        self.add_initiative_entry.grid_forget()
        self.add_button.grid_forget()
        self.save_to_library_button.grid_forget()
        self.player_row.grid_forget()
        self.from_players_label.grid_forget()
        self.source_player_combo.grid_forget()
        self.add_from_player_button.grid_forget()
        self.save_from_player_to_library_button.grid_forget()

        for column in range(6):
            self.top_left.columnconfigure(column, weight=0)
        for column in range(4):
            self.player_row.columnconfigure(column, weight=0)

        if compact:
            self.top_left.columnconfigure(1, weight=1)
            self.top_left.columnconfigure(2, weight=1)
            self.top_left.columnconfigure(3, weight=1)
            self.top_left.columnconfigure(4, weight=1)
            self.top_left.columnconfigure(5, weight=1)
            self.add_helper_label.grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 10))
            self.add_name_label.grid(row=1, column=0, sticky="w")
            self.add_name_entry.grid(row=1, column=1, columnspan=5, sticky="ew", padx=(8, 0))
            self.add_initiative_label.grid(row=2, column=0, sticky="w", pady=(10, 0))
            self.add_initiative_entry.grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
            self.add_button.grid(row=2, column=2, columnspan=2, sticky="ew", pady=(10, 0))
            self.save_to_library_button.grid(row=2, column=4, columnspan=2, sticky="ew", padx=(8, 0), pady=(10, 0))

            if self.show_hp_player_import_var.get():
                self.player_row.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(12, 0))
                self.player_row.columnconfigure(0, weight=0)
                self.player_row.columnconfigure(1, weight=1)
                self.player_row.columnconfigure(2, weight=0)
                self.player_row.columnconfigure(3, weight=0)
                self.from_players_label.grid(row=0, column=0, columnspan=4, sticky="w")
                self.source_player_combo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(8, 0))
                self.add_from_player_button.grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(8, 0))
                self.save_from_player_to_library_button.grid(row=1, column=3, sticky="ew", pady=(8, 0))
        else:
            self.top_left.columnconfigure(1, weight=1)
            self.top_left.columnconfigure(4, weight=1)
            self.top_left.columnconfigure(5, weight=1)
            self.add_helper_label.grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))
            self.add_name_label.grid(row=1, column=0, sticky="w")
            self.add_name_entry.grid(row=1, column=1, sticky="ew", padx=(8, 12))
            self.add_initiative_label.grid(row=1, column=2, sticky="w")
            self.add_initiative_entry.grid(row=1, column=3, sticky="ew", padx=(8, 12))
            self.add_button.grid(row=1, column=4, sticky="ew", padx=(0, 8))
            self.save_to_library_button.grid(row=1, column=5, sticky="ew")

            if self.show_hp_player_import_var.get():
                self.player_row.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(10, 0))
                self.player_row.columnconfigure(1, weight=1)
                self.from_players_label.grid(row=0, column=0, sticky="w")
                self.source_player_combo.grid(row=0, column=1, sticky="ew", padx=(8, 12))
                self.add_from_player_button.grid(row=0, column=2, sticky="ew", padx=(0, 8))
                self.save_from_player_to_library_button.grid(row=0, column=3, sticky="ew")

    def _layout_action_controls(self, compact: bool) -> None:
        self.turn_panel.grid_forget()
        self.turn_hint_label.grid_forget()
        for button in self.action_buttons:
            button.grid_forget()
        self.obs_topmost_check.grid_forget()
        self.obs_background_check.grid_forget()
        self.show_hp_player_import_check.grid_forget()
        self.obs_visible_slots_label.grid_forget()
        self.obs_visible_slots_combo.grid_forget()

        if compact:
            for column in range(6):
                self.top_right.columnconfigure(column, weight=0)
            for column in range(3):
                self.top_right.columnconfigure(column, weight=1)
            self.turn_panel.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
            for index, button in enumerate(self.action_buttons):
                row = index // 3 + 1
                column = index % 3
                pad_left = 0 if column == 0 else 6
                pad_right = 0 if column == 2 else 6
                button.grid(row=row, column=column, sticky="ew", padx=(pad_left, pad_right), pady=(0, 8) if row == 1 else 0)
            self.turn_hint_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
            self.obs_topmost_check.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self.obs_background_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self.show_hp_player_import_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self.obs_visible_slots_label.grid(row=7, column=0, sticky="w", pady=(8, 0))
            self.obs_visible_slots_combo.grid(row=7, column=1, sticky="w", pady=(8, 0))
        else:
            for column in range(6):
                self.top_right.columnconfigure(column, weight=1)
            self.turn_panel.grid(row=0, column=0, columnspan=6, sticky="ew", pady=(0, 10))
            for index, button in enumerate(self.action_buttons):
                padx = (0, 6) if index == 0 else (6, 0) if index == len(self.action_buttons) - 1 else 6
                if isinstance(padx, int):
                    button.grid(row=1, column=index, sticky="ew", padx=padx)
                else:
                    button.grid(row=1, column=index, sticky="ew", padx=padx)
            self.turn_hint_label.grid(row=2, column=0, columnspan=6, sticky="w", pady=(12, 0))
            self.obs_topmost_check.grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 0))
            self.obs_background_check.grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
            self.show_hp_player_import_check.grid(row=5, column=0, columnspan=6, sticky="w", pady=(8, 0))
            self.obs_visible_slots_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self.obs_visible_slots_combo.grid(row=6, column=3, columnspan=3, sticky="w", pady=(8, 0))

    def _layout_library_actions(self, compact: bool) -> None:
        self.library_actions.grid_forget()
        for button in self.library_action_buttons:
            button.grid_forget()
        for column in range(4):
            self.library_actions.columnconfigure(column, weight=0)

        self.library_actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        if compact:
            for column in range(2):
                self.library_actions.columnconfigure(column, weight=1)
            for index, button in enumerate(self.library_action_buttons):
                row = index // 2
                column = index % 2
                pad_left = 0 if column == 0 else 6
                pad_right = 0 if column == 1 else 6
                button.grid(row=row, column=column, sticky="ew", padx=(pad_left, pad_right), pady=(0, 8) if row == 0 else 0)
        else:
            for column in range(4):
                self.library_actions.columnconfigure(column, weight=1)
            self.import_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self.delete_button.grid(row=0, column=1, sticky="ew", padx=6)
            self.refresh_button.grid(row=0, column=2, sticky="ew", padx=6)
            self.use_selected_button.grid(row=0, column=3, sticky="ew", padx=(6, 0))

    def _layout_roster_actions(self, compact: bool) -> None:
        self.roster_actions.grid_forget()
        for button in self.roster_action_buttons:
            button.grid_forget()
        for column in range(3):
            self.roster_actions.columnconfigure(column, weight=0)

        self.roster_actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        if compact:
            self.roster_actions.columnconfigure(0, weight=1)
            self.add_selected_library_button.grid(row=0, column=0, sticky="ew")
            self.set_library_portrait_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))
            self.delete_library_entry_button.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        else:
            for column in range(3):
                self.roster_actions.columnconfigure(column, weight=1)
            self.add_selected_library_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self.set_library_portrait_button.grid(row=0, column=1, sticky="ew", padx=6)
            self.delete_library_entry_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _apply_responsive_layout(self, width: int) -> None:
        compact = width < INITIATIVE_COMPACT_BREAKPOINT
        mode = "compact" if compact else "wide"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode

        self.top_left.grid_forget()
        self.top_right.grid_forget()
        self.encounter_card.grid_forget()
        self.side_panel.grid_forget()
        self.status_label.grid_forget()

        if compact:
            self.container.columnconfigure(0, weight=1)
            self.container.columnconfigure(1, weight=0)
            self.container.rowconfigure(1, weight=0)
            self.container.rowconfigure(2, weight=0)
            self.container.rowconfigure(3, weight=2)
            self.container.rowconfigure(4, weight=1)
            self.container.rowconfigure(5, weight=0)
            self.top_left.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(16, 10))
            self.top_right.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
            self.encounter_card.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
            self.side_panel.grid(row=4, column=0, columnspan=2, sticky="nsew")
            self.status_label.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        else:
            self.container.columnconfigure(0, weight=3)
            self.container.columnconfigure(1, weight=2)
            self.container.rowconfigure(1, weight=0)
            self.container.rowconfigure(2, weight=1)
            self.container.rowconfigure(3, weight=0)
            self.container.rowconfigure(4, weight=0)
            self.container.rowconfigure(5, weight=0)
            self.top_left.grid(row=1, column=0, sticky="ew", pady=(16, 12), padx=(0, 8))
            self.top_right.grid(row=1, column=1, sticky="ew", pady=(16, 12), padx=(8, 0))
            self.encounter_card.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
            self.side_panel.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
            self.status_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        self.roster_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.library_card.grid(row=1, column=0, sticky="nsew")
        self._layout_add_controls(compact)
        self._layout_action_controls(compact)
        self._layout_roster_actions(compact)
        self._layout_library_actions(compact)

    def set_status(self, status: str) -> None:
        self.status_var.set(status)

    def persist(self, status: str | None = None) -> None:
        save_state(self.app.state)
        self.refresh()
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
        self.subtitle_label.config(wraplength=max(320, self.window.winfo_width() - 120))
        self.top_left.config(text=self.t("initiative.card.add_combatant"))
        self.add_helper_label.config(text=self.t("initiative.add_helper"))
        self.add_name_label.config(text=self.t("label.name"))
        self.add_initiative_label.config(text=self.t("initiative.label.initiative"))
        self.add_button.config(text=self.t("initiative.action.add_combatant"))
        self.save_to_library_button.config(text=self.t("initiative.action.save_to_library"))
        self.from_players_label.config(text=self.t("initiative.label.from_players"))
        self.add_from_player_button.config(text=self.t("initiative.action.add_from_players"))
        self.save_from_player_to_library_button.config(text=self.t("initiative.action.save_selected_player_to_library"))
        self.start_button.config(text=self.t("initiative.action.start"))
        self.previous_button.config(text=self.t("initiative.action.previous_turn"))
        self.next_button.config(text=self.t("initiative.action.next_turn"))
        self.reset_button.config(text=self.t("initiative.action.reset"))
        self.clear_button.config(text=self.t("initiative.action.clear"))
        self.obs_button.config(
            text=self.t("initiative.action.hide_obs") if self.obs_window is not None else self.t("initiative.action.show_obs")
        )
        state = self.app.state.initiative
        current = self.current_combatant()
        self.turn_panel.config(text=self.t("initiative.card.turn_controls"))
        self.turn_round_label.config(text=self.t("initiative.round_label", round_number=state.round_number))
        self.turn_count_label.config(text=self.t("initiative.combatant_count", count=len(state.combatants)))
        if state.started and current is not None:
            self.turn_current_label.config(text=self.t("initiative.current_turn", name=current.name))
        else:
            self.turn_current_label.config(text=self.t("initiative.not_started"))
        self.turn_hint_label.config(text=self.t("initiative.options_header"))
        self.obs_topmost_check.config(text=self.t("initiative.obs_topmost"))
        self.obs_background_check.config(text=self.t("initiative.obs_background"))
        self.show_hp_player_import_check.config(text=self.t("initiative.show_hp_player_import"))
        self.obs_visible_slots_label.config(text=self.t("initiative.obs_visible_slots"))
        self.show_hp_player_import_var.set(self.app.state.initiative.show_hp_player_import)
        self.obs_topmost_var.set(self.app.state.initiative.obs_topmost)
        self.obs_background_var.set(self.app.state.initiative.obs_background)
        self.obs_visible_slots_var.set(str(self.app.state.initiative.obs_visible_slots))
        self._apply_responsive_layout(max(self.window.winfo_width(), self.window.winfo_reqwidth()))
        self.add_helper_label.config(wraplength=max(260, self.top_left.winfo_width() - 24))
        self.turn_current_label.config(wraplength=max(220, self.top_right.winfo_width() - 24))
        self.encounter_card.config(text=self.t("initiative.card.encounter"))
        self.encounter_header.config(text=self.encounter_summary_text())
        self.roster_card.config(text=self.t("initiative.card.combatant_library"))
        self.roster_header.config(text=self.t("initiative.library_header"))
        self.add_selected_library_button.config(text=self.t("initiative.action.add_selected_library"))
        self.set_library_portrait_button.config(text=self.t("initiative.action.set_library_portrait"))
        self.delete_library_entry_button.config(text=self.t("initiative.action.delete_library_entry"))
        self.library_card.config(text=self.t("initiative.card.library"))
        self.search_label.config(text=self.t("initiative.label.search"))
        self.preview_title.config(text=self.t("initiative.label.preview"))
        self.import_button.config(text=self.t("initiative.action.import_portraits"))
        self.delete_button.config(text=self.t("initiative.action.delete_portrait"))
        self.refresh_button.config(text=self.t("initiative.action.refresh_library"))
        self.use_selected_button.config(text=self.t("initiative.action.use_for_new"))

        self.refresh_player_source_options()
        combatants = self.app.state.initiative.combatants
        row_order_signature = tuple(combatant.combatant_id for combatant in combatants)
        existing_ids = {combatant.combatant_id for combatant in combatants}
        for stale_id in list(self.row_widgets):
            if stale_id not in existing_ids:
                self.row_widgets.pop(stale_id).destroy()

        for combatant in combatants:
            row = self.row_widgets.get(combatant.combatant_id)
            if row is None:
                row = InitiativeCombatantRow(self, self.rows_frame, combatant)
                self.row_widgets[combatant.combatant_id] = row
            row.refresh(combatant)

        if row_order_signature != self._row_order_signature:
            for row in self.row_widgets.values():
                row.frame.pack_forget()
            for combatant in combatants:
                row = self.row_widgets.get(combatant.combatant_id)
                if row is not None:
                    row.frame.pack(fill="x", pady=4)
            self._row_order_signature = row_order_signature

        if self.obs_window is not None:
            self.obs_window.refresh()

        self.refresh_combatant_library()
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

    def library_entry_by_id(self, entry_id: str) -> InitiativeLibraryEntry | None:
        for entry in self.app.state.initiative.library:
            if entry.entry_id == entry_id:
                return entry
        return None

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

    def selected_library_entry_id(self) -> str:
        selection = self.roster_list.curselection()
        if not selection:
            return ""
        index = selection[0]
        if 0 <= index < len(self.combatant_library_refs_by_index):
            return self.combatant_library_refs_by_index[index]
        return ""

    def refresh_combatant_library(self) -> None:
        selected_entry_id = self.selected_library_entry_id()
        entries = sorted(
            self.app.state.initiative.library,
            key=lambda entry: (entry.name.lower(), -entry.initiative, entry.entry_id),
        )
        labels: list[str] = []
        refs: list[str] = []
        for entry in entries:
            label = entry.name
            if entry.initiative != 0:
                badge = self.t("initiative.initiative_badge", initiative=entry.initiative)
                label = f"{entry.name} ({badge})"
            labels.append(label)
            refs.append(entry.entry_id)

        signature = (self.app.state.locale, tuple((ref, label) for ref, label in zip(refs, labels)))
        if signature != self._combatant_library_signature:
            self.roster_list.delete(0, "end")
            for label in labels:
                self.roster_list.insert("end", label)
            self.combatant_library_refs_by_index = refs
            self._combatant_library_signature = signature

        selected_index = None
        for index, entry_id in enumerate(self.combatant_library_refs_by_index):
            if entry_id == selected_entry_id:
                selected_index = index
                break

        self.roster_list.selection_clear(0, "end")
        if selected_index is not None:
            self.roster_list.selection_set(selected_index)
            self.roster_list.see(selected_index)
        elif self.combatant_library_refs_by_index:
            self.roster_list.selection_set(0)

    def _build_combatant(self, name: str, initiative: int, portrait_ref: str) -> InitiativeCombatant:
        return InitiativeCombatant(
            name=self.app.localized_player_name(name),
            initiative=initiative,
            portrait_ref=portrait_ref,
        )

    def _next_library_combatant_name(self, base_name: str) -> str:
        name = self.app.localized_player_name(base_name)
        used_suffixes: set[int] = set()
        prefix = f"{name} "
        for combatant in self.app.state.initiative.combatants:
            existing_name = combatant.name.strip()
            if existing_name == name:
                used_suffixes.add(1)
            elif existing_name.startswith(prefix):
                suffix = existing_name[len(prefix) :]
                if suffix.isdigit():
                    used_suffixes.add(_safe_int(suffix, 0))
        if not used_suffixes:
            return name
        suffix = 2
        while suffix in used_suffixes:
            suffix += 1
        return f"{name} {suffix}"

    def _insertion_index_for_started_encounter(self, initiative: int) -> int:
        index = 0
        combatants = self.app.state.initiative.combatants
        while index < len(combatants) and combatants[index].initiative >= initiative:
            index += 1
        return index

    def _add_combatant_to_encounter(self, combatant: InitiativeCombatant) -> None:
        state = self.app.state.initiative
        if state.started:
            current_id = self._remember_current()
            insert_index = self._insertion_index_for_started_encounter(combatant.initiative)
            state.combatants.insert(insert_index, combatant)
            self._restore_current(current_id)
        else:
            state.combatants.append(combatant)

    def save_current_to_library(self) -> None:
        name = self.app.localized_player_name(self.add_name_var.get())
        portrait_ref = self.selected_portrait_ref()
        entry = InitiativeLibraryEntry(name=name, initiative=0, portrait_ref=portrait_ref)
        self.app.state.initiative.library.append(entry)
        self.persist(self.t("initiative.status.saved_to_library", name=entry.name))

    def save_selected_player_to_library(self) -> None:
        source_name = self.source_player_var.get().strip()
        if not source_name:
            self.set_status(self.t("initiative.status.no_player_selected"))
            return
        portrait_ref = self.selected_portrait_ref()
        entry = InitiativeLibraryEntry(
            name=self.app.localized_player_name(source_name),
            initiative=0,
            portrait_ref=portrait_ref,
        )
        self.app.state.initiative.library.append(entry)
        self.persist(self.t("initiative.status.saved_to_library", name=entry.name))

    def add_selected_library_combatant(self) -> None:
        entry_id = self.selected_library_entry_id()
        if not entry_id:
            self.set_status(self.t("initiative.status.no_library_selected"))
            return
        entry = self.library_entry_by_id(entry_id)
        if entry is None:
            self.set_status(self.t("initiative.status.no_library_selected"))
            return
        combatant = self._build_combatant(self._next_library_combatant_name(entry.name), 0, entry.portrait_ref)
        self._add_combatant_to_encounter(combatant)
        status_key = "initiative.status.inserted" if self.app.state.initiative.started else "initiative.status.added"
        self.persist(self.t(status_key, name=combatant.name))

    def assign_selected_portrait_to_library_entry(self) -> None:
        entry_id = self.selected_library_entry_id()
        if not entry_id:
            self.set_status(self.t("initiative.status.no_library_selected"))
            return
        entry = self.library_entry_by_id(entry_id)
        if entry is None:
            self.set_status(self.t("initiative.status.no_library_selected"))
            return
        selected = self.selected_portrait_ref()
        if not selected:
            self.set_status(self.t("initiative.status.no_portrait_selected"))
            return
        entry.portrait_ref = selected
        self._combatant_library_signature = None
        self.persist(self.t("initiative.status.library_portrait_updated", name=entry.name))

    def delete_selected_library_entry(self) -> None:
        entry_id = self.selected_library_entry_id()
        if not entry_id:
            self.set_status(self.t("initiative.status.no_library_selected"))
            return
        entry = self.library_entry_by_id(entry_id)
        if entry is None:
            self.set_status(self.t("initiative.status.no_library_selected"))
            return
        self.app.state.initiative.library = [item for item in self.app.state.initiative.library if item.entry_id != entry_id]
        self.persist(self.t("initiative.status.deleted_library_entry", name=entry.name))

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
        self._preview_signature = None
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

    def _draw_missing_portrait(self, canvas: tk.Canvas, size: int, background: str) -> None:
        canvas.delete("all")
        canvas.config(width=size, height=size, bg=background, highlightthickness=0, bd=0)
        if background != TRANSPARENT_KEY:
            canvas.create_rectangle(2, 2, size - 2, size - 2, fill="#1e2530", outline="#394455", width=2)
        canvas.create_text(
            size // 2,
            size // 2,
            text=self.t("initiative.no_portrait"),
            width=max(40, size - 16),
            fill="#d0dae8",
            font=("Segoe UI Semibold", max(10, size // 8)),
        )

    def create_portrait_widget(self, parent: tk.Misc, portrait_ref: str, size: int, background: str) -> tk.Widget:
        image = self.get_portrait_image(portrait_ref, size)
        if image is not None:
            label = tk.Label(parent, image=image, bg=background, bd=0, highlightthickness=0)
            label.image = image
            return label
        canvas = tk.Canvas(parent, width=size, height=size, bg=background, highlightthickness=0, bd=0)
        self._draw_missing_portrait(canvas, size, background)
        return canvas

    def refresh_portrait_widget(
        self,
        widget: tk.Widget | None,
        parent: tk.Misc,
        portrait_ref: str,
        size: int,
        background: str,
    ) -> tk.Widget:
        image = self.get_portrait_image(portrait_ref, size)
        if image is not None:
            if isinstance(widget, tk.Label):
                widget.config(image=image, bg=background, text="")
                widget.image = image
                return widget
            if widget is not None and widget.winfo_exists():
                widget.destroy()
            label = tk.Label(parent, image=image, bg=background, bd=0, highlightthickness=0)
            label.image = image
            return label

        if isinstance(widget, tk.Canvas):
            self._draw_missing_portrait(widget, size, background)
            return widget
        if widget is not None and widget.winfo_exists():
            widget.destroy()
        canvas = tk.Canvas(parent, width=size, height=size, bg=background, highlightthickness=0, bd=0)
        self._draw_missing_portrait(canvas, size, background)
        return canvas

    def refresh_library_preview(self) -> None:
        selected = self.selected_portrait_ref()
        signature = (selected, self.app.state.locale)
        if signature == self._preview_signature:
            return
        self._preview_signature = signature
        for child in self.preview_container.winfo_children():
            child.destroy()
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
        combatant = self._build_combatant(name, initiative, portrait_ref)
        self._add_combatant_to_encounter(combatant)
        self.add_name_var.set("")
        self.add_initiative_var.set("0")
        status_key = "initiative.status.inserted" if self.app.state.initiative.started else "initiative.status.added"
        self.persist(self.t(status_key, name=combatant.name))

    def add_from_player(self) -> None:
        source_name = self.source_player_var.get().strip()
        if not source_name:
            self.set_status(self.t("initiative.status.no_player_selected"))
            return
        initiative = _safe_int(self.add_initiative_var.get(), 0)
        portrait_ref = self.selected_portrait_ref()
        combatant = self._build_combatant(source_name, initiative, portrait_ref)
        self._add_combatant_to_encounter(combatant)
        status_key = "initiative.status.inserted" if self.app.state.initiative.started else "initiative.status.added"
        self.persist(self.t(status_key, name=combatant.name))

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

    def toggle_hp_player_import_visibility(self) -> None:
        self.app.state.initiative.show_hp_player_import = self.show_hp_player_import_var.get()
        self._layout_mode = ""
        self.persist(self.t("initiative.status.import_visibility_saved"))

    def change_obs_visible_slots(self) -> None:
        self.app.state.initiative.obs_visible_slots = max(4, min(12, _safe_int(self.obs_visible_slots_var.get(), 12)))
        if self.obs_window is not None:
            self.obs_window.refresh()
        self.persist(self.t("initiative.status.obs_settings_saved"))

    def toggle_obs_window(self) -> None:
        if self.obs_window is not None:
            self.obs_window.close()
        else:
            self.obs_window = InitiativeObsWindow(self)
        self.refresh()
