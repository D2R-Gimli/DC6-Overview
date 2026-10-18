"""256-colour palettes. Diablo II .dat/.pal = 768 bytes BGR, full 8 bit (never shift to 6 bit)."""

from pathlib import Path

import numpy as np

from core.paths import PALETTES_DIR


class Palette:
    __slots__ = ("name", "rgb")

    def __init__(self, rgb: np.ndarray, name: str = "") -> None:
        rgb = np.asarray(rgb, np.uint8).reshape(-1, 3)
        if len(rgb) < 256:
            rgb = np.vstack([rgb, np.zeros((256 - len(rgb), 3), np.uint8)])
        self.rgb: np.ndarray = rgb[:256].copy()
        self.name = name

    @classmethod
    def load(cls, path: Path) -> "Palette":
        path = Path(path)
        data = path.read_bytes()
        if data.startswith(b"JASC-PAL"):
            lines = data.decode("ascii", "replace").split()
            count = int(lines[2])
            values = np.array(lines[3 : 3 + count * 3], np.uint8)
            return cls(values, path.stem)
        if len(data) < 768:
            raise ValueError(f"{path.name}: a palette needs 768 bytes, found {len(data)}.")
        raw = np.frombuffer(data[:768], np.uint8).reshape(256, 3)
        if path.suffix.lower() == ".act":  # Photoshop: RGB order
            return cls(raw, path.stem)
        return cls(raw[:, ::-1], path.stem)  # Diablo II: BGR order

    def to_dat_bytes(self) -> bytes:
        return self.rgb[:, ::-1].tobytes()

    def flat(self) -> list[int]:
        """For Pillow's Image.putpalette()."""
        return self.rgb.reshape(-1).tolist()

    def argb_table(self, transparent_zero: bool = True) -> list[int]:
        """32-bit ARGB values, e.g. for QImage.setColorTable()."""
        table = [0xFF000000 | (int(r) << 16) | (int(g) << 8) | int(b) for r, g, b in self.rgb]
        if transparent_zero:
            table[0] = 0x00000000
        return table

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Palette) and np.array_equal(self.rgb, other.rgb)

    def __hash__(self) -> int:
        return hash(self.rgb.tobytes())


def builtin_palettes() -> dict[str, Path]:
    """Bundled Diablo II palettes, act1 first."""
    found = {p.stem: p for p in sorted(PALETTES_DIR.glob("*.dat"))}
    return dict(sorted(found.items(), key=lambda kv: (kv[0] != "act1", kv[0])))


def default_palette() -> Palette:
    return Palette.load(PALETTES_DIR / "act1.dat")
