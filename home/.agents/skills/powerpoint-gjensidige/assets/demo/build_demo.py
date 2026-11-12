#!/usr/bin/env python3
"""Demo deck: the patterns this skill covers, built on the Gjensidige template.

    python build_demo.py <source.pptx> [out.pptx]

The source is any Gjensidige presentation. Its content is discarded and only the
masters are used.

Slide text is Norwegian on purpose. Gjensidige decks are written in Norwegian, and
sample text with æ, ø and å in it proves the template fonts render them.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from gjensidige_deck import *  # noqa: E402,F403

SRC = sys.argv[1] if len(sys.argv) > 1 else "source.pptx"
OUT = sys.argv[2] if len(sys.argv) > 2 else "demo.pptx"

L_COVER, L_TITLE_CONTENT, L_TITLE_SUB, L_TWO, L_THREE = 0, 14, 15, 18, 21

prs, master = open_template(SRC)
drop_all_slides(prs)

# ------------------------------------------------------------ 1. cover page

s = add(prs, master, L_COVER)
set_text(ph(s, 0), "Demo av Gjensidige-malen")
set_text(ph(s, 1), "Fem mønstre du kan be en agent om å bygge for deg")
drop(s, 11)
s.notes_slide.notes_text_frame.text = (
    "Forsiden kommer fra layout 0, Cover Page A. Gul flate og full logo med "
    "ordmerke arves fra masteren."
)

# ------------------------------------------------------- 2. three columns

s = add(prs, master, L_THREE)
set_text(ph(s, 13), "MØNSTER 1")
set_text(ph(s, 0), "Tre kolonner med ingress, seksjoner og punkter")
for sub_idx, obj_idx, name in [(15, 1, "Første kolonne"),
                               (17, 16, "Andre kolonne"),
                               (19, 18, "Tredje kolonne")]:
    set_text(ph(s, sub_idx), name, bold=True)
    fill_body(ph(s, obj_idx), [
        ("lead", "En ingress uten kulepunkt, som forklarer hva kolonnen handler om."),
        ("label", "Fordeler"),
        ("item", "Et punkt som arver malens egen kulepunktstil"),
        ("item", "Nok et punkt"),
        ("label", "Ulemper"),
        ("item", "Et motargument"),
        ("item", "Nok et motargument"),
    ], base_size=10)
set_text(ph(s, 14), "Fotnoten nederst til venstre er plassholder 14 på alle innholdslayouts.")
s.notes_slide.notes_text_frame.text = (
    "Layout 21, Three Content A. Hver kolonne er et par: overskrift og innhold."
)

# --------------------------------------------------------- 3. two columns

s = add(prs, master, L_TWO)
set_text(ph(s, 13), "MØNSTER 2")
set_text(ph(s, 0), "To brede kolonner")
fill_body(ph(s, 1), [
    ("label", "Venstre side"),
    ("lead", "Brukes når to alternativer skal stilles opp mot hverandre i full bredde."),
    ("item", "Punktene får plass til lengre setninger enn i tre kolonner"),
    ("item", "Bra til fordeler mot ulemper"),
], base_size=11)
fill_body(ph(s, 15), [
    ("label", "Høyre side"),
    ("lead", "Layout 19, Comparison, gir det samme med egne overskrifter innebygd."),
    ("item", "Velg 18 når du vil style overskriftene selv"),
    ("item", "Velg 19 når du vil at malen skal gjøre det"),
], base_size=11)
s.notes_slide.notes_text_frame.text = "Layout 18, Two Content."

# ------------------------------------------- 4. recommendation with cards

s = add(prs, master, L_TITLE_SUB)
set_text(ph(s, 13), "MØNSTER 3")
set_text(ph(s, 0), "Anbefaling med kort")
set_text(ph(s, 15), "Ingressen i plassholder 15 settes uthevet, og egner seg til "
                    "hovedbudskapet på en beslutningsside.", bold=True)
drop(s, 1)

for i, (title, desc) in enumerate([
    ("Første grunn", "Kortene er runde rektangler i den varme lyse tonen fra temaet."),
    ("Andre grunn", "Nummeret står i overskriften, ikke i en egen brikke."),
    ("Tredje grunn", "Teksten ligger øverst til venstre, ikke midtstilt."),
]):
    b = box(s, 0.49 + i * 4.06, 3.05, 3.75, 1.6, WARM)
    box_text(b, [(f"{i + 1}. {title}", 13, True, DARK), (desc, 10.5, False, DARK)])

note = box(s, 0.49, 5.1, 11.8, 1.0, DARK)
box_text(note, [
    ("Mørk boks til hovedpoenget", 12, True, YELLOW),
    ("Gul tekst på mørk blå er den sterkeste kombinasjonen i profilen, og den "
     "tåler å bli vist på skjerm i et møterom.", 10.5, False, WHITE),
])
set_text(ph(s, 14), "Kort og bokser tegnes med box() og box_text() fra gjensidige_deck.")
s.notes_slide.notes_text_frame.text = "Layout 15, med egne former oppå."

# ------------------------------------------------------------- 5. table

s = add(prs, master, L_TITLE_CONTENT)
set_text(ph(s, 13), "MØNSTER 4")
set_text(ph(s, 0), "Tabell med uthevet kolonne")
drop(s, 1)

rows = [
    ("Første rad", "Venstre kolonne", "Uthevet kolonne"),
    ("Andre rad", "Nøytral bakgrunn", "Svak gul bakgrunn"),
    ("Tredje rad", "Brukes til det som er gratis", "Brukes til det som koster"),
]
tbl = s.shapes.add_table(len(rows) + 1, 3, Inches(0.49), Inches(2.15),
                         Inches(11.8), Inches(2.3)).table
tbl.columns[0].width = Inches(2.2)
tbl.columns[1].width = Inches(4.8)
tbl.columns[2].width = Inches(4.8)
tbl.rows[0].height = Inches(0.42)
for r in range(1, len(rows) + 1):
    tbl.rows[r].height = Inches(0.58)

for c, text in enumerate(["Område", "Kolonne A", "Kolonne B"]):
    cell = tbl.cell(0, c)
    cell.fill.solid()
    cell.fill.fore_color.rgb = DARK if c < 2 else YELLOW
    run = cell.text_frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = WHITE if c < 2 else DARK

for r, cols in enumerate(rows, start=1):
    for ci, text in enumerate(cols):
        cell = tbl.cell(r, ci)
        cell.fill.solid()
        cell.fill.fore_color.rgb = WHITE if ci < 2 else RGBColor(0xFC, 0xFF, 0xEC)
        run = cell.text_frame.paragraphs[0].add_run()
        run.text = text
        run.font.size = Pt(10.5)
        run.font.bold = ci == 0
        run.font.color.rgb = DARK

set_text(ph(s, 14), "Sett radhøyder eksplisitt, ellers auto-vokser de langt høyere enn innholdet.")
s.notes_slide.notes_text_frame.text = "Layout 14 med tabell i stedet for tekstblokk."

# ---------------------------------------------------- 6. phase sequence

s = add(prs, master, L_TITLE_CONTENT)
set_text(ph(s, 13), "MØNSTER 5")
set_text(ph(s, 0), "Faser eller stegrekke")
drop(s, 1)

phases = [
    ("Fase 0", "Avklar", "Det som blokkerer alt annet.", PURPLE),
    ("Fase 1", "Bygg fundament", "Det som må på plass først.", DARK),
    ("Fase 2", "Lever verdi", "Det brukeren merker.", DARK),
    ("Fase 3", "Utvid", "Det som kommer etterpå.", DARK),
    ("Fase 4", "Skaler", "Det som krever partnere.", DARK),
]
for i, (fase, title, desc, color) in enumerate(phases):
    b = box(s, 0.49 + i * 2.42, 2.30, 2.22, 2.55, WARM)
    box_text(b, [(fase, 11, True, color), (title, 12.5, True, DARK), (desc, 10, False, DARK)])

banner = box(s, 0.49, 5.25, 11.8, 0.72, DARK)
box_text(banner, [("Bruk den mørke boksen til konklusjonen som skal huskes.", 12.5, True, YELLOW)])
set_text(ph(s, 14), "Kun første fase får aksentfarge, så blikket lander der det skal.")
s.notes_slide.notes_text_frame.text = (
    "Layout 14 med fem kort. Bruk aksentfarge sparsomt: én uthevet boks slår fem."
)

prs.save(OUT)
print("OK:", OUT, "|", len(prs.slides._sldIdLst), "slides")
