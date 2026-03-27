# HP-Manager

Desktop HealthPoints manager for DnD-like games, built with Python and `tkinter`.

## Current features

- Main dashboard for adding and removing players
- Per-player HP controls for damage, healing, and direct edits
- Detachable floating player windows for OBS capture
- Optional floating portrait overlay windows that fill red as HP drops
- Centralized UI localization with English and Russian support
- Local JSON persistence between launches
- Google Doc sync via link-based text fetching

## Run

1. Install Python 3.11+.
2. From the repository root, run:

```powershell
python app.py
```

The app saves its state into `hp_manager_state.json` in the app folder.

The selected UI language is also saved there and restored on the next launch.

## App icon

Place your `.ico` file at:

```text
assets/app.ico
```

There is a placeholder note at `assets/app.ico.placeholder.txt`. Replace it with your real icon file named `app.ico`, and the app will load it automatically.

When you package the app into a directory build, keep the `assets` folder next to the `.exe`. The state JSON will also be stored next to the `.exe`, which makes the app portable for non-technical users.

## Sync format

The parser supports lines in this format:

```text
Name: current_hp/max_hp(temp_hp)
```

Examples:

```text
Artem: 32/45
Artem: 32/45 (10)
Aela Swift: 18/24
Borin Spencer: 7/31 (5)
Cyra Vale: 2/16
```

If temp HP is omitted, it defaults to `0`.

## Google Doc sync

Paste a Google Doc link into the sync panel and use `Fetch Doc Now`, or enable sync mode so the app polls the document automatically.

The app currently fetches the document through Google Docs text export, so the document should be readable by the app, for example via a share setting that allows viewing without a private sign-in prompt.

You can also hide the sync preview entirely from the main window; that visibility state is saved between launches.

When sync mode itself is enabled, manual HP controls are hidden. That means the add-player form and per-player manual HP editing actions disappear, while display-oriented OBS windows and fills remain available. The delete button also remains available in sync mode so players can still be removed from the dashboard.

There is also a hidden-by-default fill settings panel. From there you can choose whether portrait fills render as `1:1`, `4:3`, or `3:4`, and whether the character name is shown above the fill. Those settings are saved between launches as well.

Portrait fills open as normal standalone windows so they can be targeted more reliably by OBS window capture.
