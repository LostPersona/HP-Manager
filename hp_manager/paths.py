from __future__ import annotations

from pathlib import Path
import sys


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def asset_path(*parts: str) -> Path:
    return app_base_dir().joinpath("assets", *parts)


def state_path(filename: str = "hp_manager_state.json") -> Path:
    return app_base_dir().joinpath(filename)
