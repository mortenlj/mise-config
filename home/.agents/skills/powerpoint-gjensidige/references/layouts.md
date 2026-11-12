# Layout catalogue: Gjensidige 2022

Master 0 carries around 90 layouts. Below are the ones you actually need, with
placeholder indices. **Verify against `audit_template.py` before use.** The indices
move between template revisions, so this table is a shortcut rather than a
guarantee.

Slide size is 13.33 x 7.5 inches (16:9).

## Placeholders that recur

These keep the same idx across the content layouts, and you use them constantly:

| idx | Role | Note |
|---|---|---|
| `0` | Title | Wraps to two lines when long and pushes down into the content. Keep it short. |
| `13` | Kicker above the title | Small caps label, e.g. `OUR RECOMMENDATION`. |
| `14` | Footnote, bottom left | Small text. Good for caveats and sourcing. |
| `11`, `12` | Footer and slide number | Inherited from the master. Leave alone. |
| `10` | Date | Usually hidden in the master. |

## Layouts worth knowing

| idx | Name | Content placeholders | Use for |
|---|---|---|---|
| `0` | Cover Page A | `0` title, `1` subtitle, `11` date | Cover. Yellow brand field and the full logo with wordmark. The title is set very large, so keep it under roughly 40 characters. |
| `1` | Cover Page B | same as above | Alternative cover. |
| `6` | Agenda | `1` | Agenda page. |
| `8`–`13` | Chapter A–F | `0`, `1` | Section dividers. Different background colours. |
| `14` | Title and Content | `1` content | The workhorse. One text block or a table. |
| `15` | Title, subtitle and Content | `15` lead, `1` content | When the message needs an emphasised lead above the content. |
| `18` | Two Content | `1`, `15` | Two equal columns. |
| `19` | Comparison | `1`, `15` with their own headings | Comparisons, e.g. pros against cons. |
| `21` | Three Content A | `15`+`1`, `17`+`16`, `19`+`18` | Three columns, each with its own subheading and content. The pairing is always (heading, content). |
| `27` | Four Content | `15`+`1`, `17`+`16`, `19`+`18`, `21`+`20` | Four blocks in a grid. |
| `55` | Title and four content | `1`, `16`, `18`, `20` | Four columns without subheadings. |
| `61`–`78` | Quote (many variants) | `0` quote, `14` byline | Full-page quote. Colour variants are named in the layout. |
| `80`, `81` | End slide A/B | `0`, `1` | Closing. |
| `84`, `85` | Blank / Blank dark | none | Free composition when no layout fits. |

Layouts past `88` sit behind a marker reading `>Do not use layouts after this >`.
Leave them alone.

## Theme colours

Read from `ppt/theme/theme1.xml`. Constants with the same names live in
`scripts/gjensidige_deck.py`.

| Token | Hex | Name in the template | Use |
|---|---|---|---|
| `dk2` / `accent1` | `#090C33` | Dark Blue 700 | Primary dark. Text and dark surfaces. |
| `accent2` | `#F4FFAF` | light yellow | Cover field, highlights. |
| `accent3` | `#7C55FF` | purple | Accent, link colour. |
| `accent4` | `#50D7A5` | green | Accent. |
| `accent5` | `#A4C3FF` | light blue | Accent. |
| `accent6` | `#FF8083` | coral | Accent. |
| `lt2` | `#F0EDEB` | warm light | Card surface. |
| `lt1` | `#FFFFFF` | white | Background. |

**Contrast:** `accent2`, `accent5` and `accent6` are decorative. As text on `lt1`
or `lt2` they are too weak to read. Use them as fills and keep text on `#090C33`
or white.

## Fonts

| Role | Font |
|---|---|
| Headings (`majorFont`) | Gjensidige Display |
| Body (`minorFont`) | Gjensidige Type |

Both inherit from the theme. **Do not set font names in code.** The fonts are
installed on Gjensidige machines, and setting your own strips the branding for
everyone who opens the file.

This matters for visual QA. Rendering on a machine without the fonts gets text
width roughly right but not exactly, so leave some slack in tight boxes.
