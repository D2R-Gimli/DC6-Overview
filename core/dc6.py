"""DC6 file model: parse (with validation), edit and serialise (see filetype_dc6.md §2, §6)."""

import struct
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np

from core.rle import decode_frame, encode_frame

HEADER = struct.Struct("<iII4sii")  # version, flags, encoding, termination, directions, frames/dir
FRAME_HEADER = struct.Struct("<iiiiiIIi")  # flip, w, h, offset_x, offset_y, unknown, next_block, length
MAX_FRAMES = 1_000_000
MAX_PIXELS = 64 * 1024 * 1024
GAME_MAX_SIZE = 256
KNOWN_TERMINATIONS = (b"\xee" * 4, b"\xcd" * 4, b"\x00" * 4)


class Level(StrEnum):
    ERROR = "Error"
    WARNING = "Warning"
    INFO = "Info"


@dataclass(slots=True, frozen=True)
class Issue:
    level: Level
    message: str
    frame: int | None = None

    def __str__(self) -> str:
        where = f"Frame {self.frame:04d}: " if self.frame is not None else ""
        return f"{self.level}: {where}{self.message}"


class DC6Error(Exception):
    """The data is not a readable DC6 file."""


@dataclass(slots=True, eq=False)
class DC6Frame:
    pixels: np.ndarray  # (height, width) uint8 palette indices, row 0 = top, index 0 = transparent
    offset_x: int = 0
    offset_y: int = 0
    flip: int = 0
    unknown: int = 0
    tail: bytes = b"\xee\xee\xee"
    encoded: bytes | None = None  # original RLE bytes, reused on save while the pixels are untouched
    blank: bool = False  # placeholder added in the GUI; dropped on save unless a graphic is imported

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def set_pixels(self, pixels: np.ndarray) -> None:
        self.pixels = np.ascontiguousarray(pixels, dtype=np.uint8)
        self.encoded = None
        self.flip = 0
        self.blank = False


@dataclass(slots=True, eq=False)
class DC6File:
    directions: int
    frames_per_dir: int
    frames: list[DC6Frame]  # direction-major: index = direction * frames_per_dir + frame
    version: int = 6
    flags: int = 1
    encoding: int = 0
    termination: bytes = b"\xee" * 4
    issues: list[Issue] = field(default_factory=list)

    # ---------------------------------------------------------------- queries
    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def real_frame_count(self) -> int:
        """Frames that will be written on save (blank frames inside the file count, trailing ones don't)."""
        return self.directions * self._saved_frames_per_dir()

    def standard_size(self) -> tuple[int, int]:
        sizes = [f.size for f in self.frames if not f.blank] or [f.size for f in self.frames]
        return Counter(sizes).most_common(1)[0][0] if sizes else (16, 32)

    def default_tail(self) -> bytes:
        tails = Counter(f.tail for f in self.frames if not f.blank)
        if tails:
            return tails.most_common(1)[0][0]
        return self.termination[:3] if self.termination[:3] != b"\x00\x00\x00" else b"\xee\xee\xee"

    def has_blank_gaps(self) -> list[int]:
        """Indices of blank frames that would have to be saved as empty frames (they precede real ones)."""
        keep = self._saved_frames_per_dir()
        return [
            d * self.frames_per_dir + f
            for d in range(self.directions)
            for f in range(keep)
            if self.frames[d * self.frames_per_dir + f].blank
        ]

    # ---------------------------------------------------------------- edits
    def add_blank_frame(self) -> None:
        """Append one blank frame at the end of every direction."""
        w, h = self.standard_size()
        tail = self.default_tail()
        for d in range(self.directions - 1, -1, -1):
            pos = d * self.frames_per_dir + self.frames_per_dir
            self.frames.insert(pos, DC6Frame(np.zeros((h, w), np.uint8), tail=tail, blank=True))
        self.frames_per_dir += 1

    def remove_last_frame(self) -> None:
        """Remove the last frame of every direction."""
        if self.frames_per_dir <= 1:
            raise ValueError("A DC6 file needs at least one frame per direction.")
        for d in range(self.directions - 1, -1, -1):
            del self.frames[d * self.frames_per_dir + self.frames_per_dir - 1]
        self.frames_per_dir -= 1

    # ---------------------------------------------------------------- save
    def _saved_frames_per_dir(self) -> int:
        keep = self.frames_per_dir
        while keep > 0 and all(
            self.frames[d * self.frames_per_dir + keep - 1].blank for d in range(self.directions)
        ):
            keep -= 1
        return keep

    def to_bytes(self) -> bytes:
        """Serialise. Trailing blank frames are dropped, inner blank frames become empty frames."""
        keep = self._saved_frames_per_dir()
        if keep == 0:
            raise ValueError("Nothing to save: all frames are blank.")
        frames = [
            self.frames[d * self.frames_per_dir + f] for d in range(self.directions) for f in range(keep)
        ]
        n = len(frames)
        offset = HEADER.size + 4 * n
        pointers: list[int] = []
        chunks: list[bytes] = []
        for fr in frames:
            data = fr.encoded if fr.encoded is not None else encode_frame(fr.pixels)
            flip = fr.flip if fr.encoded is not None else 0
            next_block = offset + FRAME_HEADER.size + len(data) + 3
            pointers.append(offset)
            chunks.append(
                FRAME_HEADER.pack(
                    flip, fr.width, fr.height, fr.offset_x, fr.offset_y, fr.unknown, next_block, len(data)
                )
            )
            chunks.append(data)
            chunks.append(fr.tail)
            offset = next_block
        head = HEADER.pack(self.version, self.flags, self.encoding, self.termination, self.directions, keep)
        return head + struct.pack(f"<{n}I", *pointers) + b"".join(chunks)

    def commit_saved_state(self) -> None:
        """After a successful save: drop trailing blanks, turn inner blanks into real (empty) frames."""
        keep = self._saved_frames_per_dir()
        self.frames = [
            self.frames[d * self.frames_per_dir + f] for d in range(self.directions) for f in range(keep)
        ]
        self.frames_per_dir = keep
        for fr in self.frames:
            fr.blank = False


# ---------------------------------------------------------------- parsing
def parse_dc6(data: bytes) -> DC6File:
    """Parse and validate. Raises DC6Error for unreadable files; softer problems end up in `.issues`."""
    issues: list[Issue] = []
    if len(data) < HEADER.size:
        raise DC6Error(f"File is only {len(data)} bytes; a DC6 header needs 24.")
    version, flags, encoding, termination, dirs, fpd = HEADER.unpack_from(data, 0)
    if version != 6:
        raise DC6Error(f"Not a DC6 file (version {version}, expected 6).")
    if dirs <= 0 or fpd <= 0 or dirs * fpd > MAX_FRAMES:
        raise DC6Error(f"Invalid frame count: {dirs} direction(s) × {fpd} frame(s).")
    n = dirs * fpd
    table_end = HEADER.size + 4 * n
    if table_end > len(data):
        raise DC6Error(f"Frame pointer table ({n} entries) runs past the end of the file.")
    if flags != 1:
        issues.append(Issue(Level.WARNING, f"Header flags = {flags} (usually 1)."))
    if encoding != 0:
        issues.append(Issue(Level.WARNING, f"Header encoding = {encoding} (usually 0)."))
    if termination not in KNOWN_TERMINATIONS:
        issues.append(
            Issue(Level.WARNING, f"Unusual header termination bytes {termination.hex(' ').upper()}.")
        )

    pointers = struct.unpack_from(f"<{n}I", data, HEADER.size)
    frames: list[DC6Frame] = []
    end_of_data = table_end
    non_canonical = 0
    for i, ptr in enumerate(pointers):
        if ptr + FRAME_HEADER.size > len(data):
            raise DC6Error(f"Frame {i}: header at offset {ptr} lies outside the file.")
        flip, w, h, ox, oy, unknown, next_block, length = FRAME_HEADER.unpack_from(data, ptr)
        start = ptr + FRAME_HEADER.size
        if w < 0 or h < 0 or w * h > MAX_PIXELS:
            raise DC6Error(f"Frame {i}: invalid size {w}×{h}.")
        if length < 0 or start + length > len(data):
            raise DC6Error(f"Frame {i}: pixel data ({length} bytes) runs past the end of the file.")
        encoded = data[start : start + length]
        tail = data[start + length : start + length + 3]
        pixels, warns = decode_frame(encoded, w, h, flip)
        issues += [Issue(Level.WARNING, msg, i) for msg in warns]
        if flip != 0:
            issues.append(Issue(Level.WARNING, f"flip = {flip} (rows stored top-down; unusual).", i))
        if unknown != 0:
            issues.append(Issue(Level.WARNING, f"Unknown frame header field = {unknown} (usually 0).", i))
        if next_block != start + length + 3:
            issues.append(Issue(Level.WARNING, "next_block does not point right after this frame.", i))
        if w > GAME_MAX_SIZE or h > GAME_MAX_SIZE:
            issues.append(
                Issue(Level.WARNING, f"{w}×{h} is larger than 256×256; Diablo II can't show it.", i)
            )
        if not warns and flip == 0 and encode_frame(pixels) != encoded:
            non_canonical += 1
        if len(tail) < 3:
            tail = tail.ljust(3, b"\xee")
        frames.append(DC6Frame(pixels, ox, oy, flip, unknown, tail, encoded))
        end_of_data = max(end_of_data, start + length + 3)

    if end_of_data < len(data):
        issues.append(Issue(Level.WARNING, f"{len(data) - end_of_data} unused byte(s) after the last frame."))
    if non_canonical:
        issues.append(
            Issue(
                Level.INFO,
                f"{non_canonical} frame(s) were written by a non-Blizzard encoder "
                "(still valid; re-encoded only when changed).",
            )
        )
    return DC6File(dirs, fpd, frames, version, flags, encoding, termination, issues)


def load_dc6(path: Path) -> DC6File:
    return parse_dc6(Path(path).read_bytes())


def save_dc6(dc6: DC6File, path: Path, backup: bool = True) -> Path | None:
    """Write the file, verify it by re-reading, keep a one-time `.bak` of the original. Returns the backup."""
    path = Path(path)
    data = dc6.to_bytes()
    check = parse_dc6(data)
    if check.real_frame_count != dc6.real_frame_count:
        raise DC6Error("Verification failed: the written data does not read back correctly.")
    bak = None
    if backup and path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(path.read_bytes())
    path.write_bytes(data)
    dc6.commit_saved_state()
    return bak
