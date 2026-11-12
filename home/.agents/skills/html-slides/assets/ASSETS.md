# Gjensidige Slide Assets

This file documents every asset available to the slide-creation agent: **what it is,
when to use it, and when not to**. It follows the same principles as skills/tools in an
agent harness — each asset entry is a "tool description" that lets the agent pick the
right asset without opening the file first.

**Two files, one contract:**

| File | Audience | Purpose |
|---|---|---|
| `ASSETS.md` (this file) | Humans + agent | Explains what each asset is for and the rules around it |
| `registry.json` | The slide tool (`tools/slides.mjs`) | Machine-readable manifest: paths, hex values, slugs, keywords |

**Adding a new asset (via pull request to `gjensidige/skills` — never edit an
installed copy). Full step-by-step guide with a worked example: [`../CONTRIBUTING.md`](../CONTRIBUTING.md). The short version:**
1. Drop the file into the right subfolder (`logos/`, `fonts/`, `illustrations/`) —
   colours are the exception, see below.
2. Add an entry to `registry.json` (path, slug, keywords; panel colour for illustrations).
3. Document it here: what it is, when to use it, when NOT to use it.

Nothing else needs to change — the slide tool reads `registry.json` at runtime.

---

## Colours — data only, no `colors/` folder

Every colour the tool knows about (primary backgrounds, secondary ramps, digital
accents) is baked directly into `registry.json` as hex/CMYK/Pantone values — there is
no source-file folder to drop anything into. A new colour, or a correction to an
existing one, is a `registry.json` edit plus a note here; nothing else.

### Rules (non-negotiable)

- **Slide backgrounds MUST be a primary colour**: Dark Blue `#090C33`, Logo Blue
  `#060948`, Yellow `#F4FFAF`, White `#FFFFFF`, or Purple `#6545BF`. Never use a
  secondary colour as a slide background.
- **Secondary colours are for text, accents, logos, charts and decorative elements** —
  highlights, dividers, data series, tags.
- On **dark backgrounds** (Dark Blue, Logo Blue, Purple): body text is White, default
  accent is Yellow `#F4FFAF`. Use the `digitalAccents` values from `registry.json` for
  further accents — they exactly match the illustration palette.
- On **light backgrounds** (White, Yellow): body text is Dark Blue `#090C33`, default
  accent is Purple `#6545BF`. Use the 500–700 steps of the secondary ramps (lighter
  steps fail contrast).

### Where the hex values come from

The web hex values in `registry.json` were derived like this, in order of preference
(recorded per colour in its `source` field):

1. **Asset-exact**: colours extracted from the official digital SVGs (logos and
   illustrations) — e.g. Dark Blue `#090C33` is the canvas colour every digital
   illustration is built on, Yellow `#F4FFAF` is the yellow logo fill.
2. **Sampled**: the secondary ramps were pixel-sampled from an official print swatch
   sheet (CMYK/Pantone recipes held by brand/comms, not stored in this repo — it's
   print-oriented and the tool only ever needs the derived web hex values).

If official digital colour tokens ever land in this repo, replace the sampled values
in `registry.json`, update their `source` field, and note it here.

---

## logos/

| File | What it is | Use when |
|---|---|---|
| `Gjensidige_Main Logo Alternative_Digital_Blue.svg` / `.png` | Main logo in Logo Blue `#060948` | Slide background is **light** (White, Yellow) |
| `Gjensidige_Main Logo Alternative_Digital_Yellow.svg` / `.png` | Main logo in Yellow `#F4FFAF` | Slide background is **dark** (Dark Blue, Logo Blue, Purple) |
| `Symbol_1080x1080_kundeutbytte.mp4` | Animated logo symbol (1:1), illustrates **customer dividend / financial savings** (kundeutbytte). Has a dark-blue background baked into the video (no alpha). Loops. | Title, section-break or closing slides where the content relates to savings, dividend or financial results. Embed as `<video autoplay muted loop playsinline>`; render as a rounded card or on a dark background so the baked-in background doesn't clash. |
| `logo-animation-short.mp4` (4s) / `logo-animation-long.mp4` (6s) | Brand outro animation (16:9) — the Gjensidige watchman symbol. Composited onto darkBlue (`#090C33`), no alpha; plays once and holds on the final frame (no loop). | **Closing slide only**, any deck, any topic — optional sign-off, not content-dependent like the kundeutbytte symbol. Pick one length, never both in the same deck. Embed as `<video autoplay muted playsinline>` (no `loop`); works best on a darkBlue closing slide. |

Rules:
- **Never** put the blue logo on a dark background or the yellow logo on a light one.
- Prefer **SVG** in HTML slides; PNG is the fallback for contexts that can't render SVG.
- One logo per slide, small and out of the content's way (corner placement). The slide
  tool does this automatically (`variant: auto` picks the right colour for the background).
- The animated videos are a character/accent element, not a replacement for the logo
  mark. Use at most one per deck, and never combine two animated logos on the same slide.

---

## fonts/

Three families, three jobs. Each lives in its own flat folder, **woff2 only** — the
tool only ever renders to a browser, and woff2 is universally supported there, so
the woff/ttf/otf/eot fallbacks that came with the original asset drop were removed
as dead weight (nothing reads them).

| Family | Directory | Weights | Job |
|---|---|---|---|
| **Gjensidige Display** | `fonts/Gjensidige Display/` | Regular | Headlines and hero text ONLY: slide titles, big numbers, pull quotes. Never body text. |
| **Gjensidige Type** | `fonts/Gjensidige Type/` | Light, Regular, Bold (+ italics) | All body copy: paragraphs, bullets, subtitles, tables. |
| **Gjensidige Label** | `fonts/Gjensidige Label/` | Regular | Decorative "tag" font: a light sans with framing rules built into the glyphs above/below the text. For eyebrows/kickers and standalone tags. Do NOT add uppercase or letter-spacing (it breaks the built-in rule lines) and don't use it for long text, footers or page numbers — use Type small-size for those. |

If a print/desktop use case ever needs the other formats, get them fresh from
brand/comms rather than trying to derive them from these woff2 files.

Rules:
- Do not substitute system fonts; the slide tool embeds these via `@font-face`.
- Hierarchy on a slide = Display (title) → Type (content) → Label (metadata). Don't
  invert it.

---

## illustrations/

All illustrations are **1920×1080 SVG scenes** drawn in the official digital palette.
Except `ai` (transparent background), each is a **full-bleed scene on a solid colour
panel** — the panel colour is recorded per illustration in `registry.json`. The slide
tool renders them as rounded image cards, which works on any primary background.

Slugs (use these with the slide tool):

| Slug | File | Use for |
|---|---|---|
| `ai` | Ai.svg | AI, technology, data, automation |
| `bar-chart` | Bar chart RGB.svg | Results, KPIs, financial reporting, statistics |
| `build-bigger` | Build bigger RGB.svg | Growth, ambition, scaling |
| `company-growth` | Company Growth RGB.svg | Company growth, strategy, expansion |
| `animal-insurance` | Gjensidige_Animal Insurance_Digital.svg | Pet/animal insurance products |
| `customer-dividend` | Gjensidige_Customer Yield_Digital.svg | Kundeutbytte, savings, payout, the mutual model |
| `damage-insurance` | Gjensidige_Damage Insurance_Digital.svg | Claims, damage, property insurance |
| `driving-lesson` | Gjensidige_Driving Lesson_Digital.svg | Motor insurance, mobility, young drivers |
| `innovation` | Gjensidige_Innovation_Digital.svg | Innovation, ideas, product development |
| `mental-health` | Gjensidige_Mental Health_Digital.svg | Health, wellbeing, people topics |
| `the-day` | Gjensidige_No One Knows the Day Better_Digital.svg | Brand campaign, everyday life, customers |
| `pension` | Gjensidige_Pension_Digital.svg | Pension, retirement, long-term savings |
| `sustainability` | Gjensidige_Sustainability_Digital.svg | Sustainability, ESG, climate |
| `nordic-map` | Map Nordic RGB.svg | Nordic markets/footprint (country names included) |
| `nordic-map-plain` | Map_Nordic_RGB_without names.svg | Same map without names — decorative/background use |
| `secure-lives` | Secure lives wires RGB.svg | Security, protection, company purpose |
| `security-innovation` | Security Innovation RGB.svg | Security + technology/innovation topics |

Rules:
- Pick the illustration whose **theme matches the slide content** — they are meaningful,
  not generic decoration. If nothing matches, use no illustration rather than a wrong one.
- One illustration per slide, never overlapping text.
- Don't recolour, crop into odd shapes, or add effects. Scale proportionally only
  (they're 16:9; `object-fit: contain`).
