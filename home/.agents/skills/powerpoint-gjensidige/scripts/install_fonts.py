#!/usr/bin/env python3
"""Install the Gjensidige fonts so PowerPoint's editing view renders truthfully.

On a machine without the fonts, PowerPoint substitutes them in the editing
view and can garble runs into overlapping glyphs (a kicker reading "HW IT
WRK"), even though the deck and its PDF export are fine. The render QA
therefore passes while the deck looks broken to anyone reviewing it live in
PowerPoint. Installing the real fonts fixes it; restart PowerPoint afterwards.

The font files ship in this repo's ``html-slides`` skill as woff2, which no
desktop installs directly, so this script converts them with fontTools:

    uv run --with fonttools --with brotli python scripts/install_fonts.py

An explicit source directory (searched recursively for Gjensidige *.woff2,
*.ttf and *.otf) can be passed as the only argument. Gjensidige-managed
machines normally have the fonts already; check before installing copies.
"""

import platform
import re
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


def default_sources():
    here = Path(__file__).resolve()
    yield here.parents[2] / "html-slides" / "assets" / "fonts"  # skills repo sibling
    yield Path.home() / ".agents" / "skills" / "html-slides" / "assets" / "fonts"


def dest_dir() -> tuple[Path, str | None]:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Fonts", None
    if system == "Linux":
        return Path.home() / ".local" / "share" / "fonts", "run `fc-cache -f` afterwards"
    return (
        Path.cwd() / "GjensidigeFonts",
        "Windows: open the folder, select all fonts, right-click > Install",
    )


def main() -> int:
    if len(sys.argv) > 1:
        sources = [Path(sys.argv[1])]
    else:
        sources = [s for s in default_sources() if s.is_dir()]
    if not sources:
        sys.exit(
            "No font source found. Pass a directory holding the Gjensidige "
            "woff2/ttf/otf files (they ship in the skills repo under "
            "skills/html-slides/assets/fonts)."
        )

    out, note = dest_dir()
    out.mkdir(parents=True, exist_ok=True)
    installed = []
    for src in sources:
        for f in sorted(src.rglob("*")):
            if f.suffix.lower() not in (".woff2", ".woff", ".ttf", ".otf"):
                continue
            if "gjensidige" not in f.name.lower():
                continue
            stem = re.sub(r"-\d+x\d+$", "", f.stem)  # strip version suffixes like -22x293
            dest = out / (stem + ".ttf")
            if f.suffix.lower() in (".ttf", ".otf"):
                dest = out / f.name
                dest.write_bytes(f.read_bytes())
            else:
                font = TTFont(str(f))
                font.flavor = None
                font.save(str(dest))
            installed.append(dest.name)

    if not installed:
        sys.exit(f"No Gjensidige font files found under: {', '.join(map(str, sources))}")
    print(f"Installed {len(installed)} fonts to {out}:")
    print("\n".join(f"  {n}" for n in installed))
    if note:
        print(note)
    print("Restart PowerPoint so it picks the fonts up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
