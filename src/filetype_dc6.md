# Diablo II `.dc6` File Format: Complete Reference

> **What this is:** a self-contained reference for the Diablo II DC6 sprite format: binary layout,
> pixel encoding, palettes, coordinates, how to read/write/validate/convert DC6 files, and what the
> existing community tools do. It is written for **people and for AI assistants**: every section starts
> with a short summary, byte layouts are given as tables *and* as C/Python structs, and a complete
> reference implementation is included (§7).
>
> **Origin:** compiled for **DC6-Overview v1.0.0** (GimliHC, 17.10.2026) from the C sources of
> dc6con / dc6table / dc6font / dc6edit / dc6color, string analysis of SixDice and DC6 Creator,
> community knowledge (Phrozen Keep, OpenDiablo2), and **tests on 37 real DC6 files (7,083 frames)**.
>
> **Confidence markers used throughout:**
> * ✅ **verified**: tested on real files in this project
> * ⚠ **observed**: seen in real files, but there are known exceptions or the meaning is unclear
> * ❓ **unverified**: community knowledge, not confirmed here

---

## Contents
1. [What a DC6 is](#1-what-a-dc6-is)
2. [Cheat sheet](#2-cheat-sheet)
3. [File layout](#3-file-layout)
4. [Coordinates, offsets and frame order](#4-coordinates-offsets-and-frame-order)
5. [Pixel encoding (RLE)](#5-pixel-encoding-rle)
6. [Worked example: MaxiMap.dc6, byte by byte](#6-worked-example-maximapdc6-byte-by-byte)
7. [Reference implementation (Python)](#7-reference-implementation-python)
8. [Limits and conventions (tiles, fonts, animations)](#8-limits-and-conventions)
9. [Palettes and colormaps](#9-palettes-and-colormaps)
10. [Operations: open, preview, edit, export, import](#10-operations)
11. [Validation checklist](#11-validation-checklist)
12. [Lossless image formats for exchange](#12-lossless-image-formats-for-exchange)
13. [Existing tools (survey)](#13-existing-tools-survey)
14. [Sample corpus and MaxiMap facts](#14-sample-corpus-and-maximap-facts)
15. [Overview images (technique used by DC6-Overview)](#15-overview-images-technique-used-by-dc6-overview)
16. [Open questions](#16-open-questions)
17. [Glossary](#17-glossary)
18. [Sources](#18-sources)

---

## 1. What a DC6 is

**Summary:** DC6 = a container of *directions × frames* of **8-bit palette-indexed** images with simple
run-length transparency. **It contains no palette**: the colours come from the game's palette files.

DC6 is Blizzard's sprite format for **Diablo II** (classic 1.00–1.14d and mods such as *Project Diablo 2*).
Diablo II: Resurrected uses other formats for its HD graphics but still reads the classic files in legacy mode.

| Typical use | Example files | Shape |
|---|---|---|
| Inventory / item graphics | `invaar.dc6`, `invcap.dc6` | 1 direction × 1 frame |
| UI panels, screens | `800ctrlpnl7.dc6`, title screens | 1 × N frames (split into 256×256 tiles) |
| Fonts | `font8.dc6` … `font42.dc6` (+ `.tbl` metrics) | 1 × 256 frames |
| Automap tiles | `MaxiMap.dc6`, `MaxiMapS.dc6` | 1 × ~1500 frames (16×32 / 8×16) |
| Simple animations | `hlthmana.dc6`, `nenu3.dc6`, `mptrlitghhth.dc6` | D directions × F frames |
| Level-entry messages | `U5L1.dc6` | 1 × 1–2 frames |

Its sibling **DCC** stores large animated sprites (monsters, players) with a much more complex
bit-stream codec. It is out of scope here (SixDice reads and writes both).

---

## 2. Cheat sheet

```
All integers: little-endian, 32-bit.

FILE   = HEADER(24) + POINTER[N](4·N) + FRAME[0] + FRAME[1] + … + FRAME[N-1]
         N = directions × frames_per_dir

HEADER = int32 version (=6) | uint32 flags (=1) | uint32 encoding (=0) | byte[4] termination
         | int32 directions | int32 frames_per_dir

FRAME  = int32 flip (=0) | int32 width | int32 height | int32 offset_x | int32 offset_y
         | uint32 unknown (=0) | uint32 next_block | int32 length
         | byte data[length] | byte terminator[3]

next_block = frame_offset + 32 + length + 3    (= offset of the next frame header)

PIXEL OPCODES (rows bottom → top):
  0x80        end of row (x = 0, move one row up)
  0x81..0xFF  skip (c & 0x7F) transparent pixels, 1..127
  0x01..0x7F  copy the next c bytes as palette indices
  0x00        invalid / no-op

Palette index 0 = transparent. Palette files (.dat/.pal) = 768 bytes, B,G,R order, 8 bit.
```

---

## 3. File layout

**Summary:** a 24-byte header, a table of absolute frame offsets, then the frames back to back.

```
offset 0x00  ┌──────────────────────────────────────┐
             │ File header (24 bytes)               │
0x18         ├──────────────────────────────────────┤
             │ Frame pointer table                  │  N × uint32 (absolute file offsets)
24 + 4·N     ├──────────────────────────────────────┤
             │ Frame 0: header (32 bytes)           │
             │          pixel data (length bytes)   │
             │          terminator (3 bytes)        │
             ├──────────────────────────────────────┤
             │ Frame 1 …                            │
             └──────────────────────────────────────┘  EOF directly after the last terminator
```
✅ In all 37 sample files, frame 0 starts exactly at `24 + 4·N`, the frames are stored contiguously in
pointer order, and the file ends right after the last frame's terminator.

### 3.1 File header (24 bytes)

| Offset | Type | Name (other names used by tools) | Typical value | Notes |
|---|---|---|---|---|
| 0x00 | int32 | `version` | **6** | ✅ Anything else is not a DC6. This is the only hard magic number. |
| 0x04 | uint32 | `flags` (`unknown1`, `sub_version`) | **1** | ✅ always 1 in samples. ❓ said to mean "serialised cel file". |
| 0x08 | uint32 | `encoding` (`unknown2`, `zeros`) | **0** | ✅ always 0 in samples. |
| 0x0C | byte[4] | `termination` | `EE EE EE EE` or `CD CD CD CD` | ⚠ Blizzard's own `MaxiMap.dc6` (vanilla *and* PD2) has `00 00 00 00` here. |
| 0x10 | int32 | `directions` | 1 … 32 | number of directions (animation angles) |
| 0x14 | int32 | `frames_per_dir` | 1 … n | frames per direction (the same for every direction) |

`0xCD` is MSVC's "uninitialised heap" fill and `0xEE` is the fill used by Blizzard's and the community's
writers. Both are **meaningless padding**. A writer should keep the original bytes, or use `EE`.

### 3.2 Frame pointer table
`uint32 pointer[N]`: the absolute file offset of each frame header.
Frame index of *(direction d, frame f)* = `d * frames_per_dir + f`.
**Always trust this table.** Don't rely on `next_block` chaining.

### 3.3 Frame header (32 bytes) + data + terminator

| Offset | Type | Name | Notes |
|---|---|---|---|
| +0x00 | int32 | `flip` | ✅ **0** = rows stored bottom-up (all samples). ❓ non-zero = top-down. Treat it as a warning. |
| +0x04 | int32 | `width` | pixels |
| +0x08 | int32 | `height` | pixels |
| +0x0C | int32 | `offset_x` | X of the frame's **left** edge relative to the sprite origin (see §4) |
| +0x10 | int32 | `offset_y` | Y of the frame's **bottom** edge relative to the origin (screen Y grows downward) |
| +0x14 | uint32 | `unknown` | ✅ always 0. SixDice: "optional frame data", which it refuses to keep. |
| +0x18 | uint32 | `next_block` | ✅ absolute offset of the next frame header = `ptr + 32 + length + 3` (100 % of samples) |
| +0x1C | int32 | `length` | number of encoded pixel bytes, **excluding** the 3 terminator bytes |
| +0x20 | byte[length] | `data` | encoded pixels (§5) |
| … | byte[3] | `terminator` | ⚠ usually repeats the header termination byte (`EE EE EE` / `CD CD CD`). MaxiMap uses `CD CD CD` while its header says `00 00 00 00`, so **never validate strictly**. |

### 3.4 The same as C and Python structs

```c
#pragma pack(push, 1)
typedef struct {            /* 24 bytes */
    int32_t  version;       /* 6 */
    uint32_t flags;         /* 1 */
    uint32_t encoding;      /* 0 */
    uint8_t  termination[4];/* EE EE EE EE | CD CD CD CD | 00 00 00 00 */
    int32_t  directions;
    int32_t  frames_per_dir;
    /* followed by: uint32_t pointer[directions * frames_per_dir]; */
} DC6_HEADER;

typedef struct {            /* 32 bytes */
    int32_t  flip;          /* 0 = bottom-up */
    int32_t  width, height;
    int32_t  offset_x;      /* left edge relative to origin   */
    int32_t  offset_y;      /* bottom edge relative to origin */
    uint32_t unknown;       /* 0 */
    uint32_t next_block;    /* ptr + 32 + length + 3 */
    int32_t  length;        /* data bytes without the 3 terminator bytes */
    /* followed by: uint8_t data[length]; uint8_t terminator[3]; */
} DC6_FRAME_HEADER;
#pragma pack(pop)
```

```python
import struct
HEADER       = struct.Struct("<iII4sii")    # version, flags, encoding, termination, directions, frames_per_dir
FRAME_HEADER = struct.Struct("<iiiiiIIi")   # flip, width, height, offset_x, offset_y, unknown, next_block, length
```

---

## 4. Coordinates, offsets and frame order

**Summary:** pixels are drawn relative to a sprite **origin** (e.g. the feet of a character). `offset_x` is
where the frame's left edge is; `offset_y` is where its **bottom** edge is.

```
                  x →
        origin ─► ┼────────────────────────────
                  │
    offset_x < 0  │        frame occupies:
   ┌──────────────┼───┐      x = offset_x … offset_x + width − 1
   │   frame      │   │      y = offset_y − height … offset_y − 1
   │              │   │    (screen y grows downward)
   └──────────────┼───┘ ◄── bottom edge at y = offset_y
                  │
                  y ↓
```

* Inventory items, fonts and most UI pieces use offset (0, 0).
* Animations use real offsets. All frames of an animation share the origin, so they line up when played.
* Example (PD2 `MaxiMap.dc6`, frame 1558): 90×87 with offset (−32, 27).
* Frame order in the file: direction 0 frames 0…F−1, then direction 1, and so on.
* Bounding box of an animation (dc6edit's method): `x1 = min(offset_x)`, `x2 = max(offset_x + width)`,
  `y1 = min(offset_y − height)`, `y2 = max(offset_y)`. Drawing frame *i* in that box puts its bottom row at
  `box_bottom + offset_y − y2`.

---

## 5. Pixel encoding (RLE)

**Summary:** rows are written from the **bottom row upward**. A row is a sequence of "skip n transparent" and
"copy n indices" commands and always ends with `0x80`. Trailing transparent pixels of a row are simply not written.

| Byte `c` | Meaning |
|---|---|
| `0x80` | **End of row**: x = 0, y = y − 1 (one row up) |
| `0x81 … 0xFF` | **Skip** `c & 0x7F` transparent pixels (1…127) |
| `0x01 … 0x7F` | **Literal run**: the next `c` bytes are palette indices, copied as they are |
| `0x00` | invalid / no-op (dc6con reports "found byte 00") |

Transparency is **implicit**: skipped pixels and everything after a row's last command are transparent.
Palette **index 0 = transparent**. Writing index 0 inside a literal run is technically possible, but every
encoder treats index 0 as transparent, so it becomes transparent after a round trip.

### 5.1 Canonical encoder (reproduces Blizzard's bytes exactly) ✅
These rules reproduce the original files **byte-for-byte for 7,082 of 7,083 sample frames** (37 files). The only
exception is DC6 Creator's own `logo.dc6`. For each row from the bottom (`y = height−1`) to the top (`y = 0`):
1. Drop trailing transparent pixels; they are not encoded.
2. Walk the rest of the row:
   * a transparent run of n pixels → write `0xFF` while n > 127 (n −= 127), then `0x80 | n`
   * an opaque run → write chunks of ≤ 127: `len`, followed by `len` index bytes
3. Write `0x80`. This applies to **every** row, including empty rows and the top row.

Then add the 3 terminator bytes. A frame of height h therefore contains exactly **h** end-of-row bytes.

> Why it matters: with this encoder, *decode → encode* of an unchanged frame reproduces the file
> exactly. That is a strong self-test, and an unchanged frame can be detected byte for byte.

**Valid but non-canonical variants** (the game accepts them):
* DC6 Creator writes empty rows as `FF FF 80` (explicit skips up to the width).

**Known broken encoders (don't copy):**
* dc6edit 1.02 stops one row early (`if (y <= 0)`) and **drops the top row**.
* SixDice < 0.61 wrote skips > 127 incorrectly, which **crashes the game** (D2's decoder is fragile).

### 5.2 Robust decoder rules
* Clip pixels outside `width × height` and report a warning ("span overrun").
* More end-of-row bytes than rows → warning; stop writing rows above the top.
* `length` past the end of the file → error (or truncate with a warning).
* `next_block` disagrees with the pointer table → warning; use the pointer table.
* `flip ≠ 0` → decode top-down (start at y = 0, move y + 1 on each end-of-row).

---

## 6. Worked example: MaxiMap.dc6, byte by byte

PD2 `MaxiMap.dc6` (Season 14), the first bytes of the file:

```
offset 0x00: 06 00 00 00 | 01 00 00 00 | 00 00 00 00 | 00 00 00 00 | 01 00 00 00 | 28 06 00 00
             version=6     flags=1       encoding=0    termination   directions=1  frames=0x628=1576
offset 0x18: B8 18 00 00 | 28 19 00 00 | A4 19 00 00 | …
             frame 0 at 6328, frame 1 at 6440, frame 2 at 6564   (24 + 4·1576 = 6328 ✓)
```

Frame 0 header at offset 6328:
```
00 00 00 00 | 10 00 00 00 | 20 00 00 00 | 00 00 00 00 | 00 00 00 00 | 00 00 00 00 | 28 19 00 00 | 4D 00 00 00
flip=0        width=16      height=32     offset_x=0    offset_y=0    unknown=0     next=6440     length=77
check: 6328 + 32 + 77 + 3 = 6440 ✓
```

Frame 0 pixel data (77 bytes), decoded step by step:
```
80                    row 31 (bottom): empty → end of row
88 01 C1 81 01 BD 80  row 30: skip 8, copy 1 pixel [C1], skip 1, copy 1 pixel [BD], end of row
86 01 C1 85 01 BD 80  row 29: skip 6, [C1], skip 5, [BD], end of row
82 01 C1 81 01 C1 …   row 28: …
…
80 80 80 80 80 …      rows above: empty (only the bottom part of this automap tile has pixels)
then 3 terminator bytes: CD CD CD
```

Frame 1558 header (an oversize frame):
```
00 00 00 00 | 5A 00 00 00 | 57 00 00 00 | E0 FF FF FF | 1B 00 00 00 | 00 00 00 00 | 9F 98 04 00 | 1C 1E 00 00
flip=0        width=90      height=87     offset_x=−32  offset_y=27   unknown=0     next=301215   length=7708
```

---

## 7. Reference implementation (Python)

Self-contained, standard library only. It reads, decodes, encodes and writes DC6 files. ✅ Tested on all 37 sample
files: the round trip is byte-identical (also with every frame re-encoded, except DC6 Creator's `logo.dc6`),
as long as the original encoded data and terminators are kept.

```python
import struct

HEADER = struct.Struct("<iII4sii")
FRAME_HEADER = struct.Struct("<iiiiiIIi")


def read_dc6(data: bytes) -> dict:
    """Parse a DC6. Returns header fields + a list of frames with decoded pixels (rows top → bottom)."""
    version, flags, encoding, term, dirs, fpd = HEADER.unpack_from(data, 0)
    if version != 6:
        raise ValueError(f"not a DC6 (version {version})")
    n = dirs * fpd
    pointers = struct.unpack_from(f"<{n}I", data, HEADER.size)
    frames = []
    for ptr in pointers:
        flip, w, h, ox, oy, unknown, next_block, length = FRAME_HEADER.unpack_from(data, ptr)
        start = ptr + FRAME_HEADER.size
        encoded = data[start:start + length]
        frames.append({
            "width": w, "height": h, "offset_x": ox, "offset_y": oy, "flip": flip, "unknown": unknown,
            "pixels": decode(encoded, w, h, flip),        # list of rows, each a bytearray of indices
            "encoded": encoded, "tail": data[start + length:start + length + 3],
        })
    return {"flags": flags, "encoding": encoding, "termination": term,
            "directions": dirs, "frames_per_dir": fpd, "frames": frames}


def decode(data: bytes, w: int, h: int, flip: int = 0) -> list[bytearray]:
    rows = [bytearray(w) for _ in range(h)]               # 0 = transparent
    x, y, step, i = 0, (h - 1 if flip == 0 else 0), (-1 if flip == 0 else 1), 0
    while i < len(data):
        c = data[i]; i += 1
        if c == 0x80:                                     # end of row
            x, y = 0, y + step
        elif c & 0x80:                                    # skip transparent pixels
            x += c & 0x7F
        elif c:                                           # literal run of c indices
            run = data[i:i + c]; i += c
            if 0 <= y < h:
                k = max(0, min(len(run), w - x))          # clip to the frame width
                rows[y][x:x + k] = run[:k]
            x += c
    return rows


def encode(rows: list[bytes]) -> bytes:
    """Canonical (Blizzard-identical) encoder."""
    out = bytearray()
    for row in reversed(rows):                            # bottom row first
        last = len(row)
        while last and row[last - 1] == 0:                # trailing transparency is not written
            last -= 1
        x = 0
        while x < last:
            start = x
            if row[x] == 0:
                while x < last and row[x] == 0:
                    x += 1
                n = x - start
                while n > 0x7F:
                    out.append(0xFF); n -= 0x7F
                out.append(0x80 | n)
            else:
                while x < last and row[x] != 0 and x - start < 0x7F:
                    x += 1
                out.append(x - start); out += row[start:x]
        out.append(0x80)                                  # every row ends with 0x80
    return bytes(out)


def write_dc6(dc6: dict) -> bytes:
    frames = dc6["frames"]
    n = len(frames)
    offset = HEADER.size + 4 * n
    pointers, chunks = [], []
    for f in frames:
        data = f.get("encoded") or encode(f["pixels"])
        next_block = offset + FRAME_HEADER.size + len(data) + 3
        pointers.append(offset)
        chunks += [FRAME_HEADER.pack(f.get("flip", 0), f["width"], f["height"], f["offset_x"], f["offset_y"],
                                     f.get("unknown", 0), next_block, len(data)),
                   data, f.get("tail", b"\xEE\xEE\xEE")]
        offset = next_block
    head = HEADER.pack(6, dc6.get("flags", 1), dc6.get("encoding", 0), dc6.get("termination", b"\xEE" * 4),
                       dc6["directions"], dc6["frames_per_dir"])
    return head + struct.pack(f"<{n}I", *pointers) + b"".join(chunks)
```

Palette loading (Diablo II `.dat`, BGR order, 8 bit):
```python
def load_dat_palette(raw: bytes) -> list[tuple[int, int, int]]:
    return [(raw[i * 3 + 2], raw[i * 3 + 1], raw[i * 3]) for i in range(256)]   # → (R, G, B)
```

---

## 8. Limits and conventions

| Topic | Rule |
|---|---|
| Max in-game frame size | ⚠ **256 × 256**. SixDice: *"Diablo II does not accept DC6 files with frames containing images larger than 256x256."* The format itself allows more. |
| Large images (UI, 800×600 screens) | Split into **256 × 256 tiles**, row-major, left → right, top → bottom; the last column/row is narrower or shorter. dc6con rebuilds them by assuming "a frame that is not 256 wide ends a row". DC6 Creator: *"Show Frames as Full Image"* (Frames X × Frames Y). |
| Fonts | 1 × 256 frames (one per character code), all the same size. Glyph widths/metrics live in a separate `fontXX.tbl`. Location: `data\local\font\latin\` in `d2data.mpq`. |
| Tables (automap, fonts) | All frames the same size, offset 0/0 (dc6table's "is table" check). ⚠ PD2's MaxiMap breaks this (6 oversize frames, §14). |
| Directions | 1 for static graphics; 4/8/16/32 for animations. `frames_per_dir` is the same for all directions. Adding or removing a frame must happen in every direction. |
| Empty frames | width or height 0 is possible in theory and must not crash a reader (DC6 Creator reports an error for it). |

---

## 9. Palettes and colormaps

### 9.1 `.dat` / `.pal` (Diablo II native)
* **768 bytes = 256 × (B, G, R)**, 8 bits per channel. **Note the BGR order.**
* Game location: `data\global\palette\<ACT1|ACT2|…>\pal.dat` (inside the MPQs).
* DC6 Creator's `data/pal/*.pal` files use **the same format** (✅ `act1.pal` is byte-identical to `act1.dat`, MD5 `2eac8a8f637010b168578a00004095b0`).
* First bytes of `act1.dat`: `00 00 00 | 00 00 24 | 08 18 1C | 10 24 2C` → index 1 = RGB(36, 0, 0).

Palettes shipped with DC6 Creator (and bundled with DC6-Overview):
`act1 act2 act3 act4 act5 units menu0 menu1 menu2 menu3 menu4 sky static trademark endgame fetchar loading`.

Which palette applies: in-game objects and UI use **act1** (or the current act's palette); the character
select screen uses `fechar` (e.g. `dc6edit nenu3.dc6 fechar.dat`); loading screens use `loading`.

Useful act1 indices:

| Index | RGB | Use |
|---|---|---|
| 0 | 0, 0, 0 | **transparent** |
| 4 | 60, 52, 24 | dark gold, the border and number colour of the classic DC6 Overview |
| 10 | 188, 0, 0 | red, the "oversize" cross marker |
| 12 | 244, 196, 108 | light gold |
| 255 | 255, 255, 255 | white; dc6edit uses it for its origin marker dots |

### 9.2 ⚠ The 6-bit trap (Allegro)
All the old C tools load palettes with `value >> 2` (Allegro's VGA 0–63 range), and Allegro's `save_pcx`
writes `value × 4`. Any channel that is not a multiple of 4 is **lost** (e.g. `0xFF` → `0xFC`).
Modern code should keep the full 8-bit values.

### 9.3 Colormaps (item tints, `dc6color`)
`colormaps/*.dat` = **21 tints × 256 bytes** = 5,376 bytes. Each tint is an *index → index* remap table.

| Family file | ID used in item tables (transform / invtransform) |
|---|---|
| `grey.dat` | 1 |
| `grey2.dat` | 2 |
| `greybrown.dat` | 5 |
| `invgrey.dat` | 6 |
| `invgrey2.dat` | 7 |
| `invgreybrown.dat` | 8 |

Tint `t` (0–20) = the `transformcolor` value. Shown colour = `palette[colormap[t][index]]`.

### 9.4 Other palette formats worth supporting
| Format | Layout | Notes |
|---|---|---|
| D2 `.dat` / `.pal` | 768 bytes, BGR | native |
| Photoshop `.act` | 768 bytes **RGB** (+ optional 4 bytes: count, transparent index) | the most common exchange format |
| JASC-PAL (Paint Shop Pro) | text: `JASC-PAL`, `0100`, `256`, then `r g b` lines | |
| GIMP `.gpl` | text | |
| Embedded | the palette inside a PCX/PNG/BMP/GIF | "take palette from image" |

---

## 10. Operations

### 10.1 Open
1. Read the whole file. DC6 files are small (MaxiMap ≈ 300 KB).
2. Parse the header; check `version == 6` and `N > 0`, with sanity caps (e.g. N ≤ 1,000,000).
3. Read the pointer table; for every frame parse the 32-byte header and slice out `length` bytes.
4. Decode all frames at once or on demand. 1,576 frames take well under a second in Python.
5. Keep the **raw header fields, the original encoded bytes and the terminators**, for a byte-exact re-save.

### 10.2 Preview
* Indexed image with a 256-colour table (Qt: `QImage.Format_Indexed8` + `setColorTable`; Pillow: mode `"P"`).
  Index 0 → transparent.
* Integer zoom (nearest neighbour) for pixel-exact viewing.
* Show transparency on a plain background and draw a **1 px line around the frame area**, so the frame size and
  transparent edges are visible. This is clearer than a checkerboard.
* Optional: origin cross-hair, offset box, animation playback per direction, palette switch, colormap tints.

### 10.3 Edit
* Change offsets (one frame, or all frames by +dx/+dy). This does not touch the pixel data.
* Replace a frame's pixels (import); trim transparent borders (adjust the offsets accordingly).
* Insert, delete or reorder frames; add or delete directions (keep `frames_per_dir` the same everywhere).
* Split a big image into 256² tiles, or join tiles back into one image.
* On save: re-encode only changed frames, recompute pointers, `next_block` and `length`, then read the
  result back to verify it, and keep a backup of the original.

### 10.4 Export (lossless only)
| Mode | Output |
|---|---|
| Single frame | `0004.png` / `.pcx` / `.bmp` / `.gif` / `.tif` (8-bit indexed, palette included) |
| All frames | `0000.ext … NNNN.ext` + a **metadata sidecar** (JSON: directions, frames_per_dir, per frame w/h/offset_x/offset_y, palette) |
| Sheet / table | all frames in a grid; can be re-imported when every frame has the same size (dc6table style) |
| Animation | GIF per direction (indexed, transparent index 0) |

How older tools stored the offsets:
* dc6edit: two **white origin dots** (index 255) in an extra row and column of every PCX
* SixDice: a metadata file with the absolute virtual offset
* DC6 Creator: an **INI file**: `[Main]` with `FileName`, `Directions`, `FramesDir`, `FileType`, `Img_X0`, `Img_Y0`, `FramedGIF`;
  then a `[Direction Data:NN]` section per direction with `X_Offset`, `Y_Offset`, `Width`, `Height`.

### 10.5 Import
1. Load the image. If it is **indexed** and its palette matches the target palette for the used indices →
   take the indices 1:1 (truly lossless).
2. Otherwise (another palette, or RGB/RGBA) → map each colour **exactly** to the palette:
   * fully transparent pixels (alpha 0) and pure black (0, 0, 0) → index 0
   * an exact RGB match → the lowest palette index ≥ 1 with that colour
   * **no exact match → reject** and report the number of colours and pixels, plus the first position and RGB value.
     Fix: "convert to Indexed (8-bit) with the act1 palette, without dithering".
   * semi-transparent pixels (alpha 1–254) → reject.
   * Nearest-colour mapping should only ever be an explicit opt-in, and must **exclude index 0** so dark
     pixels don't turn transparent (SixDice's key feature).
3. Size differs from the frame being replaced → warn (show before/after), import only if the user confirms.
4. Frame larger than 256×256 → warn (the game won't show it).
5. Self-check: encode → decode must reproduce the imported indices.
6. Batch import: file name = frame number (`0004.bmp` → frame 4). Check **all** files first (duplicates, numbers
   out of range, bad files), show a report, and only then apply the valid ones.

---

## 11. Validation checklist

| Level | Check | Typical message |
|---|---|---|
| ERROR | file < 24 bytes | "File is only n bytes; a DC6 header needs 24." |
| ERROR | `version ≠ 6` | "Not a DC6 file (version v, expected 6)." |
| ERROR | directions ≤ 0, frames_per_dir ≤ 0, or absurd N | "Invalid frame count." |
| ERROR | pointer table, frame header or frame data past EOF | "Frame i: … runs past the end of the file." |
| ERROR | width/height negative or absurd | "Frame i: invalid size w×h." |
| WARNING | `flags ≠ 1`, `encoding ≠ 0`, termination not EE/CD/00 | "Header flags = x (usually 1)." |
| WARNING | `flip ≠ 0`, `unknown ≠ 0` | "flip = x (rows stored top-down; unusual)." |
| WARNING | `next_block ≠ ptr + 32 + length + 3` | "next_block does not point right after this frame." |
| WARNING | pixels outside the frame, end-of-row count ≠ height, `0x00` opcodes | from the decoder |
| WARNING | frame > 256×256 | "Diablo II can't show it." |
| WARNING | unused bytes after the last frame | "n unused byte(s) after the last frame." |
| INFO | re-encoding is not byte-identical | "written by a non-Blizzard encoder (still valid)" |
| INFO | frames larger than the most common size | the "oversize" list (§15) |

---

## 12. Lossless image formats for exchange

| Format | Indexed 8-bit | Palette stored | Transparency | Multi-frame | Lossless | Verdict |
|---|---|---|---|---|---|---|
| **PNG-8** | ✅ | ✅ | ✅ (`tRNS`, index 0) | ✗ | ✅ | modern default: small, every editor opens it |
| **PCX** v5 8 bpp RLE | ✅ | ✅ (768 bytes at the end, marker 0x0C) | ✗ (index 0 by convention) | ✗ | ✅ | **the classic D2 modding format**; all old tools use it |
| **BMP** 8 bpp | ✅ | ✅ | ✗ | ✗ | ✅ | universal, uncompressed |
| **GIF** | ✅ | ✅ | ✅ (1 index) | ✅ | ✅ (LZW) | animations |
| **TIFF** (palette) | ✅ | ✅ | (✅) | ✅ (pages) | ✅ | optional; DC6 Creator supports it |
| PNG-24/32 | ✗ | — | ✅ | ✗ | ✅ | needs exact palette mapping on import (§10.5) |
| ~~JPG~~ | ✗ | — | ✗ | ✗ | ❌ | **never for frames**: lossy, destroys the palette indices. Fine for a final *viewing* image (e.g. an overview). |

**PCX details** (from dc6con): header `manufacturer=0x0A, version=5, encoding=1, bits_per_pixel=8,
color_planes=1`, `bytes_per_line = width` (should be even; pad odd widths), `palette_type=1`.
RLE: a byte ≥ `0xC0` marks a run, length = `byte & 0x3F`, followed by the value; a single value ≥ 0xC0 must be
written as `0xC1, value`. The palette is at the end: `0x0C` + 768 bytes RGB.

---

## 13. Existing tools (survey)

| Tool | Author / year | Language | What it does | What we learned |
|---|---|---|---|---|
| **dc6con 1.0c** | Ryan Smith & Forest Hale 2000, modified by Paul Siramy 2002/2011 (GPL-2) | C | DC6 ↔ PCX; splits big images into 256² tiles; `-transcol`, `-pal` | built-in act1 palette, tile reassembly heuristic, robust decoder with overrun reports |
| **dc6table** | Paul Siramy | C / Allegro | DC6 ↔ PCX **grid** of equal-size frames | the ancestor of DC6 Overview; requires uniform frames with offset 0/0 |
| **dc6font** | Paul Siramy 2002 | C / Allegro | 256-glyph font DC6 ↔ 16×16 PCX table | fonts = 1 × 256 equal frames |
| **dc6edit 1.02** | Paul Siramy 2002/2011 | C / Allegro | animated DC6 ↔ one PCX per frame (`name-DD-FFF.pcx`) with origin dots + a `-debug.pcx` overlay | offset semantics (§4); its encoder drops the top row |
| **dc6color** | Paul Siramy 2002/2005 | C / Allegro | renders item DC6s in all 6 colormap families × 21 tints | colormap format (§9.3) |
| **txtdc6** | Joel Falcou 2003 | exe only | builds level-entry message DC6s from text + a font DC6 | font DC6 + `.txt` metrics |
| **SixDice 0.63** | Zachary E. Palmer 2006 | Java | full DC6 **and DCC** editor: GUI + batch, zoom, split/join frames, trim borders, centre offset, palette-safe import | validation messages, "never map dark colours to transparent", the 256² limit, the skip > 127 bug |
| **DC6 Creator 1.02** | **Afj666**, 2004 | C++ / MFC (.NET 2002) + CxImage | GUI editor (§13.1) | INI metadata format, framed full-image view |

### 13.1 DC6 Creator 1.02 (binary only), what is known
From the program's strings and Phrozen Keep threads:
* "DC6 Creator Version 1.0, Copyright (C) 2004" by Afj666. Needs the MSVC .NET 2002 runtime (`MFC70`, `MSVCR70`,
  `MSVCP70`, installed by its `Install.exe`). Image I/O via **CxImage** (`cximage.dll`), INI via `CIniEx.dll`.
* Features: open/save/new DC6; add/insert/delete **frames** and **directions**; import an image into a frame
  (*"Yes = Insert / No = Overwrite"*); export the current frame; **Export All** (folder + INI); **INI → DC6**;
  a **Change Offsets** dialog; a palette selector (`data/pal/palettes.ini`); Preview; *Show Frames as Full Image*; Save Framed Image.
* Formats: import BMP, PCX, TIF, GIF (multi-frame GIF → *"import all frames?"*), JPG; export BMP, GIF, TIF, PCX, JPG.
* Behaviour: *"The image you want to import is larger than allowed for a DC6 frame, do you want to split the image
  into frames after the selected one?"*; the imported image gets the **currently selected palette**; users report
  **crashes with non-256-colour images**; black (0,0,0) = transparent.
* Its validator's messages: `Fileformat not DC6`, `m_iDirections <= 0`, `m_iFramesPerDirection <= 0`,
  `m_iLength <= 0`, `DecodeDC6ImageData: Offset > Imagesize`, `m_iWidth/m_iHeight <= 0`.
* Its encoder is non-canonical (`FF FF 80` for empty rows, see its `data/logo.dc6`, 256×256).

---

## 14. Sample corpus and MaxiMap facts

| File | Size (bytes) | Dirs × frames | Frame sizes | Header term. | Frame tail |
|---|---|---|---|---|---|
| PD2 `MaxiMap.dc6` (Season 14) | 305,087 | 1 × **1576** | 1570× 16×32 + **6 oversize** | `00000000` | `CDCDCD` |
| PD2 `MaxiMapS.dc6` (small automap) | 142,274 | 1 × 1576 | 1570× 8×16 + 6 oversize | `00000000` | `CDCDCD` |
| hand-patched MaxiMap (oversize frames replaced by 16×32 thumbnails) | 295,993 | 1 × 1572 | all 16×32 | `00000000` | `CDCDCD` |
| vanilla `MaxiMap.dc6` | — | 1 × **1499** | all 16×32 | `00000000` | `CDCDCD` |
| `font42.dc6` / `font46.dc6` | — | 1 × 256 | uniform | `EE` / `CD` | same |
| `inv*.dc6` (24 files) | — | 1 × 1 | 28×28 … 56×112 | `EE` / `CD` | same |
| DC6 Creator `logo.dc6` | 36,349 | 1 × 1 | 256×256 | `CD` | `CD` (non-canonical RLE) |

✅ PD2 `MaxiMap.dc6` = vanilla frames 0–1498 (byte-identical) + 77 PD2 additions (1499–1575).

Oversize frames in PD2 MaxiMap (Season 14):

| Frame | Size | Offset |
|---|---|---|
| 1550 | 32×48 | (−16, 0) |
| 1551 | 32×48 | (0, 0) |
| 1552 | 32×32 | (−16, 0) |
| 1553 | 32×32 | (0, 0) |
| 1558 | 90×87 | (−32, 27) |
| 1559 | 19×32 | (0, 0) |

`MaxiMapS` has the same six at half size (16×24, 16×16, 45×44, 10×16).

---

## 15. Overview images (technique used by DC6-Overview)

**Summary:** show all frames of a DC6 in one grid image (e.g. to find automap tiles quickly).

* **Standard size** = the most common frame size (MaxiMap: 16×32). Every cell has this size.
* **Oversize frames** (bigger than the standard size) are cut to the cell: **keep the top, cut the bottom, and cut
  left and right equally** (x0 = (w − cell_w) / 2). A **3×3 red "+"** (act1 index 10, RGB 188,0,0) at the cell's
  top-left marks them. ✅ This reproduces hand-made thumbnails exactly for 1550–1553 and 1559.
* Classic v1.0 grid (1× pixels): 1 px border in RGB(60,52,24); numbers centred above the cell in the Allegro 8×8
  font (slashed zero), every 10th frame; number row 9 px; gap below each row 3 px; side margin 12 px; black background.
  Cell pitch = frame + 2 px (borders side by side); the newer "shared wall" mode uses frame + 1 px.
* Upscaling ×2 like Photoshop "Preserve Details 2.0": the closest classic filter is **nearest neighbour**
  (PSNR 29.9 dB vs Lanczos 28.4). A learned 7×7 linear filter per output sub-pixel, fitted by least squares to a
  real Photoshop result, reaches **35.2 dB** (hold-out).

---

## 16. Open questions
* ❓ The exact meaning of the header fields `flags` (1) and `encoding` (0) in the game DLL (`D2CMP.dll`). Keep them on save.
* ❓ Whether `flip ≠ 0` (top-down rows) occurs in any shipped file. Decoders should support it anyway.
* ❓ The game's behaviour with frames > 256 px in specific contexts (automap vs UI).
* ❓ Whether the game reads the 3 terminator bytes or `next_block` at all (all writers keep them consistent).

---

## 17. Glossary
| Term | Meaning |
|---|---|
| Frame | one image inside a DC6 |
| Direction | a group of frames for one facing angle of an animation |
| Origin | the sprite's anchor point; offsets are relative to it |
| Palette index | a byte 0–255 that selects a colour from the palette; 0 = transparent |
| RLE | run-length encoding; here: "skip n transparent" / "copy n pixels" commands |
| Canonical encoding | the byte layout Blizzard's tools produce (§5.1) |
| Termination / terminator | 4 padding bytes in the header, 3 after each frame (`EE` or `CD`) |
| MPQ | Blizzard's archive format holding the game files |
| PD2 | *Project Diablo 2*, a popular Diablo II mod with seasons |

---

## 18. Sources
* Source code in the research collection: `dc6con.c`, `dc6table.c`, `dc6font.c`, `Dc6edit.c`, `dc6color.c` (msvc6/djgpp)
* Binaries analysed: `DC6_Creator.exe` 1.02, `SixDice v0.63.jar` (class `orioni.sixdice.DC6Codec`)
* [DC6 Creator, Phrozen Keep](https://d2mods.info/forum/viewtopic.php?t=23207) ·
  [Phrozen Keep downloads: animation editing](https://d2mods.info/forum/downloadsystemcat?id=23) ·
  [COF, D2, DC6, DS1, DT1, TBL file formats, Phrozen Keep](https://d2mods.info/forum/viewtopic.php?t=724)
* [OpenDiablo2 dc6 decoder](https://github.com/OpenDiablo2/dc6) ·
  [Go package d2dc6](https://pkg.go.dev/github.com/OpenDiablo2/OpenDiablo2/d2common/d2fileformats/d2dc6)
* Item colormap documentation: <http://d2mods.com/forum/kb.php?mode=article&k=57> (from dc6color's ReadMe)
