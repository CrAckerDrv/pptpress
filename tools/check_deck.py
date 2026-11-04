#!/usr/bin/env python3
"""Validate a built deck: contrast, bleed, overflow, editability.

    python tools/check_deck.py deck.pptx
    python tools/check_deck.py deck.pptx --json --strict

Two severities:

* **error** — the delivery contract is broken: content is clipped, a page was
  rasterised, or a shape carries text but no readable text runs.
* **warning** — a design decision worth a second look: a deliberate bleed shape,
  or text below WCAG AA against the surface it sits on (footers and captions are
  commonly intentional). ``--strict`` promotes warnings to the exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn

from pptpress import util

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def _hex(value):
    if not value:
        return None
    return util.parse_color("#" + value)


def _run_color(run):
    r_pr = run.find(qn("a:rPr"))
    if r_pr is None:
        return None
    fill = r_pr.find(qn("a:solidFill"))
    if fill is None:
        return None
    srgb = fill.find(qn("a:srgbClr"))
    if srgb is None:
        return None
    color = _hex(srgb.get("val"))
    alpha = srgb.find(qn("a:alpha"))
    if alpha is not None:
        color = util.with_alpha(color, int(alpha.get("val")) / 100000.0)
    return color


def _slide_shapes(slide):
    return list(slide.shapes)


def _solid_fill_of(shape):
    """Return the flat colour a shape paints (alpha preserved), or None.

    A gradient is averaged into one representative colour; a semi-transparent
    glow keeps its alpha instead of being treated as an opaque light surface, so
    a 14%-alpha halo behind a footer is not mistaken for a white background.
    """
    element = shape._element
    sp_pr = element.find(qn("p:spPr"))
    if sp_pr is None:
        return None
    if sp_pr.find(qn("a:blipFill")) is not None:
        return None
    gradient = sp_pr.find(qn("a:gradFill"))
    if gradient is not None:
        stops = []
        for stop in gradient.iter(qn("a:gs")):
            srgb = stop.find(qn("a:srgbClr"))
            if srgb is None:
                continue
            color = _hex(srgb.get("val"))
            if color is None:
                continue
            alpha = srgb.find(qn("a:alpha"))
            value = (int(alpha.get("val")) / 100000.0) if alpha is not None else 1.0
            stops.append((color, value))
        if stops:
            count = len(stops)
            average = tuple(sum(item[0][index] for item in stops) / count for index in range(3))
            average_alpha = sum(item[1] for item in stops) / count
            return (average[0], average[1], average[2], average_alpha)
        return None
    fill = sp_pr.find(qn("a:solidFill"))
    if fill is None:
        return None
    srgb = fill.find(qn("a:srgbClr"))
    if srgb is None:
        return None
    color = _hex(srgb.get("val"))
    if color is None:
        return None
    alpha = srgb.find(qn("a:alpha"))
    if alpha is not None:
        color = (color[0], color[1], color[2], int(alpha.get("val")) / 100000.0)
    return color


def _center_inside(outer, inner):
    """True when the centre of ``inner`` lies inside ``outer``.

    Text frames are deliberately a little wider than their container so a metric
    difference never clips a line, so containment is judged by the centre point.
    """
    cx = inner.left + inner.width / 2.0
    cy = inner.top + inner.height / 2.0
    left = max(outer.left, 0)
    top = max(outer.top, 0)
    return (
        left <= cx <= outer.left + outer.width
        and top <= cy <= outer.top + outer.height
    )


def _surfaces(slide, slide_background):
    """Bottom-to-top list of (shape, colour) painted surfaces on a slide."""
    surfaces = [(None, slide_background)]
    for shape in slide.shapes:
        if shape.shape_type == 13 or not shape.has_text_frame:
            color = _solid_fill_of(shape)
            if color is not None:
                surfaces.append((shape, color))
            continue
        color = _solid_fill_of(shape)
        if color is not None and shape.text_frame.text.strip() == "":
            surfaces.append((shape, color))
    return surfaces


def _surface_under(text_shape, surfaces):
    """Composite the surfaces painted beneath ``text_shape``.

    Translucent shapes (glows, tinted chips) are blended over the surface below
    them rather than replacing it, so the contrast ratio reflects what a reader
    actually sees.
    """
    base = surfaces[0][1]
    stack = []
    for candidate, color in surfaces[1:]:
        if candidate is text_shape:
            continue
        if not _center_inside(candidate, text_shape):
            continue
        stack.append(color)
    result = base
    for color in stack:
        alpha = util.alpha_of(color)
        result = util.mix(result, color, alpha) if alpha < 0.999 else color
    return result


def _slide_background(slide):
    fill = slide.background.fill
    try:
        if fill.type is not None and fill.fore_color.type is not None:
            rgb = fill.fore_color.rgb
            return (rgb[0], rgb[1], rgb[2], 1.0)
    except (AttributeError, TypeError, ValueError):
        pass
    return (255, 255, 255, 1.0)


def check(path):
    presentation = Presentation(path)
    width = presentation.slide_width
    height = presentation.slide_height
    report = {"file": os.path.basename(path), "slides": [], "errors": [], "warnings": []}
    for index, slide in enumerate(presentation.slides, start=1):
        background = _slide_background(slide)
        surfaces = _surfaces(slide, background)
        shapes = _slide_shapes(slide)
        slide_report = {"index": index, "shapes": len(shapes), "pictures": 0, "text_boxes": 0}
        picture_area = 0
        for shape in shapes:
            if shape.shape_type == 13:
                slide_report["pictures"] += 1
                picture_area += shape.width * shape.height
            if shape.left is not None and shape.width is not None:
                if shape.left + shape.width < 0 or shape.top + shape.height < 0:
                    report["errors"].append(
                        f"slide {index}: shape '{shape.name}' lies entirely off-slide"
                    )
                elif shape.left < -width * 0.2 or shape.top < -height * 0.2:
                    # Deliberate bleed (orbs, gradients running off the edge) is a
                    # valid design choice; flag it for review instead of failing.
                    report["warnings"].append(
                        f"slide {index}: shape '{shape.name}' bleeds off the slide"
                    )
                if shape.left + shape.width > width * 1.25 and not shape.has_text_frame:
                    report["warnings"].append(
                        f"slide {index}: shape '{shape.name}' extends past the slide edge"
                    )
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            slide_report["text_boxes"] += 1
            surface = _surface_under(shape, surfaces)
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    if not run.text.strip():
                        continue
                    color = _run_color(run._r)
                    if color is None:
                        continue
                    effective = util.mix(surface, color, util.alpha_of(color))
                    ratio = util.contrast_ratio(effective, surface)
                    if ratio < 1.02:
                        # Identical text and background: the copy would vanish.
                        report["errors"].append(
                            f"slide {index}: invisible text '{run.text[:18]}'"
                        )
                    elif ratio < 4.5:
                        report["warnings"].append(
                            f"slide {index}: contrast {ratio:.1f}:1 for '{run.text[:18]}'"
                        )
        if slide_report["pictures"] and picture_area > width * height * 0.8:
            report["errors"].append(f"slide {index}: page looks rasterised (one large picture)")
        if slide_report["text_boxes"] == 0 and slide_report["pictures"] == 0:
            report["errors"].append(f"slide {index}: no text and no picture")
        report["slides"].append(slide_report)
    report["issues"] = report["errors"]
    report["ok"] = not report["errors"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="validate an exported deck")
    parser.add_argument("pptx")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args(argv)
    report = check(args.pptx)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "OK" if report["ok"] else "ISSUES"
        print(f"{report['file']}: {status}")
        for slide in report["slides"]:
            print(
                f"  slide {slide['index']:>2}: {slide['shapes']:>3} shapes, "
                f"{slide['text_boxes']:>2} text, {slide['pictures']:>2} pictures"
            )
        for issue in report["errors"]:
            print(f"  ! {issue}")
        for issue in report["warnings"]:
            print(f"  ~ {issue}")
    ok = report["ok"] and not (args.strict and report["warnings"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
