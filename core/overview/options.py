"""All overview settings in one JSON-serialisable object."""

from dataclasses import asdict, dataclass, fields

V1_BORDER_RGB = (60, 52, 24)  # act1 index 4, the v1.0 border/number colour
CROSS_RGB = (188, 0, 0)  # act1 index 10, the oversize marker
BORDER_PRESETS: list[tuple[str, tuple[int, int, int]]] = [
    ("D2 gold", V1_BORDER_RGB),
    ("Grey", (96, 96, 96)),
    ("Light grey", (200, 200, 200)),
    ("Dark red", (120, 20, 20)),
    ("Blue", (40, 60, 140)),
    ("Green", (30, 100, 40)),
]
SCALES = (1, 2, 4)
CLASSIC_FONT = "Classic 8×8 (pixel)"  # the Allegro bitmap digits of v1.0


@dataclass(slots=True)
class OverviewOptions:
    columns: int = 60
    number_every: int = 10  # 0 = no numbers
    number_font: str = "Tahoma"  # any installed font, or CLASSIC_FONT
    number_size: int = 7  # pixel size at ×1 (doubled at ×2)
    number_bold: bool = True
    number_rgb: tuple[int, int, int] = V1_BORDER_RGB
    spacing_x: int = 0
    spacing_y: int = 3
    side_margin: int = 12
    collapse_borders: bool = True  # spacing 0 → neighbouring cells share one 1 px wall
    show_border: bool = True
    border_rgb: tuple[int, int, int] = V1_BORDER_RGB
    cross_rgb: tuple[int, int, int] = CROSS_RGB
    upscale_method: str = "photoshop"
    scale: int = 2
    text_line1: str = "Project Diablo 2"
    text_line2: str = "Season 14"
    header_gap: int = 5  # black pixels between header and grid (final image, fixed)
    jpg_quality: int = 92

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OverviewOptions":
        opts = cls()
        names = {f.name for f in fields(cls)}
        for key, value in (data or {}).items():
            if key in names:
                if key.endswith("_rgb"):
                    value = tuple(int(v) for v in value)
                setattr(opts, key, value)
        return opts
