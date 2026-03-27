from __future__ import annotations

import json
from pathlib import Path

from hp_manager.models import AppState
from hp_manager.paths import state_path


STATE_PATH = state_path()


def load_state(path: Path = STATE_PATH) -> AppState:
    if not path.exists():
        return AppState()

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return AppState()

    if not isinstance(data, dict):
        return AppState()
    return AppState.from_dict(data)


def save_state(state: AppState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, indent=2)
