#!/usr/bin/env node
/**
 * Gjensidige slide tool.
 *
 * Each subcommand is a "tool" an agent (or human) can call to build HTML slide
 * decks that always follow the Gjensidige brand rules encoded in
 * assets/registry.json (documented in assets/ASSETS.md).
 *
 * Deck state lives in decks/<name>/deck.json; every mutating command re-renders
 * decks/<name>/index.html so the preview is always current.
 *
 * Run `node tools/slides.mjs help` for the full command reference.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ASSETS = join(ROOT, 'assets');
// Decks are created where the USER works, never inside this (shared, read-only)
// tool repo — unless the user is working in the repo itself.
const DECKS = resolve(process.env.GJ_SLIDES_OUT || join(process.cwd(), 'decks'));
const REG = JSON.parse(readFileSync(join(ASSETS, 'registry.json'), 'utf8'));

const PRIMARY = REG.colors.primary;
const RAMPS = REG.colors.secondaryRamps;
const DIGITAL = REG.colors.digitalAccents;
const DARK_BGS = REG.colors.rules.darkBackgrounds;
const BG_NAMES = REG.colors.rules.slideBackground;

const LAYOUTS = ['title', 'section', 'content', 'two-column', 'image', 'quote', 'stat', 'closing'];

// Accent colour per family, resolved against the slide background so contrast
// and illustration-matching are automatic.
const ACCENTS_ON_DARK = {
  yellow: '#F4FFAF', green: '#50D7A5', turquoise: '#87ECF5', blue: '#8CB2FF',
  purple: '#B099FF', pink: '#FDB6C2', red: '#FF787F', orange: '#FFB58F', white: '#FFFFFF',
};
const ACCENTS_ON_LIGHT = {
  yellow: '#6545BF', green: '#098059', turquoise: '#3D9DA6', blue: '#4164A7',
  purple: '#6545BF', pink: '#CD5D79', red: '#C04952', orange: '#B37251', white: '#090C33',
};

// ---------------------------------------------------------------- utilities

function fail(msg) {
  console.error(`error: ${msg}`);
  process.exit(1);
}

function parseArgs(argv) {
  const pos = [];
  const opts = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      if (i + 1 < argv.length && !argv[i + 1].startsWith('--')) {
        opts[key] = argv[++i];
      } else {
        opts[key] = true;
      }
    } else {
      pos.push(a);
    }
  }
  return { pos, opts };
}

function deckDir(name) { return join(DECKS, name); }
function deckFile(name) { return join(deckDir(name), 'deck.json'); }

function loadDeck(name) {
  if (!name) fail('missing deck name');
  if (!existsSync(deckFile(name))) {
    const available = existsSync(DECKS)
      ? readdirSync(DECKS).filter((d) => existsSync(deckFile(d)))
      : [];
    fail(`no deck named "${name}". Available: ${available.join(', ') || '(none — use create-deck)'}`);
  }
  return JSON.parse(readFileSync(deckFile(name), 'utf8'));
}

function saveDeck(deck) {
  mkdirSync(deckDir(deck.name), { recursive: true });
  writeFileSync(deckFile(deck.name), JSON.stringify(deck, null, 2));
  const out = render(deck);
  console.log(`deck "${deck.name}": ${deck.slides.length} slide(s) — rendered ${out}`);
}

function checkBackground(bg) {
  if (!BG_NAMES.includes(bg)) {
    fail(`"${bg}" is not a valid slide background. Brand rule: backgrounds must be a primary colour: ${BG_NAMES.join(', ')}`);
  }
  return bg;
}

function checkAccent(name) {
  if (!(name in ACCENTS_ON_DARK)) {
    fail(`"${name}" is not a valid accent. Use one of: ${Object.keys(ACCENTS_ON_DARK).join(', ')}`);
  }
  return name;
}

function checkIllustration(slug) {
  const slugs = Object.keys(REG.illustrations).filter((k) => !k.startsWith('$'));
  if (!slugs.includes(slug)) {
    fail(`unknown illustration "${slug}". Use one of: ${slugs.join(', ')} (see list-assets)`);
  }
  return slug;
}

function checkLayout(l) {
  if (!LAYOUTS.includes(l)) fail(`unknown layout "${l}". Use one of: ${LAYOUTS.join(', ')}`);
  return l;
}

// CLI variant name -> registry.logos key. "kundeutbytte" (the bare --animated-logo
// default) keeps its historical registry key "animated" for backward compatibility.
const ANIMATED_LOGO_VARIANTS = { kundeutbytte: 'animated', 'outro-short': 'outro-short', 'outro-long': 'outro-long' };
function checkAnimatedLogo(variant) {
  if (!(variant in ANIMATED_LOGO_VARIANTS)) {
    fail(`--animated-logo must be one of: ${Object.keys(ANIMATED_LOGO_VARIANTS).join(', ')} (bare flag = kundeutbytte)`);
  }
  return variant;
}

function slideIndex(deck, nStr) {
  const n = parseInt(nStr, 10);
  if (!Number.isInteger(n) || n < 1 || n > deck.slides.length) {
    fail(`slide number must be 1..${deck.slides.length}`);
  }
  return n - 1;
}

const esc = (s) => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// Minimal inline markup after escaping: **bold** and _italic_.
const rich = (s) => esc(s)
  .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  .replace(/_(.+?)_/g, '<em>$1</em>');

const bullets = (v) => (Array.isArray(v) ? v : String(v).split(';;')).map((b) => b.trim()).filter(Boolean);

// Copy recognised slide fields from CLI options onto a slide object.
const SLIDE_FIELDS = [
  'title', 'subtitle', 'eyebrow', 'body', 'author', 'date',
  'left-title', 'left-body', 'right-title', 'right-body',
  'quote', 'attribution', 'stat', 'stat-label', 'image-side', 'notes',
];
function applyFields(slide, opts) {
  for (const f of SLIDE_FIELDS) {
    if (f in opts) slide[f] = opts[f] === '' ? undefined : opts[f];
  }
  for (const f of ['bullets', 'left-bullets', 'right-bullets']) {
    if (f in opts) slide[f] = opts[f] === '' ? undefined : bullets(opts[f]);
  }
  if ('illustration' in opts) {
    slide.illustration = opts.illustration === '' || opts.illustration === 'none'
      ? undefined : checkIllustration(opts.illustration);
  }
  if ('background' in opts) slide.background = checkBackground(opts.background);
  if ('accent' in opts) slide.accent = checkAccent(opts.accent);
  if ('logo' in opts) {
    const v = opts.logo;
    if (!['auto', 'blue', 'yellow', 'none'].includes(v)) fail('--logo must be auto|blue|yellow|none');
    slide.logo = v;
  }
  if ('animated-logo' in opts) {
    const raw = opts['animated-logo'];
    slide.animatedLogo = (raw === 'false' || raw === '')
      ? undefined
      : checkAnimatedLogo(raw === true ? 'kundeutbytte' : raw);
  }
  return slide;
}

// ---------------------------------------------------------------- rendering

let REL_ASSETS = '../../assets'; // set per render: deck output dir -> assets dir

function assetHref(relFromAssets, embed) {
  const abs = join(ASSETS, relFromAssets);
  if (!embed) return encodeURI(`${REL_ASSETS}/${relFromAssets}`.replace(/\\/g, '/'));
  const ext = relFromAssets.split('.').pop().toLowerCase();
  const mime = {
    woff2: 'font/woff2', woff: 'font/woff', svg: 'image/svg+xml',
    png: 'image/png', mp4: 'video/mp4',
  }[ext] || 'application/octet-stream';
  return `data:${mime};base64,${readFileSync(abs).toString('base64')}`;
}

function themeFor(deck, slide) {
  const bg = slide.background || deck.theme.background;
  const dark = DARK_BGS.includes(bg);
  const accentName = slide.accent || deck.theme.accent || 'yellow';
  return {
    bg,
    bgHex: PRIMARY[bg].hex,
    dark,
    ink: dark ? REG.colors.rules.textOnDark.body : REG.colors.rules.textOnLight.body,
    muted: dark ? 'rgba(255,255,255,0.72)' : 'rgba(9,12,51,0.72)',
    accent: (dark ? ACCENTS_ON_DARK : ACCENTS_ON_LIGHT)[accentName],
    logoVariant: (slide.logo && slide.logo !== 'auto') ? slide.logo : (dark ? 'yellow' : 'blue'),
    showLogo: slide.logo !== 'none',
  };
}

function logoImg(t, embed, cls = 'logo') {
  const href = assetHref(REG.logos[t.logoVariant].svg, embed);
  return `<img class="${cls}" src="${href}" alt="Gjensidige">`;
}

function illuImg(slug, embed, cls = 'illu') {
  const href = assetHref(REG.illustrations[slug].file, embed);
  return `<img class="${cls}" src="${href}" alt="${esc(REG.illustrations[slug].title)}">`;
}

function animatedLogoVideo(variant, embed, cls = 'anim-logo') {
  const key = ANIMATED_LOGO_VARIANTS[variant] || 'animated';
  const href = assetHref(REG.logos[key].file, embed);
  // The kundeutbytte symbol is an ambient loop; the outro stings are a one-off
  // sign-off and hold on their final frame instead of restarting mid-slide.
  const loop = key === 'animated' ? ' loop' : '';
  return `<video class="${cls}" src="${href}" autoplay muted${loop} playsinline></video>`;
}

function bulletList(items, cls = 'bullets') {
  return `<ul class="${cls}">${items.map((b) => `<li>${rich(b)}</li>`).join('')}</ul>`;
}

function bodyHtml(text) {
  return String(text).split(/\n\n+|;;/).map((p) => `<p>${rich(p.trim())}</p>`).join('');
}

function colHtml(slide, side) {
  const title = slide[`${side}-title`];
  const body = slide[`${side}-body`];
  const items = slide[`${side}-bullets`];
  let h = '<div class="col">';
  if (title) h += `<h3>${rich(title)}</h3>`;
  if (body) h += `<div class="body">${bodyHtml(body)}</div>`;
  if (items) h += bulletList(items);
  return h + '</div>';
}

function renderSlide(deck, slide, i, sectionNo, embed) {
  const t = themeFor(deck, slide);
  const isOutro = slide.animatedLogo === 'outro-short' || slide.animatedLogo === 'outro-long';
  const media = slide.animatedLogo
    ? animatedLogoVideo(slide.animatedLogo, embed)
    : (slide.illustration ? illuImg(slide.illustration, embed) : '');
  let inner = '';

  switch (slide.layout) {
    case 'title':
      inner = `
        <div class="l-title">
          <div class="text">
            ${slide.eyebrow ? `<div class="eyebrow">${rich(slide.eyebrow)}</div>` : ''}
            <h1>${rich(slide.title || deck.title || '')}</h1>
            ${slide.subtitle ? `<p class="subtitle">${rich(slide.subtitle)}</p>` : ''}
            <div class="meta">${[slide.author, slide.date].filter(Boolean).map(esc).join(' · ')}</div>
          </div>
          ${media ? `<div class="media">${media}</div>` : ''}
        </div>`;
      break;
    case 'section':
      inner = `
        <div class="l-section">
          <div class="section-no">${String(sectionNo).padStart(2, '0')}</div>
          <h1>${rich(slide.title || '')}</h1>
          ${slide.subtitle ? `<p class="subtitle">${rich(slide.subtitle)}</p>` : ''}
          ${media ? `<div class="media">${media}</div>` : ''}
        </div>`;
      break;
    case 'content':
      if (media) {
        // content slide with an illustration/animation: render as image layout
        inner = `
        <div class="l-image media-right">
          <div class="text">
            ${slide.eyebrow ? `<div class="eyebrow">${rich(slide.eyebrow)}</div>` : ''}
            <h2>${rich(slide.title || '')}</h2>
            <div class="rule"></div>
            ${slide.body ? `<div class="body">${bodyHtml(slide.body)}</div>` : ''}
            ${slide.bullets ? bulletList(slide.bullets) : ''}
          </div>
          <div class="media">${media}</div>
        </div>`;
        break;
      }
      inner = `
        <div class="l-content">
          ${slide.eyebrow ? `<div class="eyebrow">${rich(slide.eyebrow)}</div>` : ''}
          <h2>${rich(slide.title || '')}</h2>
          <div class="rule"></div>
          ${slide.body ? `<div class="body">${bodyHtml(slide.body)}</div>` : ''}
          ${slide.bullets ? bulletList(slide.bullets) : ''}
        </div>`;
      break;
    case 'two-column':
      inner = `
        <div class="l-content">
          ${slide.eyebrow ? `<div class="eyebrow">${rich(slide.eyebrow)}</div>` : ''}
          <h2>${rich(slide.title || '')}</h2>
          <div class="rule"></div>
          <div class="cols">${colHtml(slide, 'left')}${colHtml(slide, 'right')}</div>
        </div>`;
      break;
    case 'image': {
      const side = slide['image-side'] === 'left' ? 'media-left' : 'media-right';
      inner = `
        <div class="l-image ${side}">
          <div class="text">
            ${slide.eyebrow ? `<div class="eyebrow">${rich(slide.eyebrow)}</div>` : ''}
            <h2>${rich(slide.title || '')}</h2>
            <div class="rule"></div>
            ${slide.body ? `<div class="body">${bodyHtml(slide.body)}</div>` : ''}
            ${slide.bullets ? bulletList(slide.bullets) : ''}
          </div>
          <div class="media">${media}</div>
        </div>`;
      break;
    }
    case 'quote':
      inner = `
        <div class="l-quote">
          <div class="qmark">“</div>
          <blockquote>${rich(slide.quote || slide.title || '')}</blockquote>
          ${slide.attribution ? `<div class="attribution">${rich(slide.attribution)}</div>` : ''}
        </div>`;
      break;
    case 'stat':
      inner = `
        <div class="l-stat">
          <div class="stat">${rich(slide.stat || '')}</div>
          ${slide['stat-label'] ? `<div class="stat-label">${rich(slide['stat-label'])}</div>` : ''}
          ${slide.body ? `<div class="body">${bodyHtml(slide.body)}</div>` : ''}
        </div>`;
      break;
    case 'closing':
      inner = `
        <div class="l-closing">
          ${media ? `<div class="media${isOutro ? ' media-outro' : ''}">${media}</div>` : ''}
          <h1>${rich(slide.title || 'Takk!')}</h1>
          ${slide.body ? `<div class="body">${bodyHtml(slide.body)}</div>` : ''}
          ${t.showLogo ? logoImg(t, embed, 'logo-center') : ''}
        </div>`;
      break;
  }

  const cornerLogo = t.showLogo && slide.layout !== 'closing' ? logoImg(t, embed) : '';
  const footer = deck.theme.footer !== false && !['title', 'closing'].includes(slide.layout)
    ? `<div class="footer"><span>${esc(deck.footerText || deck.title || deck.name)}</span><span>${i + 1}</span></div>`
    : '';
  const notes = slide.notes ? `<aside class="notes" hidden>${esc(slide.notes)}</aside>` : '';

  return `<section class="slide layout-${slide.layout}" style="--bg:${t.bgHex};--ink:${t.ink};--muted:${t.muted};--accent:${t.accent}">
    ${cornerLogo}${inner}${footer}${notes}
  </section>`;
}

function fontCss(embed) {
  const f = REG.fonts;
  const face = (family, file, weight = 400, style = 'normal') =>
    `@font-face{font-family:'${family}';src:url("${assetHref(file, embed)}") format('woff2');font-weight:${weight};font-style:${style};font-display:swap;}`;
  return [
    face('Gjensidige Display', f.display.web.regular),
    face('Gjensidige Type', f.type.web.light, 300),
    face('Gjensidige Type', f.type.web.regular, 400),
    face('Gjensidige Type', f.type.web.bold, 700),
    face('Gjensidige Type', f.type.web.italic, 400, 'italic'),
    face('Gjensidige Type', f.type.web.lightItalic, 300, 'italic'),
    face('Gjensidige Type', f.type.web.boldItalic, 700, 'italic'),
    face('Gjensidige Label', f.label.web.regular),
  ].join('\n');
}

const BASE_CSS = `
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{background:#05061a;font-family:'Gjensidige Type',sans-serif;overflow:hidden}
.deck{width:1280px;height:720px;position:absolute;top:50%;left:50%;transform-origin:center center}
.slide{position:absolute;inset:0;display:none;flex-direction:column;background:var(--bg);color:var(--ink);padding:64px 80px;overflow:hidden}
.slide.active{display:flex}
h1,h2,.stat,blockquote,.section-no{font-family:'Gjensidige Display',serif;font-weight:400;line-height:1.05}
/* Gjensidige Label has decorative rules built into the glyphs above/below the
   text — no uppercase or letter-spacing, they break the rule lines apart. */
.eyebrow{font-family:'Gjensidige Label',sans-serif;font-size:20px;line-height:2.1;color:var(--accent);margin-bottom:14px}
.meta,.footer,.attribution,.stat-label,.hud{font-family:'Gjensidige Type',sans-serif;font-weight:400;text-transform:uppercase;letter-spacing:0.18em}
.rule{width:72px;height:6px;background:var(--accent);border-radius:3px;margin:22px 0 30px}
.body p{font-size:22px;font-weight:300;line-height:1.5;max-width:900px;margin-bottom:14px}
.body p strong{font-weight:700}
.bullets{list-style:none;margin-top:6px}
.bullets li{font-size:22px;font-weight:300;line-height:1.45;margin-bottom:16px;padding-left:34px;position:relative;max-width:900px}
.bullets li::before{content:'';position:absolute;left:0;top:0.52em;width:14px;height:14px;border-radius:50%;background:var(--accent)}
.logo{position:absolute;top:36px;right:56px;height:58px}
.footer{position:absolute;bottom:0;left:0;right:0;display:flex;justify-content:space-between;padding:20px 56px;font-size:11px;color:var(--muted)}
.media{display:flex;align-items:center;justify-content:center}
.illu{max-width:100%;max-height:100%;object-fit:contain;border-radius:20px}
.anim-logo{max-width:100%;max-height:100%;object-fit:contain;border-radius:20px}
.notes{display:none}

.l-title{display:flex;flex:1;align-items:center;gap:40px}
.l-title .text{flex:1.1;z-index:2}
.l-title h1{font-size:76px;letter-spacing:-0.01em;margin-bottom:26px}
.l-title .subtitle{font-size:26px;font-weight:300;color:var(--muted);max-width:640px;line-height:1.4}
.l-title .meta{margin-top:44px;font-size:14px;color:var(--muted)}
.l-title .media{flex:1;height:82%;align-self:flex-end}

.l-section{display:flex;flex:1;flex-direction:column;justify-content:center;position:relative}
.section-no{font-size:120px;color:var(--accent);margin-bottom:8px}
.l-section h1{font-size:64px;max-width:820px}
.l-section .subtitle{font-size:24px;font-weight:300;color:var(--muted);margin-top:22px;max-width:700px;line-height:1.4}
.l-section{padding-right:44%}
.l-section .media{position:absolute;right:80px;top:50%;transform:translateY(-50%);width:38%}

.l-content{display:flex;flex:1;flex-direction:column;padding-top:8px}
.l-content h2{font-size:44px;max-width:1000px}
.cols{display:flex;gap:64px;flex:1}
.col{flex:1}
.col h3{font-size:26px;font-weight:700;margin-bottom:14px;color:var(--accent)}
.col .body p,.col .bullets li{font-size:20px}

.l-image{display:flex;flex:1;gap:56px;align-items:center}
.l-image .text{flex:1.15}
.l-image .media{flex:1;height:86%}
.l-image.media-left{flex-direction:row-reverse}
.l-image h2{font-size:44px}

.l-quote{display:flex;flex:1;flex-direction:column;justify-content:center;max-width:1020px;margin:0 auto}
.qmark{font-family:'Gjensidige Display',serif;font-size:140px;line-height:0.6;color:var(--accent);margin-bottom:8px}
.l-quote blockquote{font-size:46px;line-height:1.25}
.attribution{margin-top:36px;font-size:15px;color:var(--muted)}

.l-stat{display:flex;flex:1;flex-direction:column;justify-content:center;align-items:center;text-align:center}
.stat{font-size:170px;color:var(--accent);letter-spacing:-0.02em}
.stat-label{font-size:18px;margin-top:10px}
.l-stat .body{margin-top:30px}
.l-stat .body p{max-width:760px}

.l-closing{display:flex;flex:1;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:28px}
.l-closing h1{font-size:92px}
.l-closing .media{width:240px;height:240px}
.l-closing .media .anim-logo{border-radius:50%}
.l-closing .media.media-outro{width:64%;height:auto;aspect-ratio:16/9}
.l-closing .media.media-outro .anim-logo{border-radius:20px}
.logo-center{height:110px;margin-top:26px}

.hud{position:fixed;bottom:14px;right:18px;font-size:11px;color:rgba(255,255,255,0.45);z-index:10}

@media print{
  @page{size:1280px 720px;margin:0}
  body{overflow:visible;background:none}
  .deck{position:static;width:1280px;height:auto;transform:none!important}
  .slide{display:flex;position:relative;width:1280px;height:720px;page-break-after:always;break-after:page}
  .hud{display:none}
}
`;

const NAV_JS = `
const slides=[...document.querySelectorAll('.slide')];let cur=0;
function show(n){cur=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>s.classList.toggle('active',i===cur));
document.getElementById('counter').textContent=(cur+1)+' / '+slides.length;history.replaceState(null,'','#'+(cur+1));}
function fit(){const d=document.getElementById('deck');const s=Math.min(innerWidth/1280,innerHeight/720);
d.style.transform='translate(-50%,-50%) scale('+s+')';}
addEventListener('resize',fit);
addEventListener('keydown',e=>{if(['ArrowRight','ArrowDown','PageDown',' '].includes(e.key))show(cur+1);
else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key))show(cur-1);
else if(e.key==='Home')show(0);else if(e.key==='End')show(slides.length-1);});
addEventListener('click',e=>{if(e.clientX>innerWidth*0.66)show(cur+1);else if(e.clientX<innerWidth*0.33)show(cur-1);});
fit();show((parseInt(location.hash.slice(1))||1)-1);
`;

function render(deck, embed = deck.embed) {
  REL_ASSETS = relative(deckDir(deck.name), ASSETS).replace(/\\/g, '/');
  let sectionNo = 0;
  const slidesHtml = deck.slides.map((s, i) => {
    if (s.layout === 'section') sectionNo++;
    return renderSlide(deck, s, i, sectionNo, embed);
  }).join('\n');

  const html = `<!doctype html>
<html lang="${deck.lang || 'en'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(deck.title || deck.name)}</title>
<style>
${fontCss(embed)}
${BASE_CSS}
</style>
</head>
<body>
<div class="deck" id="deck">
${slidesHtml}
</div>
<div class="hud"><span id="counter"></span></div>
<script>${NAV_JS}</script>
</body>
</html>`;

  mkdirSync(deckDir(deck.name), { recursive: true });
  const out = join(deckDir(deck.name), 'index.html');
  writeFileSync(out, html);
  return out;
}

// ---------------------------------------------------------------- commands

const commands = {
  'create-deck'({ pos, opts }) {
    const name = pos[0] || fail('usage: create-deck <name> [--title ... --subtitle ... --author ... --date ... --background darkBlue --accent yellow]');
    if (existsSync(deckFile(name))) fail(`deck "${name}" already exists (decks/${name}/deck.json)`);
    if (!/^[a-z0-9-]+$/.test(name)) fail('deck name must be kebab-case: lowercase letters, digits, hyphens');
    const deck = {
      name,
      title: opts.title || name,
      footerText: opts.footer,
      lang: opts.lang,
      theme: {
        background: checkBackground(opts.background || 'darkBlue'),
        accent: checkAccent(opts.accent || 'yellow'),
        footer: true,
      },
      slides: [],
    };
    if (!opts['no-title-slide']) {
      deck.slides.push(applyFields({
        layout: 'title',
        title: opts.title || name,
        subtitle: opts.subtitle,
        author: opts.author,
        date: opts.date,
        eyebrow: opts.eyebrow,
      }, opts));
    }
    saveDeck(deck);
  },

  'add-slide'({ pos, opts }) {
    const deck = loadDeck(pos[0]);
    const layout = checkLayout(opts.layout || 'content');
    const slide = applyFields({ layout }, opts);
    const at = 'at' in opts ? slideIndex(deck, opts.at) + 1 : deck.slides.length;
    deck.slides.splice(at, 0, slide);
    saveDeck(deck);
  },

  'update-slide'({ pos, opts }) {
    const deck = loadDeck(pos[0]);
    const i = slideIndex(deck, pos[1]);
    if (opts.layout) deck.slides[i].layout = checkLayout(opts.layout);
    applyFields(deck.slides[i], opts);
    saveDeck(deck);
  },

  'remove-slide'({ pos }) {
    const deck = loadDeck(pos[0]);
    deck.slides.splice(slideIndex(deck, pos[1]), 1);
    saveDeck(deck);
  },

  'move-slide'({ pos }) {
    const deck = loadDeck(pos[0]);
    const from = slideIndex(deck, pos[1]);
    const to = slideIndex(deck, pos[2]);
    const [s] = deck.slides.splice(from, 1);
    deck.slides.splice(to, 0, s);
    saveDeck(deck);
  },

  'list-slides'({ pos }) {
    const deck = loadDeck(pos[0]);
    console.log(`deck "${deck.name}" — "${deck.title}" — background:${deck.theme.background} accent:${deck.theme.accent}`);
    deck.slides.forEach((s, i) => {
      const label = s.title || s.quote || s.stat || '';
      const extras = [
        s.illustration && `illu:${s.illustration}`,
        s.animatedLogo && `animated-logo:${s.animatedLogo}`,
        s.background && `bg:${s.background}`,
        s.accent && `accent:${s.accent}`,
      ].filter(Boolean).join(' ');
      console.log(`  ${String(i + 1).padStart(2)}. [${s.layout}] ${label} ${extras ? `(${extras})` : ''}`);
    });
  },

  // change_color: deck-wide background/accent (per-slide via update-slide --background/--accent)
  'set-theme'({ pos, opts }) {
    const deck = loadDeck(pos[0]);
    if (opts.background) deck.theme.background = checkBackground(opts.background);
    if (opts.accent) deck.theme.accent = checkAccent(opts.accent);
    if (opts.footer) deck.theme.footer = opts.footer !== 'false';
    if (opts['footer-text']) deck.footerText = opts['footer-text'];
    if (opts.title) deck.title = opts.title;
    saveDeck(deck);
  },

  // add_logo: control the logo per slide or deck-wide
  'set-logo'({ pos, opts }) {
    const deck = loadDeck(pos[0]);
    const v = opts.variant || 'auto';
    if (!['auto', 'blue', 'yellow', 'none'].includes(v)) fail('--variant must be auto|blue|yellow|none');
    if (opts.slide) {
      deck.slides[slideIndex(deck, opts.slide)].logo = v;
    } else {
      deck.slides.forEach((s) => { s.logo = v; });
    }
    saveDeck(deck);
  },

  'render'({ pos, opts }) {
    const deck = loadDeck(pos[0]);
    if ('embed' in opts) deck.embed = opts.embed !== 'false';
    writeFileSync(deckFile(deck.name), JSON.stringify(deck, null, 2));
    const out = render(deck);
    console.log(`rendered ${out}${deck.embed ? ' (self-contained: fonts & media embedded)' : ''}`);
    console.log(`open: file://${out}`);
  },

  'list-decks'() {
    if (!existsSync(DECKS)) return console.log('(no decks yet)');
    for (const d of readdirSync(DECKS)) {
      if (!existsSync(deckFile(d))) continue;
      const deck = JSON.parse(readFileSync(deckFile(d), 'utf8'));
      console.log(`${d} — "${deck.title}" — ${deck.slides.length} slide(s)`);
    }
  },

  'list-assets'({ opts }) {
    const type = opts.type;
    if (!type || type === 'colors') {
      console.log('# Backgrounds (primary — the ONLY allowed slide backgrounds)');
      for (const [k, v] of Object.entries(PRIMARY)) console.log(`  ${k}: ${v.hex} (${v.name})`);
      console.log('# Accents (resolved per background)');
      for (const k of Object.keys(ACCENTS_ON_DARK)) {
        console.log(`  ${k}: on dark ${ACCENTS_ON_DARK[k]}, on light ${ACCENTS_ON_LIGHT[k]}`);
      }
      console.log('# Full secondary ramps + digital accents: assets/registry.json');
    }
    if (!type || type === 'illustrations') {
      console.log('# Illustrations (slug: themes)');
      for (const [slug, v] of Object.entries(REG.illustrations)) {
        if (slug.startsWith('$')) continue;
        console.log(`  ${slug}: ${v.themes.join(', ')}`);
      }
    }
    if (!type || type === 'logos') {
      console.log('# Logos');
      console.log('  blue logo -> light backgrounds; yellow logo -> dark backgrounds (auto by default)');
      console.log('  animated (--animated-logo on a slide):');
      for (const variant of Object.keys(ANIMATED_LOGO_VARIANTS)) {
        console.log(`    ${variant}: ${REG.logos[ANIMATED_LOGO_VARIANTS[variant]].use}`);
      }
    }
    if (!type || type === 'fonts') {
      console.log('# Fonts (embedded automatically)');
      for (const [k, v] of Object.entries(REG.fonts)) console.log(`  ${v.family}: ${v.use}`);
    }
  },

  help() {
    console.log(`Gjensidige slide tool — every command re-renders decks/<name>/index.html

  create-deck <name> [--title T --subtitle S --author A --date D --eyebrow E]
              [--background ${BG_NAMES.join('|')}] [--accent yellow|green|...]
              [--no-title-slide] [--footer-text T] [--lang no|en]
  add-slide <deck> --layout ${LAYOUTS.join('|')}
              [--title --subtitle --eyebrow --body --bullets "a;;b;;c"]
              [--left-title --left-body --left-bullets] [--right-...]   (two-column)
              [--quote --attribution] [--stat --stat-label]             (quote / stat)
              [--illustration <slug>] [--image-side left|right]         (image)
              [--animated-logo [kundeutbytte|outro-short|outro-long]]  (video instead of illustration;
                bare flag = kundeutbytte; outro-* = brand sign-off, closing slide only)
              [--background <primary>] [--accent <name>] [--logo auto|blue|yellow|none]
              [--notes "speaker notes"] [--at N  (insert after slide N)]
  update-slide <deck> <n> [same flags; pass --field "" to clear a field]
  remove-slide <deck> <n>        move-slide <deck> <from> <to>
  list-slides <deck>             list-decks
  set-theme <deck> [--background ...] [--accent ...] [--title ...] [--footer-text ...] [--footer false]
  set-logo <deck> [--variant auto|blue|yellow|none] [--slide N]
  render <deck> [--embed]        --embed makes a single self-contained HTML file
  list-assets [--type colors|illustrations|logos|fonts]

Text supports **bold**, _italic_; ";;" separates bullets/paragraphs.
Brand rules are enforced: backgrounds = primary colours only; logo colour auto-matches background.
Asset docs: assets/ASSETS.md`);
  },
};

const [, , cmd, ...rest] = process.argv;
const handler = commands[cmd || 'help'];
if (!handler) fail(`unknown command "${cmd}". Run: node tools/slides.mjs help`);
handler(parseArgs(rest));
