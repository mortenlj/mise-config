#!/usr/bin/env python3
"""Render every slide to a PNG for visual QA. Works on macOS, Windows and Linux.

Converter priority, per platform:

  macOS    Microsoft PowerPoint via AppleScript, else LibreOffice
  Windows  Microsoft PowerPoint via PowerShell COM, else LibreOffice
  Linux    LibreOffice

PowerPoint is preferred where present because it is the renderer the audience
opens the file in, so font substitution and text fit are truthful. LibreOffice
substitutes the Gjensidige fonts, which makes its text-fit check approximate:
leave slack in tight boxes when that is all you have.

PDF to image goes through poppler (`pdftoppm`), else mutool, else PyMuPDF. That
order is deliberate: PyMuPDF is the only one of the three that needs no install,
but it silently drops and mis-places text in the PDFs PowerPoint for Mac
produces, because the Gjensidige fonts are embedded there as TrueType subsets.
A QA image that invents defects is worse than no QA image, so the fallback
warns when it is used. `brew install poppler` is the fix.

Rendering is meant to be safe to run while someone is working. The only deck
this closes is the one being rendered, and PowerPoint is left running unless it
was this script that started it.

    python render_qa.py deck.pptx [outdir]
"""

import argparse
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DPI = 110


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# PowerPoint re-exports its in-memory copy, so a deck it already has open
# silently yields a stale PDF and the QA pass reviews the previous build. The
# cache is per presentation, not per application, so only the deck being
# rendered has to go: whatever else the user is working in stays open, and
# PowerPoint itself is left running if it was running before.


# A modal dialog (a repair prompt, a stale lock file, "save changes?") stops
# PowerPoint answering Apple events at all, and osascript then waits forever.
# Every call is bounded so that state surfaces as an error you can act on.
OSA_TIMEOUT_SECONDS = 900


def _osa(script: str):
    try:
        return _run(["osascript", "-e", script], timeout=OSA_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        sys.exit(
            "PowerPoint stopped responding to AppleScript.\n"
            "It is almost certainly showing a dialog that needs a human: a file-repair\n"
            "prompt, a 'file in use' warning, or an unsaved-changes sheet. Switch to\n"
            "PowerPoint, dismiss it, and run this again."
        )


def _osa_str(value) -> str:
    """Quote a value for interpolation into an AppleScript string literal."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _macos_running() -> bool:
    # Asked through System Events so that a check never launches PowerPoint.
    r = _osa('tell application "System Events" to return '
             '(name of processes) contains "Microsoft PowerPoint"')
    return r.stdout.strip() == "true"


def _macos_close_stale(deck: Path) -> None:
    """Close an already-open copy of `deck`, and nothing else.

    PowerPoint reports paths as opened, so a deck under a symlinked directory
    comes back as /tmp/... where `deck` resolved to /private/tmp/... . Matching
    is therefore done in Python, on resolved paths, and the close is keyed on
    the exact string PowerPoint itself reported.
    """
    listing = _osa('''
tell application "Microsoft PowerPoint"
  set fullNames to {}
  repeat with p in (get every presentation)
    try
      set end of fullNames to (full name of p)
    end try
  end repeat
  set AppleScript's text item delimiters to linefeed
  return fullNames as text
end tell
''')
    for line in listing.stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            if Path(candidate).resolve() != deck:
                continue
        except OSError:
            continue
        _osa(f'''
tell application "Microsoft PowerPoint"
  repeat with p in (get every presentation)
    try
      if (full name of p) is "{_osa_str(candidate)}" then
        close p saving no
        exit repeat
      end if
    end try
  end repeat
end tell
''')


def _clear_orphan_lock(deck: Path) -> None:
    """Delete the ``~$deck.pptx`` lock file left behind by a crashed PowerPoint.

    PowerPoint writes that file while a deck is open and removes it on close. A
    crash or a killed process leaves it, and the next open then stops on a
    "file in use" dialog that blocks Apple events. Only removed when no
    PowerPoint is running, since a running one may legitimately own it.
    """
    lock = deck.with_name(f"~${deck.name}")
    if lock.exists() and not _macos_running():
        try:
            lock.unlink()
        except OSError:
            pass


def _powerpoint_macos(deck: Path, pdf: Path) -> bool:
    if not Path("/Applications/Microsoft PowerPoint.app").exists():
        return False
    was_running = _macos_running()
    if was_running:
        _macos_close_stale(deck)
    else:
        _clear_orphan_lock(deck)

    # Two things this script must not do: give up before PowerPoint has finished
    # opening the deck, and export whatever else happens to be in front.
    #
    # `open` returns nothing, so the deck has to be picked up as the active
    # presentation, and the only way to know the open finished is to poll for it
    # by name. A fixed delay is wrong in both directions: too short on a cold
    # launch (the export then runs against a half-laid-out deck and silently
    # drops shapes) and wasted time on a warm one. The name check doubles as the
    # safety check, since exporting or closing someone else's deck is the worst
    # outcome available here.
    #
    # `with timeout` matters separately: Apple events default to two minutes,
    # and a cold launch plus a PDF export of a large deck goes past that, which
    # surfaces as -1712 while PowerPoint is still working.
    name = _osa_str(deck.name)
    script = f'''
with timeout of {OSA_TIMEOUT_SECONDS} seconds
  tell application "Microsoft PowerPoint"
    launch
    open POSIX file "{_osa_str(deck)}"
    set waited to 0
    repeat until waited > 300
      try
        if (name of active presentation) is "{name}" then exit repeat
      end try
      -- A cold launch can swallow the open event while the app is still
      -- initialising, and then the poll waits forever for a deck that was
      -- never opened. Re-issuing the open is safe: on an already-open deck
      -- it only activates the window.
      if waited is not 0 and (waited mod 20) is 0 then open POSIX file "{_osa_str(deck)}"
      delay 1
      set waited to waited + 1
    end repeat
    set theDeck to missing value
    try
      if (name of active presentation) is "{name}" then set theDeck to active presentation
    end try
    if theDeck is missing value then error "PowerPoint never finished opening {name}"
    save theDeck in POSIX file "{_osa_str(pdf)}" as save as PDF
    close theDeck saving no
  end tell
end timeout
'''
    try:
        r = _osa(script)
        if r.returncode != 0 and not pdf.exists():
            sys.stderr.write(r.stderr)
    finally:
        if not was_running:
            # We launched it. Leave the machine as we found it, but not at the
            # cost of a deck the user opened while the export was running.
            _osa('tell application "Microsoft PowerPoint" to '
                 'if (count of presentations) is 0 then quit')
    return pdf.exists()


def _powerpoint_windows(deck: Path, pdf: Path) -> bool:
    if not shutil.which("powershell") and not shutil.which("pwsh"):
        return False
    shell = shutil.which("pwsh") or shutil.which("powershell")
    # ppSaveAsPDF = 32. Same cache reasoning as macOS: close a stale copy of
    # this deck only, and quit only if we were the ones who started PowerPoint.
    script = f'''
$ErrorActionPreference = "Stop"
$deck = "{deck}"
$wasRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$pp = New-Object -ComObject PowerPoint.Application
try {{
  for ($i = $pp.Presentations.Count; $i -ge 1; $i--) {{
    $open = $pp.Presentations.Item($i)
    if ($open.FullName -ieq $deck) {{
      $open.Saved = $true
      $open.Close()
    }}
  }}
  $pres = $pp.Presentations.Open($deck, $true, $false, $false)
  $pres.SaveAs("{pdf}", 32)
  $pres.Close()
}} finally {{
  if (-not $wasRunning -and $pp.Presentations.Count -eq 0) {{ $pp.Quit() }}
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}}
'''
    r = _run([shell, "-NoProfile", "-NonInteractive", "-Command", script])
    if not pdf.exists() and r.returncode != 0:
        sys.stderr.write(r.stderr)
        return False
    return pdf.exists()


def _libreoffice(deck: Path, pdf: Path) -> bool:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice and platform.system() == "Darwin":
        candidate = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        soffice = str(candidate) if candidate.exists() else None
    if not soffice and platform.system() == "Windows":
        for base in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                     r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
            if Path(base).exists():
                soffice = base
                break
    if not soffice:
        return False

    with tempfile.TemporaryDirectory() as tmp:
        r = _run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(deck)])
        produced = Path(tmp) / (deck.stem + ".pdf")
        if not produced.exists():
            sys.stderr.write(r.stderr or "LibreOffice produced no PDF.\n")
            return False
        shutil.move(str(produced), str(pdf))
    return pdf.exists()


def to_pdf(deck: Path, pdf: Path) -> str:
    system = platform.system()
    attempts = []
    if system == "Darwin":
        attempts = [("PowerPoint", _powerpoint_macos), ("LibreOffice", _libreoffice)]
    elif system == "Windows":
        attempts = [("PowerPoint", _powerpoint_windows), ("LibreOffice", _libreoffice)]
    else:
        attempts = [("LibreOffice", _libreoffice)]

    for name, fn in attempts:
        pdf.unlink(missing_ok=True)
        try:
            if fn(deck, pdf):
                return name
        except Exception as exc:  # a missing converter must not abort the run
            sys.stderr.write(f"{name} failed: {exc}\n")
    sys.exit(
        "No usable converter found.\n"
        "Install Microsoft PowerPoint, or LibreOffice (https://libreoffice.org)."
    )


def _collect_rendered(tmp: Path, outdir: Path) -> list[Path]:
    """Rename a rasterizer's numbered output to zero-padded slide-NN.png."""
    produced = sorted(
        tmp.glob("page*.png"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)),
    )
    width = len(str(len(produced)))
    written = []
    for i, src in enumerate(produced, start=1):
        target = outdir / f"slide-{i:0{width}d}.png"
        shutil.move(str(src), str(target))
        written.append(target)
    return written


def _rasterize_poppler(pdf: Path, outdir: Path) -> list[Path]:
    exe = shutil.which("pdftoppm")
    if not exe:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        _run([exe, "-png", "-r", str(DPI), str(pdf), str(Path(tmp) / "page")])
        return _collect_rendered(Path(tmp), outdir)


def _rasterize_mutool(pdf: Path, outdir: Path) -> list[Path]:
    exe = shutil.which("mutool")
    if not exe:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        _run([exe, "draw", "-o", str(Path(tmp) / "page%d.png"),
              "-r", str(DPI), "-F", "png", str(pdf)])
        return _collect_rendered(Path(tmp), outdir)


def _rasterize_pymupdf(pdf: Path, outdir: Path) -> list[Path]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    written = []
    with fitz.open(pdf) as doc:
        zoom = DPI / 72
        matrix = fitz.Matrix(zoom, zoom)
        width = len(str(doc.page_count))
        for i, page in enumerate(doc, start=1):
            target = outdir / f"slide-{i:0{width}d}.png"
            page.get_pixmap(matrix=matrix).save(target)
            written.append(target)
    return written


def to_images(pdf: Path, outdir: Path) -> tuple[list[Path], str]:
    """PDF to PNG, preferring a rasterizer that can be trusted with this PDF.

    PyMuPDF is the fallback rather than the first choice, and that ordering was
    bought the hard way. PowerPoint for Mac embeds the Gjensidige fonts as
    TrueType subsets, and rasterizing those through PyMuPDF silently drops whole
    text frames and mis-positions glyphs in others. The PDF is correct and so is
    the deck: only the QA image is wrong, which is the worst possible failure
    for a step whose entire job is to be believed. poppler and mutool both
    render the same PDFs faithfully.
    """
    for name, fn in (
        ("poppler", _rasterize_poppler),
        ("mutool", _rasterize_mutool),
        ("PyMuPDF", _rasterize_pymupdf),
    ):
        images = fn(pdf, outdir)
        if images:
            return images, name
    sys.exit(
        "No usable rasterizer found. Install one:\n"
        "  brew install poppler      (or mutool, via mupdf-tools)\n"
        "  pip install PyMuPDF       (fallback; see the note in to_images)"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("deck")
    ap.add_argument("outdir", nargs="?", default=None)
    args = ap.parse_args()

    deck = Path(args.deck).expanduser().resolve()
    if not deck.is_file():
        sys.exit(f"No such file: {deck}")

    outdir = Path(args.outdir).expanduser().resolve() if args.outdir else deck.parent / "qa"
    outdir.mkdir(parents=True, exist_ok=True)
    for stale in outdir.glob("slide-*.png"):
        stale.unlink()

    pdf = outdir / "qa.pdf"
    renderer = to_pdf(deck, pdf)
    images, rasterizer = to_images(pdf, outdir)
    pdf.unlink(missing_ok=True)

    print(f"Rendered {len(images)} slides with {renderer} and {rasterizer}:")
    for img in images:
        print(f"  {img}")
    if renderer == "LibreOffice":
        print("\nNote: LibreOffice substitutes the Gjensidige fonts, so text-fit "
              "checks here are approximate.", file=sys.stderr)
    if rasterizer == "PyMuPDF":
        print("\nNote: PyMuPDF is the fallback rasterizer, and it drops or "
              "mis-places text in PDFs that embed the Gjensidige fonts as "
              "subsets. Before you 'fix' a slide that looks empty or garbled "
              "here, confirm it against the deck itself. `brew install poppler` "
              "removes the doubt.", file=sys.stderr)


if __name__ == "__main__":
    main()
