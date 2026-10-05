#!/usr/bin/env python3
"""
Assemble and render the lecture suite.

One source (Jupyter notebooks) -> three targets:

  slides      revealjs slides for one lecture
  notes       PDF lecture notes for one lecture
  course      one PDF containing all lectures
  slides-pdf  the revealjs slides printed to PDF

The script concatenates all ``Part_L*P*.ipynb`` of a lecture into a single
generated ``.qmd`` file.  Generated files are written next to their sources
(so that ``figures/`` and ``data/`` stay resolvable) and are git-ignored.

Usage
-----
    python scripts/build.py assemble  [Lecture01 ...]
    python scripts/build.py slides    [Lecture01 ...]
    python scripts/build.py notes     [Lecture01 ...]
    python scripts/build.py lecture   [Lecture01 ...]   # slides + notes
    python scripts/build.py slides-pdf[Lecture01 ...]
    python scripts/build.py course
    python scripts/build.py all
    python scripts/build.py clean
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LECTURE_ROOT = ROOT / "Lectures"
OUTPUT_DIR = ROOT / "_output"

SLIDES_SUFFIX = "-slides.qmd"
CHROME_FILE = "_slide-chrome.html"
NOTES_SUFFIX = "-notes.qmd"
COURSE_FILE = ROOT / "course-notes.qmd"

# ---------------------------------------------------------------- helpers


def read_yaml(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing configuration file: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def course_config() -> dict:
    return read_yaml(ROOT / "course.yml")


def all_lecture_dirs() -> list[Path]:
    if not LECTURE_ROOT.is_dir():
        raise SystemExit(f"no Lectures/ directory found under {ROOT}")
    dirs = [
        d
        for d in LECTURE_ROOT.iterdir()
        if d.is_dir() and re.fullmatch(r"Lecture\d+", d.name)
    ]
    return sorted(dirs, key=lambda d: d.name)


def select_lectures(names: list[str] | None) -> list[Path]:
    available = all_lecture_dirs()
    if not names:
        return available
    by_name = {d.name.lower(): d for d in available}
    chosen = []
    for raw in names:
        key = raw.strip("/").split("/")[-1].lower()
        if key.isdigit():
            key = f"lecture{int(key):02d}"
        if key not in by_name:
            raise SystemExit(
                f"unknown lecture {raw!r}; available: "
                + ", ".join(d.name for d in available)
            )
        chosen.append(by_name[key])
    return chosen


def lecture_config(ldir: Path) -> dict:
    cfg = read_yaml(ldir / "lecture.yml")
    cfg.setdefault("number", int(re.search(r"\d+", ldir.name).group()))
    cfg.setdefault("title", ldir.name)
    return cfg


def parts_of(ldir: Path) -> list[Path]:
    parts = sorted(ldir.glob("Part_L*P*.ipynb"), key=_part_sort_key)
    if not parts:
        raise SystemExit(f"no Part_L*P*.ipynb notebooks found in {ldir}")
    return parts


def _part_sort_key(path: Path):
    m = re.search(r"Part_L(\d+)P(\d+)", path.stem)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def relpath(target: Path, start: Path) -> str:
    """POSIX-style relative path, usable in YAML, LaTeX and HTML."""
    return Path(os.path.relpath(target, start)).as_posix()


MIME = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def data_uri(path: Path) -> str:
    """Inline an image so it cannot be lost by resource copying.

    Logos and title artwork are referenced from a raw HTML include and from a
    template partial, neither of which Quarto's resource scanner reliably
    follows.  Embedding them removes that failure mode entirely.
    """
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def smallest_variant(path: Path) -> Path:
    """Pick the lightest available variant of an asset for inlining."""
    candidates = [
        sibling
        for ext in (".svg", ".png", ".jpg", ".jpeg", ".webp")
        if (sibling := path.with_suffix(ext)).exists()
    ]
    return min(candidates, key=lambda p: p.stat().st_size) if candidates else path


def swap_suffix_for_latex(path: Path) -> Path:
    """LaTeX cannot include SVG: prefer a PNG/PDF sibling when present."""
    if path.suffix.lower() != ".svg":
        return path
    for ext in (".pdf", ".png"):
        candidate = path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return path


# ------------------------------------------------- notebook -> markdown

_MD_IMAGE = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)")
_HTML_SRC = re.compile(r"""(<(?:img|source|video)\b[^>]*?\bsrc\s*=\s*["'])([^"']+)""")
_EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|/|#|\{)")


def rewrite_resource_paths(text: str, prefix: str) -> str:
    """Prefix relative resource references (used for the whole-course build)."""
    if not prefix:
        return text

    def fix(match: re.Match) -> str:
        head, url = match.group(1), match.group(2)
        if _EXTERNAL.match(url):
            return match.group(0)
        return f"{head}{prefix}/{url}"

    text = _MD_IMAGE.sub(fix, text)
    text = _HTML_SRC.sub(fix, text)
    return text


def strip_front_matter(text: str) -> str:
    """Drop a YAML header if a notebook carries one in a raw cell."""
    stripped = text.lstrip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return text


def notebook_to_markdown(nb_path: Path, prefix: str) -> str:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    chunks: list[str] = []

    for cell in nb.get("cells", []):
        source = "".join(cell.get("source", [])).rstrip()
        if not source.strip():
            continue
        ctype = cell.get("cell_type")

        if ctype == "markdown":
            chunks.append(rewrite_resource_paths(source, prefix))

        elif ctype == "code":
            language = (
                nb.get("metadata", {})
                .get("kernelspec", {})
                .get("language", "python")
            )
            options = cell_options(cell)
            body = "\n".join(options + [source]) if options else source
            chunks.append(f"```{{{language}}}\n{body}\n```")

        elif ctype == "raw":
            text = strip_front_matter(source)
            if text.strip():
                chunks.append(rewrite_resource_paths(text, prefix))

    return "\n\n".join(chunks) + "\n"


#: Jupyter cell tags mapped to Quarto cell options.
TAG_OPTIONS = {
    "hide-input": "#| echo: false",
    "hide-output": "#| output: false",
    "hide-cell": "#| include: false",
    "remove-cell": "#| include: false",
    "fragment": "#| output-location: fragment",
}


def cell_options(cell: dict) -> list[str]:
    source = "".join(cell.get("source", []))
    opts: list[str] = []
    for tag in cell.get("metadata", {}).get("tags", []):
        option = TAG_OPTIONS.get(tag)
        if option and option not in source:
            opts.append(option)
    return opts


# ------------------------------------------------------- qmd assembly


def preamble_block(ldir: Path) -> str:
    """Hidden cell that tells the notebooks where their lecture folder is."""
    return (
        "```{python}\n"
        "#| include: false\n"
        "#| echo: false\n"
        "import os, sys\n"
        f'os.environ["COURSE_LECTURE_DIR"] = r"{ldir}"\n'
        f'sys.path.insert(0, r"{ROOT / "scripts"}")\n'
        "```"
    )


def lecture_body(ldir: Path, prefix: str = "", with_chapter: bool = False) -> str:
    cfg = lecture_config(ldir)
    blocks = [preamble_block(ldir)]

    if with_chapter:
        # Level 0: the lecture becomes a numbered LaTeX chapter, which also
        # drives the <lecture>.<part>.<n> numbering of equations/figures/tables.
        blocks.append(
            "```{=latex}\n"
            f"\\setcounter{{chapter}}{{{int(cfg['number']) - 1}}}\n"
            f"\\chapter{{{cfg['title']}}}\n"
            "```"
        )

    for nb in parts_of(ldir):
        blocks.append(notebook_to_markdown(nb, prefix))

    return "\n\n".join(blocks)


def references_block(heading_level: int = 1) -> str:
    hashes = "#" * heading_level
    return f"{hashes} References {{.unnumbered}}\n\n::: {{#refs}}\n:::\n"


def front_matter(data: dict) -> str:
    # width must stay huge: folding would insert newlines into data URIs.
    dumped = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, width=10**6
    )
    return f"---\n{dumped}---\n\n"


def asset_map(course: dict, lec: dict) -> dict:
    """The three branding assets, as absolute paths."""
    mapping = {
        "psi-logo": course.get("psi-logo"),
        "artwork": lec.get("artwork") or course.get("artwork"),
    }
    return {k: (ROOT / v).resolve() for k, v in mapping.items() if v}


def latex_assets(course: dict, lec: dict, base: Path) -> dict:
    """Asset paths relative to *base*, in a format pdfLaTeX can \\includegraphics."""
    out = {}
    for key, path in asset_map(course, lec).items():
        path = swap_suffix_for_latex(path)
        if path.exists():
            out[key] = relpath(path, base)
        else:
            print(f"  ! missing asset for {key}: {path}", file=sys.stderr)
    return out


def slide_assets(course: dict, lec: dict) -> dict:
    """Assets inlined as data URIs, so nothing depends on resource copying."""
    out = {}
    for key, path in asset_map(course, lec).items():
        path = smallest_variant(path)
        if path.exists():
            out[key] = data_uri(path)
        else:
            print(f"  ! missing asset for {key}: {path}", file=sys.stderr)
    return out


def write_slides(ldir: Path) -> Path:
    course = course_config()
    lec = lecture_config(ldir)
    target = ldir / f"{ldir.name}{SLIDES_SUFFIX}"

    footer = (
        f"{course.get('short-title', course.get('title'))} &nbsp;|&nbsp; "
        f"{lec.get('date', course.get('date'))}"
    )
    assets = slide_assets(course, lec)
    write_slide_chrome(ldir, assets, footer)

    fm = {
        "title": lec["title"],
        "subtitle": lec.get("subtitle", f"Lecture {lec['number']}"),
        "author": lec.get("author", course.get("author")),
        "date": lec.get("date", course.get("date")),
        "course-title": course.get("title"),
        "bibliography": relpath(ROOT / course.get("bibliography", "references.bib"), ldir),
        "format": {
            "ethpsi-revealjs": {"include-after-body": [CHROME_FILE]}
        },
    }
    fm.update(assets)

    body = lecture_body(ldir, prefix="", with_chapter=False)
    target.write_text(
        front_matter(fm) + body + "\n\n" + references_block(1), encoding="utf-8"
    )
    return target


def write_notes(ldir: Path) -> Path:
    course = course_config()
    lec = lecture_config(ldir)
    target = ldir / f"{ldir.name}{NOTES_SUFFIX}"

    fm = {
        "title": lec["title"],
        "subtitle": lec.get("subtitle", f"Lecture {lec['number']}"),
        "author": lec.get("author", course.get("author")),
        "date": lec.get("date", course.get("date")),
        "course-title": course.get("title"),
        "bibliography": relpath(ROOT / course.get("bibliography", "references.bib"), ldir),
        "format": {"ethpsi-pdf": {"output-file": f"{ldir.name}-notes.pdf"}},
    }
    fm.update(latex_assets(course, lec, ldir))

    body = lecture_body(ldir, prefix="", with_chapter=True)
    target.write_text(
        front_matter(fm) + TOC_BLOCK + "\n\n" + body + "\n\n" + references_block(1),
        encoding="utf-8",
    )
    return target


def write_course() -> Path:
    course = course_config()
    target = COURSE_FILE

    fm = {
        "title": course.get("title"),
        "subtitle": course.get("subtitle", "Complete lecture notes"),
        "author": course.get("author"),
        "date": course.get("date"),
        "course-title": course.get("title"),
        "bibliography": course.get("bibliography", "references.bib"),
        "format": {"ethpsi-pdf": {"output-file": "course-notes.pdf"}},
    }
    fm.update(latex_assets(course, {}, ROOT))

    bodies = []
    for ldir in all_lecture_dirs():
        prefix = relpath(ldir, ROOT)
        bodies.append(lecture_body(ldir, prefix=prefix, with_chapter=True))

    target.write_text(
        front_matter(fm)
        + TOC_BLOCK
        + "\n\n"
        + "\n\n".join(bodies)
        + "\n\n"
        + references_block(1),
        encoding="utf-8",
    )
    return target


def write_slide_chrome(ldir: Path, assets: dict, footer: str) -> Path:
    """Per-lecture slide chrome: both logos, the footer and the slide number.

    The block is cloned into every slide rather than pinned to the viewport.
    That matters twice over: the chrome then sits in the deck's own coordinate
    system, so the ETH logo and the slide titles stay aligned at any window
    aspect ratio, and every page of the printed PDF carries its own logos.
    """
    psi = assets.get("psi-logo", "")
    html = f"""<div class="ethpsi-chrome ethpsi-chrome-template" aria-hidden="true">
  <img class="ethpsi-logo-psi" src="{psi}" alt="Paul Scherrer Institut">
  <div class="ethpsi-footer">{footer}</div>
  <div class="ethpsi-slide-number"></div>
</div>
<script>
(function () {{
  function decorate(deck) {{
    var template = document.querySelector('.ethpsi-chrome-template');
    if (!template) return;
    var slides = deck.getSlides();
    slides.forEach(function (section, i) {{
      if (section.querySelector(':scope > .ethpsi-chrome')) return;
      var chrome = template.cloneNode(true);
      chrome.classList.remove('ethpsi-chrome-template');
      if (section.id === 'title-slide') {{
        chrome.classList.add('ethpsi-chrome-title');
      }}
      var number = chrome.querySelector('.ethpsi-slide-number');
      if (number) number.textContent = (i + 1) + ' / ' + slides.length;
      section.appendChild(chrome);
    }});
    template.remove();
  }}

  function start() {{
    if (typeof Reveal === 'undefined') return;
    if (Reveal.isReady && Reveal.isReady()) decorate(Reveal);
    else Reveal.on('ready', function () {{ decorate(Reveal); }});
  }}

  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
}})();
</script>
"""
    target = ldir / CHROME_FILE
    target.write_text(html, encoding="utf-8")
    return target


TOC_BLOCK = """```{=latex}
\\cleardoublepage
\\pdfbookmark[0]{\\contentsname}{ethpsi-toc}
\\setcounter{tocdepth}{3}
\\tableofcontents
\\cleardoublepage
```"""


# ------------------------------------------------------------ rendering


def quarto(*args: str) -> None:
    cmd = ["quarto", *args]
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def render_slides(ldir: Path) -> Path:
    src = write_slides(ldir)
    quarto("render", relpath(src, ROOT), "--to", "ethpsi-revealjs")
    return OUTPUT_DIR / relpath(src, ROOT).replace(".qmd", ".html")


def render_notes(ldir: Path) -> Path:
    src = write_notes(ldir)
    quarto("render", relpath(src, ROOT), "--to", "ethpsi-pdf")
    return OUTPUT_DIR / relpath(src, ROOT).replace(".qmd", ".pdf")


def render_course() -> Path:
    src = write_course()
    quarto("render", relpath(src, ROOT), "--to", "ethpsi-pdf")
    return OUTPUT_DIR / "course-notes.pdf"


def render_slides_pdf(ldir: Path) -> Path:
    html = render_slides(ldir)
    pdf = html.with_suffix(".pdf")
    script = ROOT / "scripts" / "slides_to_pdf.py"
    print("+", sys.executable, script.name, html.name, flush=True)
    result = subprocess.run(
        [sys.executable, str(script), str(html), str(pdf)], cwd=ROOT
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return pdf


def clean() -> None:
    removed = []
    for pattern in (
        f"Lectures/*/*{SLIDES_SUFFIX}",
        f"Lectures/*/*{NOTES_SUFFIX}",
        f"Lectures/*/{CHROME_FILE}",
    ):
        for path in ROOT.glob(pattern):
            path.unlink()
            removed.append(path)
    if COURSE_FILE.exists():
        COURSE_FILE.unlink()
        removed.append(COURSE_FILE)
    for folder in (OUTPUT_DIR, ROOT / ".quarto", ROOT / "_freeze"):
        if folder.exists():
            shutil.rmtree(folder)
            removed.append(folder)
    for path in removed:
        print("removed", relpath(path, ROOT))


# ----------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "command",
        choices=[
            "assemble",
            "slides",
            "notes",
            "lecture",
            "slides-pdf",
            "course",
            "all",
            "clean",
        ],
    )
    parser.add_argument(
        "lectures",
        nargs="*",
        help="lecture folders (e.g. Lecture01, or just 1); default: all",
    )
    args = parser.parse_args()

    if args.command == "clean":
        clean()
        return
    if args.command == "course":
        print("->", render_course())
        return

    targets = select_lectures(args.lectures)

    if args.command == "assemble":
        for ldir in targets:
            print("->", write_slides(ldir))
            print("->", write_notes(ldir))
        write_course()
        print("->", COURSE_FILE)
        return

    for ldir in targets:
        if args.command in ("slides", "lecture"):
            print("->", render_slides(ldir))
        if args.command in ("notes", "lecture"):
            print("->", render_notes(ldir))
        if args.command == "slides-pdf":
            print("->", render_slides_pdf(ldir))
        if args.command == "all":
            print("->", render_slides(ldir))
            print("->", render_notes(ldir))

    if args.command == "all":
        print("->", render_course())


if __name__ == "__main__":
    main()
