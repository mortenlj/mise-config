#!/usr/bin/env python3
"""Print the layout catalogue and theme tokens of a Gjensidige deck or template.

Run this first, every time. Layout indices are not stable across template
versions, so never hardcode an index you have not just read from the file.

Usage:
    python audit_template.py <deck.pptx|template.potx> [--master N] [--layout N ...]
"""

import argparse
import re
import sys
import zipfile

try:
    from pptx import Presentation
except ImportError:
    sys.exit("Missing dependency. Run: pip install python-pptx")

EMU = 914400


def theme_tokens(path):
    """Colour scheme and font scheme, read straight from the theme part."""
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if re.match(r"ppt/theme/theme1\.xml$", n)), None)
        if not name:
            return
        xml = z.read(name).decode("utf-8", "replace")

    print("=== THEME ===")
    m = re.search(r"<a:clrScheme[^>]*name=\"([^\"]*)\"", xml)
    if m:
        print(f"  name: {m.group(1)}")
    scheme = re.search(r"<a:clrScheme.*?</a:clrScheme>", xml, re.S)
    if scheme:
        pattern = r"<a:(\w+)>\s*<a:(?:srgbClr val=\"([0-9A-Fa-f]{6})\"|sysClr[^>]*lastClr=\"([0-9A-Fa-f]{6})\")"
        for m in re.finditer(pattern, scheme.group(0)):
            print(f"  {m.group(1):<9} #{(m.group(2) or m.group(3)).upper()}")
    fonts = re.search(r"<a:fontScheme.*?</a:fontScheme>", xml, re.S)
    if fonts:
        for m in re.finditer(r"<a:(majorFont|minorFont)>\s*<a:latin typeface=\"([^\"]*)\"", fonts.group(0)):
            label = "heading" if m.group(1) == "majorFont" else "body"
            print(f"  {label:<9} {m.group(2)}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--master", type=int, default=0, help="master to list layouts for (default 0)")
    ap.add_argument("--layout", type=int, nargs="*", default=[],
                    help="layout indices to expand with placeholder geometry")
    args = ap.parse_args()

    theme_tokens(args.deck)

    prs = Presentation(args.deck)
    print(f"=== SLIDE SIZE: {prs.slide_width / EMU:.2f} x {prs.slide_height / EMU:.2f} in ===\n")
    print(f"=== MASTERS: {len(prs.slide_masters)} ===")
    for i, m in enumerate(prs.slide_masters):
        print(f"  [{i}] {m.name or '(unnamed)'}, {len(m.slide_layouts)} layouts")
    print()

    master = prs.slide_masters[args.master]
    print(f"=== LAYOUTS ON MASTER {args.master} ===")
    for i, layout in enumerate(master.slide_layouts):
        print(f"  [{i:>3}] {layout.name}")
    print()

    for li in args.layout:
        layout = master.slide_layouts[li]
        print(f"=== [{li}] {layout.name} placeholders ===")
        for ph in layout.placeholders:
            f = ph.placeholder_format
            print(f"  idx={f.idx:<3} {str(f.type).split()[0]:<13}"
                  f" x={ph.left / EMU:.2f} y={ph.top / EMU:.2f}"
                  f" w={ph.width / EMU:.2f} h={ph.height / EMU:.2f}  {ph.name!r}")
        print()


if __name__ == "__main__":
    main()
