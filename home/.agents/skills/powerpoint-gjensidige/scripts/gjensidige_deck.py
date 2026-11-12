#!/usr/bin/env python3
"""Helpers for building a deck on the Gjensidige PowerPoint Template.

Import this from a build script. Every function here exists because the naive
python-pptx call produces a visible defect; see the docstrings.

    from gjensidige_deck import *

    prs, master = open_template("kildedeck.pptx")
    drop_all_slides(prs)
    s = add(prs, master, 14)          # index from audit_template.py, never guessed
    set_text(ph(s, 0), "Tittel")
    fill_body(ph(s, 1), [("lead", "Ingress"), ("item", "Punkt")])
    prs.save("ut.pptx")
"""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# Theme colours of "Gjensidige 2022". Verify against audit_template.py output:
# a newer template revision may move these.
DARK = RGBColor(0x09, 0x0C, 0x33)     # dk2 / accent1, the primary dark blue
YELLOW = RGBColor(0xF4, 0xFF, 0xAF)   # accent2
PURPLE = RGBColor(0x7C, 0x55, 0xFF)   # accent3
GREEN = RGBColor(0x50, 0xD7, 0xA5)    # accent4
LBLUE = RGBColor(0xA4, 0xC3, 0xFF)    # accent5
CORAL = RGBColor(0xFF, 0x80, 0x83)    # accent6
WARM = RGBColor(0xF0, 0xED, 0xEB)     # lt2, the card fill
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# Contrast note: LBLUE, CORAL and YELLOW are decorative. As text on WARM or
# WHITE they fail legibility. Use them as fills, and keep text DARK or WHITE.

__all__ = [
    "Inches", "Pt", "RGBColor", "MSO_SHAPE", "PP_ALIGN", "MSO_ANCHOR",
    "DARK", "YELLOW", "PURPLE", "GREEN", "LBLUE", "CORAL", "WARM", "WHITE",
    "open_template", "drop_all_slides", "add", "ph", "drop",
    "set_text", "fill_body", "box", "box_text", "no_bullet",
]


def open_template(path):
    """Open a Gjensidige deck as the template source. Returns (prs, master0)."""
    prs = Presentation(path)
    return prs, prs.slide_masters[0]


def drop_all_slides(prs):
    """Strip content slides, keeping masters, layouts, theme, logo and media.

    This is what makes an existing corporate deck usable as a template: the
    branding lives in the masters, not in the slides.
    """
    sldIdLst = prs.slides._sldIdLst
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sldId in list(sldIdLst):
        prs.part.drop_rel(sldId.get(rel_ns))
        sldIdLst.remove(sldId)


def add(prs, master, layout_idx):
    return prs.slides.add_slide(master.slide_layouts[layout_idx])


def ph(slide, idx):
    """Placeholder by idx. Use the idx from audit_template.py, not position."""
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == idx:
            return shape
    raise KeyError(f"placeholder idx={idx} not on this layout")


def drop(slide, idx):
    """Remove an unused placeholder so its prompt text does not print."""
    try:
        shape = ph(slide, idx)
    except KeyError:
        return
    shape._element.getparent().remove(shape._element)


def no_bullet(paragraph):
    """Remove the bullet glyph and the hanging indent it leaves behind.

    Dropping only the glyph leaves marL/indent from the layout, so the second
    line of an unbulleted paragraph stays indented under nothing.
    """
    pPr = paragraph._p.get_or_add_pPr()
    for tag in ("a:buChar", "a:buAutoNum", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    pPr.set("marL", "0")
    pPr.set("indent", "0")
    pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def set_text(shape, text, size=None, bold=None, color=None):
    """Write one run into a placeholder, keeping its inherited formatting.

    Assigning ``text_frame.text`` collapses the paragraph to a single unstyled
    run and loses the template's font, so write a run instead.
    """
    p = shape.text_frame.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    run = p.add_run()
    run.text = text
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    return p


def fill_body(shape, blocks, base_size=11):
    """Fill a content placeholder from ``(kind, text)`` pairs.

    kind: ``lead`` intro prose, ``label`` a bold section heading, ``item`` a
    bullet. Lead and label lose their bullet and indent; items keep the
    template's own bullet styling at level 1.
    """
    tf = shape.text_frame
    tf.word_wrap = True
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    first = tf.paragraphs[0]
    for r in list(first.runs):
        r._r.getparent().remove(r._r)

    para = first
    for i, (kind, text) in enumerate(blocks):
        if i > 0:
            para = tf.add_paragraph()
        run = para.add_run()
        run.text = text
        if kind == "lead":
            para.level = 0
            run.font.size = Pt(base_size)
            no_bullet(para)
            para.space_after = Pt(8)
        elif kind == "label":
            para.level = 0
            run.font.size = Pt(base_size)
            run.font.bold = True
            no_bullet(para)
            para.space_before = Pt(6)
            para.space_after = Pt(2)
        else:
            para.level = 1
            run.font.size = Pt(base_size - 0.5)
            para.space_after = Pt(3)
    return tf


def set_language(container, language_id):
    """Tag every run in ``container`` (a slide or a notes slide) with a language.

    The template's editing language is Norwegian Bokmål, so an English deck
    shows proofing squiggles under half its copy on any reviewer's machine.
    Call after the slide is filled (runs added later are not covered), e.g.::

        from pptx.enum.lang import MSO_LANGUAGE_ID
        set_language(s, MSO_LANGUAGE_ID.ENGLISH_UK)
        set_language(s.notes_slide, MSO_LANGUAGE_ID.ENGLISH_UK)
    """

    def _tag(text_frame):
        for para in text_frame.paragraphs:
            for run in para.runs:
                run.font.language_id = language_id

    for shape in container.shapes:
        if shape.has_text_frame:
            _tag(shape.text_frame)
        if getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    _tag(cell.text_frame)


def box(slide, x, y, w, h, fill, radius=0.06):
    """Rounded card in inches. Shadowless and borderless, per the brand."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    shape.shadow.inherit = False
    try:
        shape.adjustments[0] = radius
    except Exception:
        pass
    shape.text_frame.word_wrap = True
    return shape


def box_text(shape, lines):
    """Fill a card from ``(text, size, bold, color)`` tuples.

    Shapes default to centred and vertically middled text, which reads as an
    accident in a card. This anchors top-left.
    """
    tf = shape.text_frame
    tf.margin_left = Inches(0.18)
    tf.margin_right = Inches(0.18)
    tf.margin_top = Inches(0.14)
    tf.margin_bottom = Inches(0.12)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    para = tf.paragraphs[0]
    for r in list(para.runs):
        r._r.getparent().remove(r._r)
    for i, (text, size, bold, color) in enumerate(lines):
        if i > 0:
            para = tf.add_paragraph()
        no_bullet(para)
        para.alignment = PP_ALIGN.LEFT
        run = para.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        para.space_after = Pt(4)
    return tf
