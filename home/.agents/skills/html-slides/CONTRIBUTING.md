# Adding assets to the Gjensidige slide tool

This guide is for anyone who has a new brand asset — usually an illustration — and
wants every slide-tool user in the company to get it. Total effort: one small pull
request, no code changes. The tool reads `assets/registry.json` at runtime, so once
your PR merges, the asset simply exists for everyone on their next skill update.

**Golden rule: never edit an installed copy of this skill.** Installed copies
(`~/.claude/plugins/...`, `~/.agents/skills/...`, `~/.config/opencode/skills/...`)
are overwritten on update and are not reviewed by anyone. Contributions go through
a checkout of the repo:

```bash
git clone https://github.com/gjensidige/skills.git
cd skills
git checkout -b add-<asset-name>
cd skills/html-slides
```

## Adding an illustration (the common case)

Illustrations are **1920×1080 SVG scenes in the official digital palette**. If yours
doesn't match that, talk to brand/comms before adding it.

### 1. Drop the file in

Copy the SVG into `assets/illustrations/`, keeping its official filename
(e.g. `Gjensidige_Cyber Security_Digital.svg`).

### 2. Register it in `assets/registry.json`

Add an entry under `"illustrations"`. This step is what makes the asset exist for
the tool — without it, the file is invisible:

```json
"cyber-security": {
  "file": "illustrations/Gjensidige_Cyber Security_Digital.svg",
  "title": "Cyber security",
  "panel": "#B6F4FA",
  "themes": ["cyber", "security", "it", "data protection"]
}
```

Field by field:

| Field | What it is | How to get it |
|---|---|---|
| key (`cyber-security`) | The slug users type: kebab-case, short, unique | You choose it |
| `file` | Path relative to `assets/` | The file you just copied |
| `title` | Human-readable name | — |
| `panel` | The solid background colour of the scene | Open the SVG in a text editor; find the full-canvas `<rect ... fill="#XXXXXX">` (usually the first element). That hex is the panel. |
| `transparent` | Use `"transparent": true` INSTEAD of `panel` | Only if the artwork has no background rect (like `ai`) |
| `themes` | Lowercase keywords matched against slide content | Think: "which slide topics should suggest this illustration?" |

### 3. Document it in `assets/ASSETS.md`

Add one row to the illustrations table (keep the existing format):

```markdown
| `cyber-security` | Gjensidige_Cyber Security_Digital.svg | Cyber security, IT risk, data protection |
```

The "Use for" column is the judgement call only you can make: when should someone
pick this illustration — and implicitly, when not. Be specific; "technology stuff"
helps nobody.

### 4. Check your work

```bash
# your slug should appear:
node scripts/slides.mjs list-assets --type illustrations

# and render correctly (run from any scratch folder; test decks are not committed):
node scripts/slides.mjs create-deck asset-check --title Check
node scripts/slides.mjs add-slide asset-check --layout image --illustration cyber-security --title "Looks right?"
```

Open `decks/asset-check/index.html` in a browser and eyeball it: the illustration
should sit in a rounded card, no clipping, panel colour looking intentional against
the slide background.

### 5. Open the PR

Commit the three changes (SVG + registry entry + ASSETS.md row) on your branch and
open a PR to `gjensidige/skills`. CODEOWNERS routes it to review automatically.
Once merged, everyone gets the asset on their next `git pull` / skill update —
no announcement needed, `list-assets` shows it.

## Adding logos or fonts (rare)

These are structural brand elements — the tool has rendering logic tied to them
(logo auto-selection, `@font-face` blocks). The same three steps apply (file +
`registry.json` entry + `ASSETS.md` documentation), but expect the PR review to
involve the brand owners. Fonts go in as **woff2 only** (see `assets/ASSETS.md`) —
don't add the other formats back, nothing in the tool reads them. Check whether
`scripts/slides.mjs` needs a matching change too. When in doubt, open an issue in
`gjensidige/skills` first and describe what you want to add.

## Adding or correcting a colour (rare)

Colours are pure data — there is no `colors/` folder. Edit the relevant value in
`registry.json` (`colors.primary`, `.secondaryRamps`, or `.digitalAccents`), set its
`source` field honestly (asset-exact vs. sampled), and update the notes in
`assets/ASSETS.md`. A new **primary** (slide-background) colour also needs
`scripts/slides.mjs` updated — background validation and the dark/light text-contrast
rules are driven from the registry, but adding a new one is a brand decision, not a
routine PR; loop in the brand owners first.
