from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from hp_manager.localization import normalize_locale


def _clean_int(value: int | str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Player:
    name: str
    current_hp: int
    max_hp: int
    temp_hp: int = 0
    player_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.max_hp = max(1, _clean_int(self.max_hp, 1))
        self.current_hp = max(0, min(_clean_int(self.current_hp, self.max_hp), self.max_hp))
        self.temp_hp = max(0, _clean_int(self.temp_hp))
        self.name = (self.name or "Unnamed").strip() or "Unnamed"

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

    @property
    def hp_ratio(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp else 0.0

    @property
    def missing_ratio(self) -> float:
        return 1.0 - self.hp_ratio

    def to_dict(self) -> dict[str, int | str]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "temp_hp": self.temp_hp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int | str]) -> "Player":
        return cls(
            player_id=str(data.get("player_id") or uuid4().hex),
            name=str(data.get("name") or "Unnamed"),
            current_hp=_clean_int(data.get("current_hp"), 0),
            max_hp=_clean_int(data.get("max_hp"), 1),
            temp_hp=_clean_int(data.get("temp_hp"), 0),
        )


@dataclass(slots=True)
class SyncSettings:
    enabled: bool = False
    source: str = ""
    poll_seconds: int = 15
    visible: bool = True

    def to_dict(self) -> dict[str, bool | int | str]:
        return {
            "enabled": self.enabled,
            "source": self.source,
            "poll_seconds": max(5, _clean_int(self.poll_seconds, 15)),
            "visible": self.visible,
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
        )


@dataclass(slots=True)
class OverlaySettings:
    aspect_ratio: str = "1:1"
    show_title: bool = False
    panel_visible: bool = False

    def to_dict(self) -> dict[str, bool | str]:
        return {
            "aspect_ratio": self.aspect_ratio if self.aspect_ratio in {"1:1", "4:3"} else "1:1",
            "show_title": self.show_title,
            "panel_visible": self.panel_visible,
        }

    @classmethod
    def from_dict(cls, data: dict[str, bool | str] | None) -> "OverlaySettings":
        if not data:
            return cls()
        aspect_ratio = str(data.get("aspect_ratio") or "1:1")
        if aspect_ratio not in {"1:1", "4:3"}:
            aspect_ratio = "1:1"
        return cls(
            aspect_ratio=aspect_ratio,
            show_title=bool(data.get("show_title", False)),
            panel_visible=bool(data.get("panel_visible", False)),
        )


@dataclass(slots=True)
class AppState:
    players: list[Player] = field(default_factory=list)
    sync: SyncSettings = field(default_factory=SyncSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    locale: str = "en"

    def to_dict(self) -> dict[str, object]:
        return {
            "players": [player.to_dict() for player in self.players],
            "sync": self.sync.to_dict(),
            "overlay": self.overlay.to_dict(),
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
        return cls(
            players=players,
            sync=sync,
            overlay=overlay,
            locale=normalize_locale(data.get("locale") if isinstance(data.get("locale"), str) else None),
        )
