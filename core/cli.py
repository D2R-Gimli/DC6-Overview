"""Command line: `python main.py overview MaxiMap.dc6 --cols 60` / `validate` / `export-frames`."""

import argparse
import sys
from pathlib import Path

from core import APP_NAME, APP_VERSION
from core.dc6 import DC6Error, load_dc6
from core.imageio import EXPORT_FORMATS, export_frame, frame_filename
from core.overview.options import SCALES, OverviewOptions
from core.overview.upscale import METHODS
from core.palette import Palette, builtin_palettes


def _palette(name_or_path: str) -> Palette:
    pals = builtin_palettes()
    return Palette.load(pals[name_or_path] if name_or_path in pals else Path(name_or_path))


def cmd_overview(args: argparse.Namespace) -> int:
    from PySide6.QtGui import QGuiApplication

    from core.overview.pipeline import build_overview, export_overview

    _app = QGuiApplication.instance() or QGuiApplication(["DC6-Overview"])
    dc6 = load_dc6(args.dc6)
    opts = OverviewOptions(
        columns=args.cols,
        number_every=args.every,
        spacing_x=args.spacing_x,
        spacing_y=args.spacing_y,
        scale=args.scale,
        upscale_method=args.method,
        text_line1=args.line1,
        text_line2=args.line2,
        jpg_quality=args.jpg_quality,
    )
    result = build_overview([f.pixels for f in dc6.frames], _palette(args.palette), opts, args.dc6.name)
    png, jpg = export_overview(result.image, args.out or args.dc6.parent, args.dc6.name, opts.jpg_quality)
    print(
        f"{png}\n{jpg}\n{result.image.width()} x {result.image.height()} px, "
        f"{result.frame_count} frames, oversize: {result.oversize or 'none'}"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    dc6 = load_dc6(args.dc6)
    print(
        f"{args.dc6.name}: {dc6.directions} direction(s) x {dc6.frames_per_dir} frame(s), "
        f"standard size {dc6.standard_size()}"
    )
    for issue in dc6.issues:
        print(" ", issue)
    if not dc6.issues:
        print("  no problems found")
    return 0


def cmd_export_frames(args: argparse.Namespace) -> int:
    dc6 = load_dc6(args.dc6)
    pal = _palette(args.palette)
    args.out.mkdir(parents=True, exist_ok=True)
    ext = EXPORT_FORMATS[args.format.upper()]
    for i, fr in enumerate(dc6.frames):
        export_frame(fr.pixels, pal, args.out / frame_filename(i, dc6.frame_count, ext))
    print(f"{dc6.frame_count} frame(s) written to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="main.py", description=f"{APP_NAME} {APP_VERSION} command line")
    sub = p.add_subparsers(dest="command", required=True)

    o = sub.add_parser("overview", help="export the overview image (PNG + JPG)")
    o.add_argument("dc6", type=Path)
    o.add_argument("--cols", type=int, default=60)
    o.add_argument("--every", type=int, default=10, help="number every N frames (0 = off)")
    o.add_argument("--spacing-x", type=int, default=0)
    o.add_argument("--spacing-y", type=int, default=3)
    o.add_argument("--scale", type=int, choices=SCALES, default=2)
    o.add_argument("--method", choices=list(METHODS), default="photoshop")
    o.add_argument("--line1", default="Project Diablo 2")
    o.add_argument("--line2", default="Season 14")
    o.add_argument("--jpg-quality", type=int, default=92)
    o.add_argument("--palette", default="act1")
    o.add_argument("--out", type=Path)
    o.set_defaults(func=cmd_overview)

    v = sub.add_parser("validate", help="check a DC6 file")
    v.add_argument("dc6", type=Path)
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("export-frames", help="export all frames as NNNN.<ext>")
    e.add_argument("dc6", type=Path)
    e.add_argument("out", type=Path)
    e.add_argument("--format", choices=[f.lower() for f in EXPORT_FORMATS], default="bmp")
    e.add_argument("--palette", default="act1")
    e.set_defaults(func=cmd_export_frames)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, DC6Error, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
