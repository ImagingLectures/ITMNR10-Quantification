# ETH / PSI lecture suite — Quarto template

One source, three deliverables:

| Deliverable | Command | Output |
|---|---|---|
| revealjs slides, one lecture | `pixi run slides Lecture01` | `_output/Lectures/Lecture01/Lecture01-slides.html` |
| slides as PDF | `pixi run slides-pdf Lecture01` | `…/Lecture01-slides.pdf` |
| PDF lecture notes, one lecture | `pixi run notes Lecture01` | `…/Lecture01-notes.pdf` |
| PDF notes, whole course | `pixi run course` | `_output/course-notes.pdf` |
| everything | `pixi run all` | all of the above |

The source of truth is always the notebooks. Nothing is written twice.

---

## Quick start

```bash
pixi install
pixi run setup          # once: TinyTeX + Chromium
pixi run all
```

To work on a lecture:

```bash
pixi run lab            # edit Part_L1P1.ipynb … in JupyterLab
pixi run lecture 1      # slides + notes for Lecture01
```

Lectures can be named `Lecture01`, `1`, or `Lectures/Lecture01` — all resolve
to the same folder. Omit the name to build every lecture.

---

## Layout

```
quarto-lecture-suite/
├── pixi.toml                  # environment + tasks
├── course.yml                 # course-wide metadata (title, author, logos)
├── _quarto.yml                # Quarto project config (output dir, freeze, crossref)
├── references.bib             # shared bibliography
│
├── _extensions/ethpsi/        # all styling lives here
│   ├── _extension.yml         # defines the ethpsi-revealjs and ethpsi-pdf formats
│   ├── ethpsi-slides.scss     # slide theme
│   └── partials/
│       ├── title-slide.html   # revealjs title slide
│       ├── before-body.tex    # PDF title page + ToC
│       └── preamble.tex       # PDF numbering, colours, headers/footers
│
├── assets/
│   ├── logos/                 # psi-logo.{svg,png}
│   └── artwork/               # course.{svg,png}, lecture01.{svg,png}, …
│
├── scripts/
│   ├── build.py               # assembles notebooks → .qmd, drives Quarto
│   ├── courselib.py           # path helper imported by the notebooks
│   └── slides_to_pdf.py       # prints revealjs decks to PDF
│
└── Lectures/
    ├── Lecture01/
    │   ├── lecture.yml        # lecture number, title, date, artwork
    │   ├── Part_L1P1.ipynb
    │   ├── Part_L1P2.ipynb
    │   ├── figures/
    │   └── data/
    └── Lecture02/ …
```

---

## How the build works

`scripts/build.py` concatenates every `Part_L<m>P<n>.ipynb` of a lecture, in
part order, into a generated `.qmd` file, then calls Quarto on it:

```
Part_L1P1.ipynb ┐
Part_L1P2.ipynb ┼─→ Lecture01-slides.qmd ─→ quarto --to ethpsi-revealjs ─→ .html ─→ .pdf
                └─→ Lecture01-notes.qmd  ─→ quarto --to ethpsi-pdf      ─→ .pdf
                └─→ course-notes.qmd     ─→ quarto --to ethpsi-pdf      ─→ .pdf  (all lectures)
```

Generated files (`*-slides.qmd`, `*-notes.qmd`, `_logos.html`,
`course-notes.qmd`) are build artefacts and are git-ignored. Never edit them;
regenerate with `pixi run assemble`.

Two things are handled per target so that the same notebooks work everywhere:

- **Figure paths.** The course build rewrites `figures/x.png` to
  `Lectures/Lecture01/figures/x.png`.
- **Asset formats.** Slides use the `.svg` logo/artwork, LaTeX automatically
  gets the `.png` (or `.pdf`) twin, since pdfLaTeX cannot read SVG.

`execute: freeze: auto` in `_quarto.yml` means a notebook is only re-executed
when it actually changed, so rebuilds are cheap.

---

## Header levels

The mapping requested in the specification is implemented as follows.

| Level | Markdown | Slides | PDF notes | Number |
|---|---|---|---|---|
| 0 | *(from `lecture.yml`)* | title slide | `\chapter` | `1` |
| 1 | `#` | part separator slide | `\section` | `1.1` |
| 2 | `##` | one slide | `\subsection` | `1.1.1` |
| 3 | `###` | heading on the slide | `\subsubsection` | `1.1.1.1` |

Each notebook is one part, so a notebook begins with a single `#` heading.
Level 0 is never written in the notebooks — it comes from `lecture.yml` and is
injected as a LaTeX `\chapter`, which is what makes the numbering below work.

Equations, figures and tables are numbered **lecture.part.index**:

```
Figure 1.2.1     first figure in part 2 of lecture 1
Table  2.1.3     third table in part 1 of lecture 2
(1.1.1)          first equation in part 1 of lecture 1
```

This is `\numberwithin{…}{section}` in `partials/preamble.tex`.

The table of contents lists down to level 3 (`toc-depth: 3`). If you would
rather not *number* level-3 headings, set `\setcounter{secnumdepth}{2}` in
`preamble.tex` — the ToC depth is independent of it.

---

## Writing a lecture

### A new lecture

1. `mkdir -p Lectures/Lecture03/figures Lectures/Lecture03/data`
2. Copy a `lecture.yml` and edit `number`, `title`, `date`, `artwork`.
3. Add `Part_L3P1.ipynb`, `Part_L3P2.ipynb`, …
4. `pixi run lecture 3`

Lecture folders must match `Lecture\d+`; part notebooks must match
`Part_L<lecture>P<part>.ipynb`. Both are discovered and sorted automatically —
there is no list to keep in sync.

### The notebook setup cell

Every notebook starts with a setup cell tagged `hide-cell`. It makes the
notebook run identically in JupyterLab, in a per-lecture render (working
directory = the lecture folder) and in the course render (working directory =
the project root):

```python
import os, sys
from pathlib import Path
if "COURSE_LECTURE_DIR" not in os.environ:
    os.environ["COURSE_LECTURE_DIR"] = str(Path.cwd())
    sys.path.insert(0, str(Path.cwd().parents[1] / "scripts"))

from courselib import data_path, figure_path
```

Then always reach for data through the helpers, never with a bare relative
path:

```python
df = pd.read_csv(data_path("transmission.csv"))     # Lectures/LectureNN/data/…
```

Markdown image links stay relative (`figures/beamline.png`); the build script
rewrites them where necessary.

### Cell tags

Jupyter cell tags are translated to Quarto cell options:

| Tag | Effect |
|---|---|
| `hide-input` | `#| echo: false` |
| `hide-output` | `#| output: false` |
| `hide-cell` / `remove-cell` | `#| include: false` |
| `fragment` | output appears on click |

Anything written directly as a `#|` comment in the cell is passed through
untouched, so the full Quarto cell-option vocabulary is available
(`#| label:`, `#| fig-cap:`, `#| code-fold: true`, …).

### Cross-references and citations

Standard Quarto syntax works in both targets:

```markdown
$$ I(d) = I_0 e^{-\Sigma d} $$ {#eq-beer}

![Beamline layout.](figures/beamline.png){#fig-beamline width=85%}

As shown in @fig-beamline and derived from @eq-beer [@kaestner2011].
```

A `# References` section is appended automatically to every document.

---

## Styling

### Slides

`_extensions/ethpsi/ethpsi-slides.scss`. The deck is 1600×900 and reveal's own
`margin` is **0**, so every length in the theme is in deck pixels and nothing
is inset twice. Four variables control the whole layout:

| Variable | Default | Meaning |
|---|---|---|
| `--ethpsi-inset` | `64px` | left/right inset, shared by chrome and content |
| `--ethpsi-band` | `32px` | slide edge → logo |
| `--ethpsi-logo-h` | `44px` | logo height |
| `--ethpsi-gap` | `26px` | logo → content |

Slides carry the padding; the chrome is positioned against the slide's
*padding box*. That is precisely what makes the ETH logo and the slide title
share one left edge — at 64px — regardless of window size or aspect ratio.
Change `--ethpsi-inset` and the logo, the title, the footer and the right-hand
margin all move together.

`_slide-chrome.html` (generated per lecture) holds the two logos, the footer
and the slide number, and a short script **clones it into every slide**. This
is deliberate rather than pinning it to the viewport: reveal.js scales the
deck, so viewport-fixed chrome only lines up with slide content when the
window happens to be exactly 16:9. Cloning also means every page of the
printed PDF carries its own logos.

Deck geometry is 1600×900; change `width`/`height` in `_extension.yml` and the
matching constants in `scripts/slides_to_pdf.py` together.

### PDF notes

- `partials/before-body.tex` — title page (ETH logo top-left, PSI top-right,
  artwork on the right, course title / lecture title / author / date on the
  left) and the table of contents.
- `partials/preamble.tex` — colours, numbering, `titlesec` heading styles,
  `fancyhdr` running head and page numbers.

### Self-contained output

The slides render with `embed-resources: true`, and the logos and title
artwork are inlined as base64 data URIs by `build.py`. The deck is therefore a
single HTML file you can mail, put on a USB stick or open from anywhere, and
nothing depends on Quarto's resource copying — which does not reliably follow
images referenced from a raw HTML include or a template partial.

If you would rather have a smaller file with a `_files/` sidecar, set
`embed-resources: false` in `_extension.yml`.

### Replacing the placeholder branding

`assets/logos/*` and `assets/artwork/*` are **generated placeholders**. Drop in
the official ETH and PSI files, keeping the same names, and keep an SVG plus a
PNG or PDF of each. Since the logos are inlined, keep them small — a vector SVG
of a few kB is ideal. Nothing else needs to change.

If your PSI logo is much wider than the placeholder, adjust `--ethpsi-logo-h`
so the two logos look optically balanced.

---

## Control files

| File | Scope | Purpose |
|---|---|---|
| `pixi.toml` | project | dependencies and every build task |
| `course.yml` | course | title, author, date, bibliography, logos, course artwork |
| `Lectures/*/lecture.yml` | lecture | number, title, subtitle, date, artwork, author override |
| `_quarto.yml` | project | output directory, freeze, crossref labels, resources |
| `_extensions/ethpsi/_extension.yml` | formats | every revealjs and PDF format option |
| `.gitignore` | repo | keeps generated `.qmd` and `_output/` out of version control |

Precedence is `lecture.yml` → `course.yml` for metadata, and front matter →
`_extension.yml` → `_quarto.yml` for format options.

---

## Troubleshooting

**Missing LaTeX package.** Quarto installs into TinyTeX on demand; if it
cannot, run `quarto install tinytex` again or install the package with
`tlmgr install <name>`.

**Slides PDF is blank or clipped.** `scripts/slides_to_pdf.py` waits three
seconds after load; increase it for decks with heavy plots. The Node
alternative also works:
`decktape reveal "file:///abs/path/slides.html" out.pdf -s 1600x900`.

**A figure is missing from the course PDF only.** The path was probably
absolute or built at runtime, so it escaped rewriting. Use `figure_path()` or
a relative link.

**Stale output.** `pixi run clean` removes the generated sources, `_output/`,
`.quarto/` and `_freeze/`.

**The table of contents is empty.** The ToC is written into the document body
by `build.py` (see `TOC_BLOCK`), and the format sets `toc: false` so Quarto
does not emit a second one. Overriding `before-body.tex` removes Quarto's own
ToC hook, so do not re-enable `toc: true` expecting the stock behaviour — you
would get an empty page instead. If you add your own front matter before the
ToC, keep `\tableofcontents` in the body.

**Logos or artwork missing from the slides.** Check the assemble step for
`! missing asset` warnings — `build.py` reports any path in `course.yml` or
`lecture.yml` it could not resolve instead of failing silently. Assets are
inlined, so a working deck never references them by path.

**Slide titles do not line up with the ETH logo.** Something reintroduced a
second inset. Check that `margin: 0` is still set for revealjs in
`_extension.yml`, and that no rule adds `padding-left` or a negative
`margin-left` to `h2` on top of the section padding.
