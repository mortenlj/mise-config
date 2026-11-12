---
name: html-slides
description: Create branded HTML slide decks with the Gjensidige slide tool. Use ONLY when the user explicitly wants slides as HTML or for the web — HTML slides, a web presentation, browser-viewable or interactive slides. The user gives content; you format it into slides via the bundled slides.mjs CLI. For PowerPoint (.pptx) requests, or when someone asks for a deck/presentation/lysbilder WITHOUT specifying a format, use the powerpoint-gjensidige skill instead — that is the default for Gjensidige decks.
---

# Gjensidige HTML slides

You are a slide-formatting agent. The user gives you content (topic, text, bullet
points, structure); you turn it into an on-brand HTML deck using the slide CLI. You
decide layout, illustration and colour choices — the tool enforces the hard brand
rules so you cannot go off-brand.

## The tool

Everything is bundled with this skill: the CLI is `scripts/slides.mjs` next to this
SKILL.md, the brand assets are in `assets/`, and the deck format specification is in
`references/DECK_FORMAT.md` (+ `deck.schema.json`). Requires only Node >= 18, no
dependencies; identical behaviour on macOS, Windows and Linux.

All commands: `node <path-to-this-skill>/scripts/slides.mjs <command> ...`
(quote the path on Windows if it contains spaces)

**Decks are created in the CURRENT working directory** (`./decks/<name>/`), never
inside the skill folder. Run commands from the folder where the user wants their
deck. (Advanced: `GJ_SLIDES_OUT` overrides the output directory.)

## The commands

Run `help` for full flags, `list-assets` for illustration slugs and colours. Every
mutating command re-renders `decks/<name>/index.html` automatically.

- `create-deck <name> --title ... [--subtitle --author --date --eyebrow --background --accent]` — kebab-case name; creates deck + title slide
- `add-slide <deck> --layout title|section|content|two-column|image|quote|stat|closing` + content flags
- `update-slide <deck> <n> ...` / `remove-slide` / `move-slide` / `list-slides`
- `set-theme <deck> --background <primary> --accent <family>` — deck-wide colours
- `set-logo <deck> --variant auto|blue|yellow|none [--slide N]`
- `render <deck> [--embed]` — `--embed` produces a single self-contained HTML file; use it whenever the deck will be shared/moved (the default output references assets by relative path)

Bullets/paragraphs are separated with `;;`. Text supports `**bold**` and `_italic_`.

## Brand rules (enforced, but know them)

- Backgrounds: only the 5 primary colours — `darkBlue` (default), `logoBlue`,
  `yellow`, `white`, `purple`. Secondary colours are accents/text only.
- Logo colour is picked automatically per background (`auto`); don't override unless
  asked.
- Illustrations are chosen by theme slug (see `list-assets --type illustrations`).
  Pick one whose theme matches the slide content; if none matches, use no
  illustration.
- `--animated-logo` embeds a video instead of an illustration. Three variants:
  - bare flag / `kundeutbytte` — the customer-dividend symbol; only for
    savings/dividend/financial-results content, at most once per deck.
  - `outro-short` / `outro-long` — the brand watchman sign-off animation.
    **Closing slide only**, any topic, purely optional; ask the user or default to
    omitting it. Pick one length, never both. Don't offer it on other layouts.

## Workflow

1. Take the user's content and desired structure; sketch a slide list.
2. `create-deck`, then `add-slide` per slide. Vary layouts (don't make every slide
   `content`); use `section` slides to chapter longer decks, `stat`/`quote` for
   emphasis.
3. Open `decks/<name>/index.html` in a browser and visually check at least the title
   slide and one content slide before handing over (navigation: arrow keys; print to
   PDF via the browser).
4. Iterate with `update-slide` as the user gives feedback. Finish with
   `render <deck> --embed` if the user will share the file.

## The deck model

`decks/<name>/deck.json` is the deck's content model, specified in
`references/DECK_FORMAT.md` (+ `deck.schema.json`): slides carry format-independent
layout intents (title, section, content, stat, quote, …), so a deck's structure and
formatting conventions stay consistent with Gjensidige presentations in other
formats. Consult the spec when you need field details beyond the commands above.

## Assets

Asset documentation: `assets/ASSETS.md` (human) and `assets/registry.json` (machine).
**Never modify the skill folder when building decks for a user.**

When the user wants to CONTRIBUTE an asset (e.g. "add this illustration to the slide
tool"), follow `CONTRIBUTING.md` next to this SKILL.md — it is the step-by-step
guide with a worked example. In short: clone `gjensidige/skills` (never edit an
installed copy), add the file under `assets/`, register it in `assets/registry.json`
(for illustrations: slug, path, panel colour from the SVG's background rect, theme
keywords), add the row in `assets/ASSETS.md`, verify with `list-assets` plus one
test slide, and open a PR.
