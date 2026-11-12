# The Gjensidige deck format (`deck.json`)

A presentation at Gjensidige is three separable layers:

1. **Brand truth** — colours, fonts, logos, illustrations and their usage rules.
   Lives next to this spec as data: `../assets/registry.json` (colours, logos, fonts,
   illustrations — all in one machine-readable manifest).
2. **Content** — what the deck says: an ordered list of slides, each with an
   *intent* layout and text fields. That is `deck.json`, specified here. Nothing in
   it is HTML- or PowerPoint-specific.
3. **Renderer** — the format-specific part. Today there are two:
   - **HTML**: `../scripts/slides.mjs` renders `deck.json` directly.
   - **PowerPoint**: the sibling `powerpoint-gjensidige` skill in this repository
     builds the same content on the official template. Its layouts are matched to
     the intents below by auditing the template, never by hardcoded index.

Any new output format (Google Slides, PDF-first, …) should be a new renderer over
this same model — not a new content format.

Machine-readable schema: [`deck.schema.json`](deck.schema.json).

## Layout intents

| intent | meaning | HTML renderer | PowerPoint mapping (by audit) |
|---|---|---|---|
| `title` | deck opener: title, subtitle, author, date | title layout | Cover page layout |
| `section` | chapter divider, auto-numbered | section layout | Section/divider layout |
| `content` | heading + bullets or paragraphs | content layout | Title-and-bullets layout |
| `two-column` | two titled columns of text/bullets | two-column layout | Two-column layout |
| `image` | illustration-led slide with short text | image layout | Picture/content layout |
| `quote` | one quotation with attribution | quote layout | Lead-text/statement layout |
| `stat` | one big number with a label | stat layout | Emphasised-number treatment |
| `closing` | thank-you/contact slide | closing layout | Closing/back-cover layout |

## Field reference

Deck level: `name` (kebab-case id), `title`, `footerText`, `lang`,
`theme.background` (one of the five primary colours: `darkBlue`, `logoBlue`,
`yellow`, `white`, `purple`), `theme.accent` (secondary colour family),
`theme.footer` (bool), `slides[]`.

Slide level (all optional except `layout`): `title`, `subtitle`, `eyebrow`, `body`,
`author`, `date`, `bullets[]`, `left-title`, `left-body`, `left-bullets[]`,
`right-title`, `right-body`, `right-bullets[]`, `quote`, `attribution`, `stat`,
`stat-label`, `illustration` (slug from `../assets/registry.json`), `image-side`
(`left`|`right`), `background` / `accent` (per-slide theme override), `logo`
(`auto`|`blue`|`yellow`|`none`), `animatedLogo` (bool; set via the CLI's
`--animated-logo`; customer-dividend content only), `notes` (speaker notes).

Text conventions, all renderers: `**bold**`, `_italic_`; `;;` separates bullets or
paragraphs when a field arrives as one string. Norwegian text keeps æ, ø, å intact.

## Brand rules that bind every renderer

- Slide backgrounds come only from the five primary colours; secondary colours are
  accents and text only.
- Logo colour follows the background: yellow on dark, blue on light (`auto`).
- Fonts: Gjensidige Display for headlines and big numbers, Type for body, Label for
  eyebrows/footers. In PowerPoint these are inherited from the template; in HTML
  they are embedded from `assets/fonts/`.
