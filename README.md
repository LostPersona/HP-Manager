# HP-Manager

Desktop HealthPoints manager for DnD-like games, built with Python and `tkinter`.

## Current features

- Main dashboard for adding and removing players
- Per-player HP controls for damage, healing, and direct edits
- Per-player money tracking with `cc`, `sc`, and `gc`
- Per-player spell slot tracking for levels I-IX
- Detachable floating player windows for OBS capture
- Standalone money and spell slot windows for OBS capture
- Optional floating portrait fill windows that fill red as HP drops
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

When you package the app into a directory build, the bundled assets are loaded from PyInstaller's internal app contents, while the state JSON is still stored next to the `.exe`, which keeps the app portable for non-technical users.

For custom money icons, place these files in:

```text
assets/coins/cc.png
assets/coins/sc.png
assets/coins/gc.png
```

The money windows will show the coin image on the left and the corresponding amount on the right. If those files are missing, the app falls back to built-in coin badges.

## Sync format

The parser only reads lines placed between `>>>` markers. Inside those blocks, each character entry must start with `Name:` / `Имя:`. After that, the rest of the fields can appear in any order:

- `Health:` / `Здоровье:`
- `Coins:` / `Монеты:`
- `Spell Slots:` / `Ячейки заклинаний:`

Missing values default to zero. For health, that means `0/1 (0)` if no health line is present. Text outside those marker blocks is ignored by the parser.

English example:

```text
>>>
Name: Aela Swift
Health: 18/24
Coins: 4 gc 3 sc 1 cc

Name: Borin Spencer
Coins: 5 gc 0 sc 2 cc
Health: 7/31 (5)

Name: Cyra Vale
Health: 2/16
Coins: 12 cc 7 sc 42 gc
Spell Slots:
1: 4/4
2: 3/3
3: 2/3
4: 1/1
5: 0/0
6: 0/0
7: 0/0
8: 0/0
9: 0/0
>>>
```

Russian example:

```text
>>>
Имя: Лоренс
Здоровье: 13/56 (0)
Монеты: 13 зм 0 см 0 мм
Ячейки заклинаний:
1: 4/4
2: 3/3
3: 2/3
4: 1/1
5: 0/0
6: 0/0

Имя: Мей Мей
Здоровье: 15/34
Монеты: 2 мм 13 см 45 зм
Ячейки заклинаний:
1: 4/4
2: 3/3
3: 1/3
4: 0/0
5: 0/0
6: 0/0
>>>
```

Money aliases are:

- EN: `cc`, `sc`, `gc`
- RU: `мм`, `см`, `зм`

## Google Doc sync

Paste a Google Doc link into the sync panel and use `Fetch Doc Now`, or enable sync mode so the app polls the document automatically.

The app currently fetches the document through Google Docs text export, so the document should be readable by the app, for example via a share setting that allows viewing without a private sign-in prompt.

When automatic sync is enabled, temporary fetch failures should not stop polling permanently. The app will keep scheduling the next sync attempt after both successful and failed auto-fetches.

You can also enable an option that updates only existing players from sync data. With that enabled, unknown names from the Google Doc or pasted sync text are skipped instead of creating new dashboard entries, and their money/spell data is skipped as well.

You can also hide the sync preview entirely from the main window; that visibility state is saved between launches.

When sync mode itself is enabled, manual editing controls are hidden. That means the add-player form and per-player manual HP/money/spell slot editing actions disappear, while display-oriented OBS windows and fills remain available. The delete button also remains available in sync mode so players can still be removed from the dashboard.

There is also a hidden-by-default fill settings panel. From there you can choose whether portrait fills render as `1:1`, `4:3`, or `3:4`, whether the character name is shown above the fill, whether money windows use separate lines or a single row, whether coins are shown as copper-to-gold or gold-to-copper, how large the HP/money/spell values render in their OBS windows, and whether spawned player/fill windows stay above other applications or can sit behind them for OBS-only capture. Those settings are saved between launches as well.

Player, money, spell slot, and fill views all open as normal standalone windows so they can be targeted more reliably by OBS window capture.
