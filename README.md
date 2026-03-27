# More than HP Manager by LostPersona

`More than HP Manager by LostPersona` is a desktop companion app for DnD-like and other TTRPG games. It started as an HP tracker, but the current project goes further: it can manage per-character health, coins, spell slots, and multiple OBS-friendly display windows from a single bilingual dashboard.

Built with Python and `tkinter`, it is designed for GMs, streamers, and groups that want a lightweight local tool without needing a web app.

## What it does

- Manage a party from one dashboard
- Track per-character HP, temp HP, coins, and spell slots
- Open separate standalone windows for OBS capture
- Show a portrait fill window that changes with missing HP
- Sync character data from a Google Doc
- Work in English or Russian from the same codebase
- Save settings and state locally between launches

## Current capabilities

### Character tracking

Each character can store:

- Name
- Current HP
- Max HP
- Temp HP
- Coins: `cc`, `sc`, `gc` or `мм`, `см`, `зм`
- Spell slots for levels I-IX

The dashboard supports manual editing when sync mode is off. When sync mode is on, the app can switch to a display-oriented mode and hide manual edit controls while still keeping OBS-related windows available.

### OBS-friendly windows

The app can spawn separate windows for:

- HP
- Money
- Spell slots
- Fill

These windows are normal standalone windows, which makes them easier to capture through OBS `Window Capture`.

The fill window supports:

- `1:1`
- `4:3`
- `3:4`

It can also optionally show the character name above the fill.

### Advanced display settings

There is a hidden-by-default extra settings panel for stream-facing customization.

Current settings include:

- Fill aspect ratio
- Whether fill windows show the character name
- Whether player windows stay on top
- Whether fill windows stay on top
- Money layout: separate lines or one line
- Money order: `copper -> silver -> gold` or `gold -> silver -> copper`
- Spell display count from `1` to `9`
- Font size for HP value
- Font size for temp HP text
- Font size for money values
- Font size for spell level headers
- Font size for spell slot values
- Spell cell size / scale

All of these settings are persisted in the local state file.

### Localization

The UI is centralized around shared locale logic and currently supports:

- English
- Russian

The selected language is saved and restored on the next launch.

## Run locally

Install Python `3.11+`, then from the repository root run:

```powershell
python app.py
```

The app stores its state in:

```text
hp_manager_state.json
```

By default, that file lives in the app folder, which also makes the packaged build portable.

## Assets

### App icon

Place the main icon here:

```text
assets/app.ico
```

This icon is used by the application at runtime and should also be passed to PyInstaller when building the Windows `.exe`.

### Coin icons

Optional custom coin icons can be placed here:

```text
assets/coins/cc.png
assets/coins/sc.png
assets/coins/gc.png
```

If these files are present, money displays will show the icon on the left and the amount on the right. If they are missing, the app falls back to built-in badges.

## Google Doc sync

The app can fetch text from a Google Doc link and parse character records from it.

Current sync behavior:

- Paste a Google Doc link into the sync panel
- Fetch the document manually or enable automatic polling
- Hide the sync preview when you want more dashboard space
- Restrict sync to only existing characters if you do not want renamed or unexpected names to create new entries

If automatic sync is enabled, the app keeps rescheduling future polling attempts after both successful and failed fetches.

### Sync mode behavior

When sync mode is enabled:

- Manual editing controls are hidden
- OBS-oriented windows remain available
- Fill windows remain available
- Delete remains available

This keeps the dashboard cleaner when the document is acting as the source of truth.

## Sync format

The current parser reads content only inside `>>>` blocks.

Inside those blocks, each character entry must begin with:

- `Name:` in English
- `Имя:` in Russian

After that, the rest of the sections may appear in any order.

Supported fields:

- `Health:` / `Здоровье:`
- `Coins:` / `Монеты:`
- `Spell Slots:` / `Ячейки заклинаний:`

Missing values default to zero. For example:

- missing temp HP becomes `0`
- missing coins become `0`
- missing spell slots become `0/0`

### English example

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

### Russian example

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

Supported money aliases:

- EN: `cc`, `sc`, `gc`
- RU: `мм`, `см`, `зм`

## Packaging into a Windows `.exe`

The project is currently set up well for a portable `PyInstaller --onedir` build.

Install PyInstaller:

```powershell
py -m pip install pyinstaller
```

Build the app:

```powershell
py -m PyInstaller --noconfirm --clean --windowed --onedir --name HP-Manager --icon assets/app.ico --add-data "assets;assets" app.py
```

This produces a distributable folder under:

```text
dist\HP-Manager\
```

Important behavior of the packaged app:

- bundled assets are loaded from the PyInstaller runtime bundle
- `hp_manager_state.json` is stored next to the `.exe`
- the app remains portable as long as the whole folder stays together

## Project structure

Main files and folders:

- `app.py` - entry point
- `hp_manager/ui.py` - main interface and spawned windows
- `hp_manager/models.py` - persisted state and data models
- `hp_manager/sync.py` - sync parsing and Google Doc fetch logic
- `hp_manager/localization.py` - centralized EN/RU locale strings
- `hp_manager/paths.py` - asset and runtime path helpers
- `assets/` - app icon and optional coin images

## Notes

- This project is Windows-friendly first, especially around icon handling and portable packaging.
- The current sync source is Google Docs text export, not Google Sheets.
- Google Sheets support was discussed as a future direction, but it is not part of the current implementation.
