"""Render a PPTX to PNG images for visual verification.

LibreOffice's PNG filter only exports the first slide, so each page is rendered
by saving a one-slide copy of the deck and converting that. No PyMuPDF, no
network, no extra dependency: python-pptx + LibreOffice is enough.

    python tools/render_pptx.py deck.pptx out/rendered
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile


def find_soffice():
    candidates = [
        os.environ.get("SOFFICE"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return shutil.which("soffice")


def _convert(soffice, source, out_dir, target_format):
    profile = os.path.join(tempfile.gettempdir(), "deckpress-lo-profile")
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--nofirststartwizard",
        f"-env:UserInstallation=file:///{profile.replace(os.sep, '/')}",
        "--convert-to",
        target_format,
        "--outdir",
        out_dir,
        os.path.abspath(source),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def _drop_all_but_first(pptx_path, target_path):
    """Copy ``pptx_path`` to ``target_path`` keeping only slide 1."""
    from pptx import Presentation

    presentation = Presentation(pptx_path)
    slide_ids = presentation.slides._sldIdLst
    entries = list(slide_ids)
    for entry in entries[1:]:
        rel_id = entry.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        presentation.part.drop_rel(rel_id)
        slide_ids.remove(entry)
    presentation.save(target_path)
    return target_path


def _slide_count(pptx_path):
    from pptx import Presentation

    return len(Presentation(pptx_path).slides)


def render_pptx(pptx_path, out_dir, dpi=96):
    """Return PNG paths, one per slide."""
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice (soffice) not found; set $env:SOFFICE")
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="deckpress-render-")
    total = _slide_count(pptx_path)
    images = []
    for index in range(1, total + 1):
        single = os.path.join(work, f"page-{index:02d}.pptx")
        if index == 1:
            _drop_all_but_first(pptx_path, single)
        else:
            _keep_only(pptx_path, single, index)
        _convert(soffice, single, work, "png")
        produced = os.path.join(work, f"page-{index:02d}.png")
        if not os.path.exists(produced):
            continue
        target = os.path.join(out_dir, f"page-{index:02d}.png")
        shutil.copyfile(produced, target)
        images.append(target)
    return images


def _keep_only(pptx_path, target_path, keep_index):
    """Keep a single slide (1-based) in a copy of the deck."""
    from pptx import Presentation

    presentation = Presentation(pptx_path)
    slide_ids = presentation.slides._sldIdLst
    entries = list(slide_ids)
    for position, entry in enumerate(entries):
        if position == keep_index - 1:
            continue
        rel_id = entry.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        presentation.part.drop_rel(rel_id)
        slide_ids.remove(entry)
    presentation.save(target_path)
    return target_path


if __name__ == "__main__":
    target = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "rendered"
    for path in render_pptx(target, out):
        print(path)
