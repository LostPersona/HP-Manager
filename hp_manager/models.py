from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from hp_manager.localization import normalize_locale

SPELL_SLOT_LEVELS = (1, 2, 3, 4, 5, 6, 7, 8, 9)


def _clean_int(value: int | str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class SpellSlotTrack:
    current: int = 0
    maximum: int = 0

    def __post_init__(self) -> None:
        self.maximum = max(0, _clean_int(self.maximum, 0))
        self.current = max(0, min(_clean_int(self.current, self.maximum), self.maximum))

    def set_counts(self, current: int, maximum: int) -> None:
        self.maximum = max(0, _clean_int(maximum, self.maximum))
        self.current = max(0, min(_clean_int(current, self.current), self.maximum))

    def to_dict(self) -> dict[str, int]:
        return {"current": self.current, "maximum": self.maximum}

    @classmethod
    def from_dict(cls, data: dict[str, int | str] | None) -> "SpellSlotTrack":
        if not data:
            return cls()
        return cls(
            current=_clean_int(data.get("current"), 0),
            maximum=_clean_int(data.get("maximum"), 0),
        )


def _default_spell_slots() -> dict[int, SpellSlotTrack]:
    return {level: SpellSlotTrack() for level in SPELL_SLOT_LEVELS}


@dataclass(slots=True)
class CoinPouch:
    cc: int = 0
    sc: int = 0
    gc: int = 0

    def __post_init__(self) -> None:
        self.cc = max(0, _clean_int(self.cc, 0))
        self.sc = max(0, _clean_int(self.sc, 0))
        self.gc = max(0, _clean_int(self.gc, 0))

    def set_counts(self, cc: int, sc: int, gc: int) -> None:
        self.cc = max(0, _clean_int(cc, self.cc))
        self.sc = max(0, _clean_int(sc, self.sc))
        self.gc = max(0, _clean_int(gc, self.gc))

    def to_dict(self) -> dict[str, int]:
        return {"cc": self.cc, "sc": self.sc, "gc": self.gc}

    @classmethod
    def from_dict(cls, data: dict[str, int | str] | None) -> "CoinPouch":
        if not data:
            return cls()
        return cls(
            cc=_clean_int(data.get("cc"), 0),
            sc=_clean_int(data.get("sc"), 0),
            gc=_clean_int(data.get("gc"), 0),
        )


@dataclass(slots=True)
class Player:
    name: str
    current_hp: int
    max_hp: int
    temp_hp: int = 0
    money: CoinPouch = field(default_factory=CoinPouch)
    spell_slots: dict[int, SpellSlotTrack] = field(default_factory=_default_spell_slots)
    player_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.max_hp = max(1, _clean_int(self.max_hp, 1))
        self.current_hp = max(0, min(_clean_int(self.current_hp, self.max_hp), self.max_hp))
        self.temp_hp = max(0, _clean_int(self.temp_hp))
        self.name = (self.name or "Unnamed").strip() or "Unnamed"
        if not isinstance(self.money, CoinPouch):
            self.money = CoinPouch.from_dict(self.money if isinstance(self.money, dict) else None)
        self.spell_slots = self._normalize_spell_slots(self.spell_slots)

    def apply_damage(self, amount: int) -> None:
        amount = max(0, _clean_int(amount))
        if amount == 0:
            return

        absorbed = min(self.temp_hp, amount)
        self.temp_hp -= absorbed
        remaining = amount - absorbed
        self.current_hp = max(0, self.current_hp - remaining)

    def apply_healing(self, amount: int) -> None:
        amount = max(0, _clean_int(amount))
        if amount == 0:
            return
        self.current_hp = min(self.max_hp, self.current_hp + amount)

    def set_current_hp(self, value: int) -> None:
        self.current_hp = max(0, min(_clean_int(value, self.current_hp), self.max_hp))

    def set_max_hp(self, value: int) -> None:
        self.max_hp = max(1, _clean_int(value, self.max_hp))
        self.current_hp = min(self.current_hp, self.max_hp)

    def set_temp_hp(self, value: int) -> None:
        self.temp_hp = max(0, _clean_int(value, self.temp_hp))

    def set_money(self, cc: int, sc: int, gc: int) -> None:
        self.money.set_counts(cc, sc, gc)

    def set_spell_slot(self, level: int, current: int, maximum: int) -> None:
        if level not in SPELL_SLOT_LEVELS:
            return
        self.spell_slots.setdefault(level, SpellSlotTrack()).set_counts(current, maximum)

    def replace_spell_slots(self, slots: dict[int, SpellSlotTrack | tuple[int, int] | dict[str, int | str]]) -> None:
        self.spell_slots = _default_spell_slots()
        for level in SPELL_SLOT_LEVELS:
            raw_value = slots.get(level)
            if isinstance(raw_value, SpellSlotTrack):
                self.spell_slots[level] = SpellSlotTrack(raw_value.current, raw_value.maximum)
            elif isinstance(raw_value, tuple) and len(raw_value) == 2:
                self.spell_slots[level] = SpellSlotTrack(raw_value[0], raw_value[1])
            elif isinstance(raw_value, dict):
                self.spell_slots[level] = SpellSlotTrack.from_dict(raw_value)

    @staticmethod
    def _normalize_spell_slots(
        slots: dict[int, SpellSlotTrack] | dict[int | str, SpellSlotTrack | dict[str, int | str]]
    ) -> dict[int, SpellSlotTrack]:
        normalized = _default_spell_slots()
        for raw_level, raw_slot in (slots or {}).items():
            level = _clean_int(raw_level, 0)
            if level not in SPELL_SLOT_LEVELS:
                continue
            if isinstance(raw_slot, SpellSlotTrack):
                normalized[level] = SpellSlotTrack(raw_slot.current, raw_slot.maximum)
            elif isinstance(raw_slot, dict):
                normalized[level] = SpellSlotTrack.from_dict(raw_slot)
        return normalized

    @property
    def hp_ratio(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp else 0.0

    @property
    def missing_ratio(self) -> float:
        return 1.0 - self.hp_ratio

    def to_dict(self) -> dict[str, object]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "temp_hp": self.temp_hp,
            "money": self.money.to_dict(),
            "spell_slots": {str(level): slot.to_dict() for level, slot in self.spell_slots.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Player":
        raw_spell_slots = data.get("spell_slots", {})
        spell_slots: dict[int, SpellSlotTrack] = _default_spell_slots()
        if isinstance(raw_spell_slots, dict):
            for raw_level, raw_slot in raw_spell_slots.items():
                level = _clean_int(raw_level, 0)
                if level not in SPELL_SLOT_LEVELS or not isinstance(raw_slot, dict):
                    continue
                spell_slots[level] = SpellSlotTrack.from_dict(raw_slot)
        raw_money = data.get("money")
        return cls(
            player_id=str(data.get("player_id") or uuid4().hex),
            name=str(data.get("name") or "Unnamed"),
            current_hp=_clean_int(data.get("current_hp"), 0),
            max_hp=_clean_int(data.get("max_hp"), 1),
            temp_hp=_clean_int(data.get("temp_hp"), 0),
            money=CoinPouch.from_dict(raw_money if isinstance(raw_money, dict) else None),
            spell_slots=spell_slots,
        )


@dataclass(slots=True)
class SyncSettings:
    enabled: bool = False
    source: str = ""
    poll_seconds: int = 15
    visible: bool = True
    existing_only: bool = False

    def to_dict(self) -> dict[str, bool | int | str]:
        return {
            "enabled": self.enabled,
            "source": self.source,
            "poll_seconds": max(5, _clean_int(self.poll_seconds, 15)),
            "visible": self.visible,
            "existing_only": self.existing_only,
        }

    @classmethod
    def from_dict(cls, data: dict[str, bool | int | str] | None) -> "SyncSettings":
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            source=str(data.get("source") or ""),
            poll_seconds=max(5, _clean_int(data.get("poll_seconds"), 15)),
            visible=bool(data.get("visible", True)),
            existing_only=bool(data.get("existing_only", False)),
        )


@dataclass(slots=True)
class OverlaySettings:
    aspect_ratio: str = "1:1"
    show_title: bool = False
    panel_visible: bool = False
    player_windows_topmost: bool = True
    fill_windows_topmost: bool = True
    player_window_background: bool = True
    money_window_background: bool = True
    spell_window_background: bool = True
    fill_window_background: bool = True
    money_layout: str = "stacked"
    money_order: str = "cc_sc_gc"
    spell_display_count: int = 6
    spell_render_mode: str = "pips"
    show_spell_level_headers: bool = True
    hp_font_size: int = 34
    temp_hp_font_size: int = 22
    money_font_size: int = 24
    spell_level_font_size: int = 32
    spell_font_size: int = 24
    spell_cell_scale: int = 100
    spell_pip_scale: int = 100

    @staticmethod
    def valid_aspect_ratios() -> set[str]:
        return {"1:1", "4:3", "3:4"}

    @staticmethod
    def valid_money_layouts() -> set[str]:
        return {"stacked", "inline"}

    @staticmethod
    def valid_money_orders() -> set[str]:
        return {"cc_sc_gc", "gc_sc_cc"}

    @staticmethod
    def valid_spell_render_modes() -> set[str]:
        return {"text", "pips"}

    @staticmethod
    def clean_spell_display_count(value: int | str | None) -> int:
        return max(1, min(9, _clean_int(value, 6)))

    @staticmethod
    def clean_value_font_size(value: int | str | None, default: int) -> int:
        return max(12, min(72, _clean_int(value, default)))

    @staticmethod
    def clean_spell_cell_scale(value: int | str | None) -> int:
        return max(80, min(200, _clean_int(value, 100)))

    def to_dict(self) -> dict[str, bool | int | str]:
        return {
            "aspect_ratio": self.aspect_ratio if self.aspect_ratio in self.valid_aspect_ratios() else "1:1",
            "show_title": self.show_title,
            "panel_visible": self.panel_visible,
            "player_windows_topmost": self.player_windows_topmost,
            "fill_windows_topmost": self.fill_windows_topmost,
            "player_window_background": self.player_window_background,
            "money_window_background": self.money_window_background,
            "spell_window_background": self.spell_window_background,
            "fill_window_background": self.fill_window_background,
            "money_layout": self.money_layout if self.money_layout in self.valid_money_layouts() else "stacked",
            "money_order": self.money_order if self.money_order in self.valid_money_orders() else "cc_sc_gc",
            "spell_display_count": self.clean_spell_display_count(self.spell_display_count),
            "spell_render_mode": self.spell_render_mode if self.spell_render_mode in self.valid_spell_render_modes() else "pips",
            "show_spell_level_headers": self.show_spell_level_headers,
            "hp_font_size": self.clean_value_font_size(self.hp_font_size, 34),
            "temp_hp_font_size": self.clean_value_font_size(self.temp_hp_font_size, 22),
            "money_font_size": self.clean_value_font_size(self.money_font_size, 24),
            "spell_level_font_size": self.clean_value_font_size(self.spell_level_font_size, 32),
            "spell_font_size": self.clean_value_font_size(self.spell_font_size, 24),
            "spell_cell_scale": self.clean_spell_cell_scale(self.spell_cell_scale),
            "spell_pip_scale": self.clean_spell_cell_scale(self.spell_pip_scale),
        }

    @classmethod
    def from_dict(cls, data: dict[str, bool | str] | None) -> "OverlaySettings":
        if not data:
            return cls()
        aspect_ratio = str(data.get("aspect_ratio") or "1:1")
        if aspect_ratio not in cls.valid_aspect_ratios():
            aspect_ratio = "1:1"
        money_layout = str(data.get("money_layout") or "stacked")
        if money_layout not in cls.valid_money_layouts():
            money_layout = "stacked"
        money_order = str(data.get("money_order") or "cc_sc_gc")
        if money_order not in cls.valid_money_orders():
            money_order = "cc_sc_gc"
        spell_render_mode = str(data.get("spell_render_mode") or "pips")
        if spell_render_mode not in cls.valid_spell_render_modes():
            spell_render_mode = "pips"
        return cls(
            aspect_ratio=aspect_ratio,
            show_title=bool(data.get("show_title", False)),
            panel_visible=bool(data.get("panel_visible", False)),
            player_windows_topmost=bool(data.get("player_windows_topmost", True)),
            fill_windows_topmost=bool(data.get("fill_windows_topmost", True)),
            player_window_background=bool(data.get("player_window_background", True)),
            money_window_background=bool(data.get("money_window_background", True)),
            spell_window_background=bool(data.get("spell_window_background", True)),
            fill_window_background=bool(data.get("fill_window_background", True)),
            money_layout=money_layout,
            money_order=money_order,
            spell_display_count=cls.clean_spell_display_count(data.get("spell_display_count")),
            spell_render_mode=spell_render_mode,
            show_spell_level_headers=bool(data.get("show_spell_level_headers", True)),
            hp_font_size=cls.clean_value_font_size(data.get("hp_font_size"), 34),
            temp_hp_font_size=cls.clean_value_font_size(data.get("temp_hp_font_size"), 22),
            money_font_size=cls.clean_value_font_size(data.get("money_font_size"), 24),
            spell_level_font_size=cls.clean_value_font_size(data.get("spell_level_font_size"), 32),
            spell_font_size=cls.clean_value_font_size(data.get("spell_font_size"), 24),
            spell_cell_scale=cls.clean_spell_cell_scale(data.get("spell_cell_scale")),
            spell_pip_scale=cls.clean_spell_cell_scale(data.get("spell_pip_scale")),
        )


@dataclass(slots=True)
class InitiativeCombatant:
    name: str
    initiative: int = 0
    portrait_ref: str = ""
    combatant_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.name = (self.name or "Unnamed").strip() or "Unnamed"
        self.initiative = _clean_int(self.initiative, 0)
        self.portrait_ref = str(self.portrait_ref or "").strip()

    def to_dict(self) -> dict[str, object]:
        return {
            "combatant_id": self.combatant_id,
            "name": self.name,
            "initiative": self.initiative,
            "portrait_ref": self.portrait_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "InitiativeCombatant":
        return cls(
            combatant_id=str(data.get("combatant_id") or uuid4().hex),
            name=str(data.get("name") or "Unnamed"),
            initiative=_clean_int(data.get("initiative"), 0),
            portrait_ref=str(data.get("portrait_ref") or ""),
        )


@dataclass(slots=True)
class InitiativeState:
    combatants: list[InitiativeCombatant] = field(default_factory=list)
    current_turn_index: int = 0
    round_number: int = 1
    started: bool = False
    obs_topmost: bool = True
    obs_background: bool = True
    obs_visible_slots: int = 12

    def __post_init__(self) -> None:
        self.combatants = [
            item if isinstance(item, InitiativeCombatant) else InitiativeCombatant.from_dict(item)
            for item in self.combatants
            if isinstance(item, (InitiativeCombatant, dict))
        ]
        self.round_number = max(1, _clean_int(self.round_number, 1))
        self.current_turn_index = max(0, _clean_int(self.current_turn_index, 0))
        self.obs_visible_slots = max(4, min(12, _clean_int(self.obs_visible_slots, 12)))
        if self.combatants:
            self.current_turn_index = min(self.current_turn_index, len(self.combatants) - 1)
        else:
            self.current_turn_index = 0
            self.started = False

    def to_dict(self) -> dict[str, object]:
        return {
            "combatants": [combatant.to_dict() for combatant in self.combatants],
            "current_turn_index": self.current_turn_index,
            "round_number": self.round_number,
            "started": self.started,
            "obs_topmost": self.obs_topmost,
            "obs_background": self.obs_background,
            "obs_visible_slots": self.obs_visible_slots,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "InitiativeState":
        if not data:
            return cls()
        raw_combatants = data.get("combatants", [])
        combatants = []
        if isinstance(raw_combatants, list):
            combatants = [InitiativeCombatant.from_dict(item) for item in raw_combatants if isinstance(item, dict)]
        return cls(
            combatants=combatants,
            current_turn_index=_clean_int(data.get("current_turn_index"), 0),
            round_number=max(1, _clean_int(data.get("round_number"), 1)),
            started=bool(data.get("started", False)),
            obs_topmost=bool(data.get("obs_topmost", True)),
            obs_background=bool(data.get("obs_background", True)),
            obs_visible_slots=max(4, min(12, _clean_int(data.get("obs_visible_slots"), 12))),
        )


@dataclass(slots=True)
class AppState:
    players: list[Player] = field(default_factory=list)
    sync: SyncSettings = field(default_factory=SyncSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    initiative: InitiativeState = field(default_factory=InitiativeState)
    locale: str = "en"

    def to_dict(self) -> dict[str, object]:
        return {
            "players": [player.to_dict() for player in self.players],
            "sync": self.sync.to_dict(),
            "overlay": self.overlay.to_dict(),
            "initiative": self.initiative.to_dict(),
            "locale": self.locale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "AppState":
        if not data:
            return cls()

        raw_players = data.get("players", [])
        players = []
        if isinstance(raw_players, list):
            players = [Player.from_dict(item) for item in raw_players if isinstance(item, dict)]

        raw_sync = data.get("sync")
        sync = SyncSettings.from_dict(raw_sync if isinstance(raw_sync, dict) else None)
        raw_overlay = data.get("overlay")
        overlay = OverlaySettings.from_dict(raw_overlay if isinstance(raw_overlay, dict) else None)
        raw_initiative = data.get("initiative")
        initiative = InitiativeState.from_dict(raw_initiative if isinstance(raw_initiative, dict) else None)
        return cls(
            players=players,
            sync=sync,
            overlay=overlay,
            initiative=initiative,
            locale=normalize_locale(data.get("locale") if isinstance(data.get("locale"), str) else None),
        )
