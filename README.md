# DC6-Overview v1.0.0

**made by GimliHC · 17.10.2026**

View, extract, import and overview Diablo II **`.dc6`** files, and export a big decorated overview
of all frames (e.g. `MaxiMap.dc6`) as **one PNG + JPG**.

## Setup & start
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py                 (GUI)
.venv\Scripts\python main.py MaxiMap.dc6     (GUI, opens the file)
```
Requires Python 3.13 (Windows).

## DC6 Viewer tab
| Control | What it does |
|---|---|
| Open… / Save / Save As… | Save checks the written file by reading it back and keeps a one-time `name.dc6.bak` |
| Palette | act1 (default), act2–5, units, menu0–4, … or your own `.dat/.pal/.act` |
| − / + / Set as default zoom | pixel-exact zoom; a 1 px line shows the frame area |
| Change Offsets… | X / Y offset of the selected frame (whole numbers, negative allowed) |
| Export… / Export All… | frame(s) → BMP / PCX / PNG / GIF / TIF (8-bit, lossless); all = `0000.bmp`, `0001.bmp`, … + `frames.json` |
| Import… / Import All… | replace frame(s) from images (`NNNN.ext` = frame number). Every file is checked first; problems are explained with a fix |
| + Add new frame / − Remove last frame | grow/shrink the DC6. New frames are saved only once a graphic has been imported into them |

## Overview tab
Settings on the left, live preview on the right (mouse wheel = zoom, drag = pan).
* Header: logo, file name, free text (2 lines × 50 characters), `Graphics:` (frame count), `Oversize:` list, date (automatic), creator GimliHC
* Grid: columns ↔ rows, frame numbers every N frames (font, size, bold, colour), spacing X/Y (0 = shared 1 px walls), side margin, border colour
* Oversize frames are cut to the standard size (keep the top, cut left/right/bottom) and marked with a red cross. The DC6 is not changed
* Upscale ×1/×2/×4. **Photoshop-like** = a filter calibrated against a real Photoshop "Preserve Details 2.0" result
* **Export PNG + JPG** → `<name>_overview.png` / `.jpg`

## Command line
```
python main.py overview MaxiMap.dc6 --cols 60 --every 10 --line1 "Project Diablo 2" --line2 "Season 14"
python main.py validate MaxiMap.dc6
python main.py export-frames MaxiMap.dc6 out_folder --format bmp
```

## Project structure
```
main.py              entry point (GUI or command line)
DC6-Overview.rc      Windows resource: icon + version info (for an .exe build)
core/                program logic: dc6.py (read/validate/write), rle.py, palette.py, imageio.py,
                     import_check.py, font8x8.py, cli.py, paths.py, overview/ (layout, render, upscale,
                     header, pipeline, data/ps2x_kernel.npy)
gui/                 PySide6 UI: app, main_window, viewer_tab, overview_tab, dialogs, widgets, settings
gui/assets/          gimli.png, icon.ico, palettes/*.dat (Diablo II palettes, 768 bytes BGR)
src/filetype_dc6.md  complete reference of the DC6 file format (for people and AI)
```
User settings are stored in the registry under `HKCU\Software\GimliHC\DC6-Overview`.

## Building an .exe (later)
PyInstaller example (keeps the folder layout that `core/paths.py` expects):
```
pyinstaller --name DC6-Overview --windowed --icon gui\assets\icon.ico ^
  --add-data "gui\assets;gui\assets" --add-data "core\overview\data;core\overview\data" main.py
```
`DC6-Overview.rc` holds the version info and icon for resource compilers and C/C++ or Rust launchers.
PyInstaller itself expects a version file in its own format (`--version-file`).
