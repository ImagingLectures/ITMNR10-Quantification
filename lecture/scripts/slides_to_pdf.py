#!/usr/bin/env python3
"""
Print rendered revealjs slides to PDF.

Loads the generated HTML with reveal.js' ``?print-pdf`` query string in a
headless Chromium and prints it at the deck's own aspect ratio.

    python scripts/slides_to_pdf.py <slides.html> [output.pdf]

Requires ``playwright`` plus its Chromium build::

    pixi run setup          # or: playwright install chromium

Alternative, if you prefer the Node toolchain:

    decktape reveal "file:///abs/path/slides.html" slides.pdf -s 1600x900
"""
from __future__ import annotations

import sys
from pathlib import Path

# Must match `width`/`height` in _extensions/ethpsi/_extension.yml
SLIDE_WIDTH_PX = 1600
SLIDE_HEIGHT_PX = 900
PX_PER_INCH = 96


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    html = Path(sys.argv[1]).resolve()
    if not html.exists():
        print(f"slides not found: {html}", file=sys.stderr)
        return 1
    pdf = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else html.with_suffix(".pdf")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright is not installed.\n"
            "  pixi run setup        (installs playwright + chromium)",
            file=sys.stderr,
        )
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--allow-file-access-from-files"])
        page = browser.new_page(
            viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX}
        )
        page.goto(f"{html.as_uri()}?print-pdf", wait_until="networkidle")
        # Give reveal.js time to lay out the print stylesheet and any plots.
        page.wait_for_timeout(3000)
        page.pdf(
            path=str(pdf),
            width=f"{SLIDE_WIDTH_PX / PX_PER_INCH}in",
            height=f"{SLIDE_HEIGHT_PX / PX_PER_INCH}in",
            print_background=True,
            prefer_css_page_size=False,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()

    print(f"wrote {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
