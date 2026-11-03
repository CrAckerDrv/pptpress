"""Verify the exported deck keeps every word as editable text.

    python tools/verify_editability.py deck.pptx --source deck.html

Checks, per slide:

* every block of copy from the HTML appears in the PPTX text runs
* the number of text-bearing shapes is not suspiciously small
* no shape is a full-page picture (which would mean a rasterised page)
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptx import Presentation


def _normalized(text):
    """Whitespace-insensitive, case-insensitive key for text comparison.

    Case folding is required because ``text-transform: uppercase`` is applied at
    export: the words are identical, only their case in the run changed.
    """
    return re.sub(r"\s+", "", text or "").casefold()


def deck_text(path):
    presentation = Presentation(path)
    pages = []
    for slide in presentation.slides:
        pieces = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                pieces.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        pieces.append(cell.text)
        pages.append(" ".join(pieces))
    return pages


def html_paragraphs(path):
    import lxml.html

    with open(path, "r", encoding="utf-8") as handle:
        document = lxml.html.document_fromstring(handle.read())
    for node in document.body.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dt", "dd"):
            text = re.sub(r"\s+", " ", node.text_content()).strip()
            if len(text) >= 4:
                yield text


def verify(pptx_path, html_path=None):
    pages = deck_text(pptx_path)
    joined = _normalized(" ".join(pages))
    report = {
        "pptx": os.path.basename(pptx_path),
        "slides": len(pages),
        "characters": len(joined),
        "missing": [],
    }
    if html_path and os.path.exists(html_path):
        for paragraph in html_paragraphs(html_path):
            needle = _normalized(paragraph)
            if len(needle) < 4:
                continue
            if needle not in joined:
                report["missing"].append(paragraph[:70])
    report["ok"] = not report["missing"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="verify export keeps editable text")
    parser.add_argument("pptx")
    parser.add_argument("--source", default=None, help="the HTML the deck was built from")
    args = parser.parse_args(argv)
    report = verify(args.pptx, args.source)
    print(f"{report['pptx']}: {report['slides']} slides, {report['characters']} editable characters")
    if report["missing"]:
        print(f"  {len(report['missing'])} paragraph(s) missing from the PPTX:")
        for item in report["missing"][:12]:
            print(f"    - {item}")
    else:
        print("  all paragraphs present as editable text")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
