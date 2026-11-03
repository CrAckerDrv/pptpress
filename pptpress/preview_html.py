"""Standalone HTML preview page (slide thumbnails + optional slide show mode)."""

from __future__ import annotations

import html
import os


def _slide_markup(slide, base_dir):
    from .preview import render_slide

    svg, issues = render_slide(slide, base_dir)
    return svg, issues


def build_html_page(slides, base_dir="", title="PPT Press preview", embed_svg=True, svg_dir=None):
    cards = []
    for slide in slides:
        if embed_svg:
            svg, issues = _slide_markup(slide, base_dir)
        else:
            svg, issues = "", []
        note = html.escape(slide.speaker_notes or "").replace("\n", "<br>")
        issue_markup = ""
        if issues:
            issue_markup = '<div class="issues">' + "".join(
                f"<span>{html.escape(item)}</span>" for item in issues
            ) + "</div>"
        cards.append(
            f'<section class="card" data-index="{slide.index + 1}">'
            f'<div class="frame">{svg}</div>'
            f'<div class="meta"><b>{slide.index + 1:02d}</b>'
            f'<span>{html.escape(slide.title or "")}</span>{issue_markup}</div>'
            + (f'<div class="notes">{note}</div>' if note else "")
            + "</section>"
        )
    notes = "\n".join(cards)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #0b0c10; color: #e8eaed;
         font: 14px/1.5 Inter, 'Segoe UI', 'Microsoft YaHei', system-ui, sans-serif; }}
  header {{ position: sticky; top: 0; padding: 14px 24px; background: #14161c;
            border-bottom: 1px solid #23262f; display: flex; gap: 16px; align-items: baseline; z-index: 5; }}
  header h1 {{ font-size: 15px; margin: 0; letter-spacing: .04em; text-transform: uppercase; }}
  header span {{ color: #8b93a7; font-size: 12px; }}
  main {{ display: grid; gap: 22px; padding: 24px; max-width: 1080px; margin: 0 auto; }}
  .card {{ border-radius: 14px; overflow: hidden; background: #14161c; border: 1px solid #23262f; }}
  .frame {{ background: #fff; }}
  .frame svg {{ display: block; width: 100%; height: auto; }}
  .meta {{ display: flex; gap: 10px; align-items: center; padding: 8px 14px; border-top: 1px solid #23262f;
           color: #c3c9d6; font-size: 12px; }}
  .meta b {{ color: #6ee7b7; font-variant-numeric: tabular-nums; }}
  .issues {{ margin-left: auto; display: flex; gap: 6px; }}
  .issues span {{ background: #3a2418; color: #f6c177; padding: 2px 8px; border-radius: 999px; font-size: 11px; }}
  .notes {{ padding: 10px 14px 14px; color: #97a0b2; font-size: 12px; border-top: 1px dashed #23262f; }}
</style>
</head>
<body>
<header><h1>{html.escape(title)}</h1><span>{len(slides)} slides · editable PPTX preview</span></header>
<main>{notes}</main>
</body>
</html>
"""
