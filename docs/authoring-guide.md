# PPT Press · authoring guide

This is the reference the skill loads while writing pages. It is deliberately
short: HTML + CSS in, an editable PPTX out.

Everything you write maps onto a **native PowerPoint object**. If a CSS feature
is not listed here, it is silently dropped rather than rendered as a picture.

---

## 1. The document skeleton

```html
<!doctype html>
<html data-size="16:9">      <!-- 16:9 | 4:3 | 1:1 | 9:16 | 1280x720 | A4 -->
<head><meta charset="utf-8"><style> … </style></head>
<body>
  <section class="slide"> … page 1 … </section>
  <section class="slide"> … page 2 … </section>
  <aside class="notes">Speaker notes for the deck</aside>
</body>
</html>
```

| Rule | Why |
|---|---|
| One `<section class="slide">` per page | Every section becomes one PowerPoint slide |
| All styles in `<style>` or a `<link rel=stylesheet>` next to the file | Links are read from disk; remote URLs are ignored (offline by design) |
| Design in **1280×720 px** (16:9) | 1 px = 0.75 pt, so the canvas is exactly 960×540 pt |
| `<aside class="notes">` for narration | Becomes the slide's speaker notes |
| Keep text verbatim in the HTML | The deck is the source of truth; PPTX is a build artefact |

---

## 2. What each element becomes

| HTML / CSS | PowerPoint object | Editable |
|---|---|---|
| `div`, `section`, painted box | Autoshape (rect / rounded rect / custom path) with fill, border, shadow | Yes — colour, corner, border |
| `h1`…`h6`, `p`, `li`, `blockquote` | Text box, one **paragraph per laid-out line** | Yes — text, font, size, colour |
| `<b> <i> <u> <s> <sub> <sup> <small>` | Runs inside the paragraph | Yes — each run independently |
| `ul` / `ol` → `li` | Native bullets (`buChar`) / native numbering (`buAutoNum`) | Yes — bullet and scheme |
| `img` | Picture with `object-fit` crop | Yes — replace, crop, recolour |
| inline `<svg>` | **Native vector shapes** (custom geometry) | Yes — can be recoloured |
| `table` | PowerPoint table with merged cells and per-cell borders | Yes — edit cells live |
| `background` | Slide background / full-bleed shape | Yes |
| `box-shadow` | Native outer shadow | Yes |
| `text-shadow` | Native shadow **on the run** | Yes |
| `linear-gradient` | Native gradient fill | Yes |
| `radial-gradient` | Native gradient fill, approximated as a linear ramp | Yes — colour stops only |
| `border-radius` (per corner / `50%`) | Custom geometry (`custGeom`) | Yes |
| `border-style: dashed / dotted` | Native `a:prstDash` | Yes |
| `text-decoration: underline / line-through` | Native `a:rPr@u` / `@strike` | Yes |
| `transform: rotate()` / `translate()` | Shape rotation / offset | Yes |

> **Two rules that save an afternoon:**
>
> 1. **Semantic defaults now work** (`h1` = 32pt/700, `<b>` is bold, `<i>` is
>    italic) via a built-in UA stylesheet, and your own rules still win. Still,
>    write the sizes you mean — an explicit `h1{font-size:52px}` is what makes a
>    deck look designed rather than defaulted.
> 2. **Keep SVG tag names in their real case** (`linearGradient`, `viewBox`).
>    Since 1.1.0 the HTML parser's lowercasing is repaired automatically, but
>    writing them correctly keeps the source readable and portable.

Never produce a full-page picture: the exporter rasterises *nothing* except
SVG icons that use filters, masks, clip-paths or text.

---

## 3. Layout that the engine implements

### Block flow
Normal document flow. Adjacent inline siblings (text + `inline-block` chips +
icons) share a line and wrap when they run out of width.

### Flexbox
```css
.row   { display:flex; gap:20px; align-items:stretch; }
.card  { flex:1; }                  /* even split */
.fixed { width:240px; }             /* fixed column */
```
Supported: `flex-direction` (row/column and `-reverse`), `flex: n`,
`flex-grow`, `gap`, `align-items` (start/center/end/stretch),
`align-self`, `justify-content` (start/center/end/space-between).

### Grid
```css
.grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:20px; }
```
Supported tracks: `Npx`, `Npt`, `N%`, `Nfr`, `auto`, `repeat(n, …)`,
`repeat(auto-fit, …)`, and mixed lists (`1.2fr 1fr`).

### Absolute positioning
```css
.badge { position:absolute; right:64px; top:56px; }
.orbs  { position:absolute; right:-140px; top:-150px; }
```
Resolved against the nearest positioned ancestor; `left+right` and `top+bottom`
pairs stretch the box, a single side anchors it, and the box shrinks to fit its
content when no width is given. Shapes that leave the slide are allowed (that is
how bleeds work) — but keep them decorative.

### Doesn't exist here (by design)
`float`, `columns`, `position:sticky`, `filter`, `backdrop-filter`,
`clip-path`, `transform` on text runs, `@keyframes`, `calc()` beyond the simple
cases, media queries. Use the composition instead of fighting the renderer.

---

## 4. Type

```css
.slide { font-family:'Inter','Segoe UI','Microsoft YaHei',sans-serif; }
h1     { font-size:52px; line-height:1.1; letter-spacing:-1px; }
.lead  { font-size:19px; line-height:1.65; color:#5A6472; }
```

* Font sizes are in **px** like the web; they are converted to points on export.
  `pt`, `rem`, `em`, `%`, `vw`, `vh` also resolve (2 vw → 19.2 pt on a 16:9 canvas).
* Tag defaults come from a built-in UA stylesheet: `h1` = 32pt/700, `h2` = 24pt/700,
  `b`/`strong` = 700, `i`/`em` = italic, `small` = 0.85em. Author rules override
  them at equal specificity, so a project stylesheet always wins.
  Write the sizes you mean anyway — that is what makes a deck look designed.
* The **first installed family** of the stack is written into the PPTX, so the
  measurement font and the file's font are always the same. Put a real fallback
  in every stack (`'Inter','Segoe UI','Microsoft YaHei',sans-serif`).
* CJK is measured per glyph (full-width), Latin with the font's real metrics.
* `text-transform: uppercase` works; `letter-spacing` maps to native tracking.
* Wrapping is computed once, and each laid-out line becomes one paragraph, so
  PowerPoint never re-wraps a headline you spent time balancing. Use `<br>` to
  break a headline where you want it broken.

---

## 5. Colour and surfaces

```css
:root { --ink:#111827; --brand:#C2410C; --paper:#FBFAF7; }
.card { background:#fff; border:1px solid var(--line); border-radius:12px; }
.hero { background:linear-gradient(160deg,#080B14,#101A33); }
```
* CSS custom properties work everywhere (`var(--x)`).
* `rgba()` alpha is preserved as native transparency.
* `border` accepts per-side widths/styles/colours (uneven borders become
  separate thin bars automatically).
* `box-shadow` takes the first outer shadow; inset shadows are approximated.
* Text colour is fully editable: no text is converted to outlines.

---

## 6. Icons and graphics

```html
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
  <path d="M3 12l4 4L21 4"/>
</svg>
```

The icon inherits `color` from CSS and becomes **native PowerPoint shapes**
(move, resize, recolour, ungroup). Supported: `path`, `rect`, `circle`,
`ellipse`, `line`, `polyline`, `polygon`, `g`, `transform`, gradients, opacity.
Unsupported features fall back to a crisp PNG at 6× scale — check the build
report; it lists every fallback.

For data graphics, prefer real shapes:

```html
<div class="bar-track"><div class="bar-fill" style="width:64%"></div></div>
```

---

## 7. Tables

```html
<table class="matrix">
  <thead><tr><th>业务线</th><th>收入</th></tr></thead>
  <tbody><tr><td>订阅</td><td>6.8</td></tr></tbody>
</table>
```
`colspan` merges cells. Per-cell borders, backgrounds, alignment and padding
are preserved. The table stays a table: filled numbers remain editable.

---

## 8. The build contract

1. **Page job first.** Write one sentence: what can the reader do after this
   page? If you cannot, the page is not ready.
2. **One idea per page.** Supporting details belong on the next page, not in a
   smaller font.
3. **No overflow.** The build reports `content overflow` warnings with the page
   number. Fix the copy or the CSS — never hide it with a smaller font.
4. **Names matter.** Every shape is named from its tag and class
   (`h2: 增长换挡`, `div-card`, `table-matrix`) so the slides are navigable in
   PowerPoint's selection pane.
5. **Speaker notes in `<aside>`.** They survive into PowerPoint's notes pane.

---

## 9. Quick recipes

**Cover with bleed and a chip**

```css
.cover { background:#0B1220; color:#F2F5FF; padding:64px 72px; }
.chip  { position:absolute; right:72px; top:64px; padding:9px 18px;
         border-radius:999px; background:rgba(77,227,208,.14); color:#4DE3D0; }
```

**Three-up KPI row**

```css
.kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:18px; }
.kpi .value { font-size:34px; }
```

**Two-column argument**

```css
.two { display:grid; grid-template-columns:1.05fr .95fr; gap:44px; }
```

**Section divider**

```css
.divider { background:#101A33; color:#fff; display:flex;
           flex-direction:column; justify-content:center; height:100%; }
```

**Bar chart without a chart object**

```css
.bar-row   { display:flex; align-items:center; gap:14px; }
.bar-track { flex:1; height:10px; border-radius:6px; background:rgba(255,255,255,.1); }
.bar-fill  { height:10px; border-radius:6px;
             background:linear-gradient(90deg,#8B7CFF,#4DE3D0); }
```
(The fill width is a real, editable rectangle — a designer can still adjust it.)
