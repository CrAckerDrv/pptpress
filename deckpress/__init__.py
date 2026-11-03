"""Deckpress — HTML-first, editable-PPTX presentation engine.

The package turns a hand-authored HTML deck into a fully editable PowerPoint
file: every heading, paragraph, card, image and table becomes a native
PowerPoint object (no rasterised pages, no locked template).

Public entry points
-------------------
build_file(html_path, out_pptx, theme=None)   -> BuildResult
preview_file(html_path, out_dir, theme=None)  -> PreviewResult
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["build_file", "preview_file", "__version__"]


def build_file(html_path, out_pptx, theme=None, **kw):
    from .pipeline import BuildResult, build

    return build(html_path, out_pptx, theme=theme, **kw)


def preview_file(html_path, out_dir, theme=None, **kw):
    from .pipeline import preview

    return preview(html_path, out_dir, theme=theme, **kw)
