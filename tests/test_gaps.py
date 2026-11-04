"""Regression tests for the CSS gaps fixed in 1.1.0.

Each test is a minimal deck; assertions read the laid-out geometry or the emitted
DrawingML, never the implementation. A bug that comes back breaks a test here.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from pptpress import pipeline, values

HEAD = """<!doctype html><html data-size="16:9"><head><meta charset="utf-8"><style>
body{margin:0}
.slide{width:1280px;height:720px;padding:40px;background:#fff;
font-family:Inter,'Segoe UI',sans-serif}
%s</style></head><body><section class="slide">%s</section></body></html>"""


def build(css: str, body: str):
    """Build a one-slide deck; return (slide_xml, layout_boxes_by_class, all_boxes)."""
    directory = tempfile.mkdtemp()
    source = os.path.join(directory, "case.html")
    target = os.path.join(directory, "case.pptx")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write(HEAD % (css, body))
    result = pipeline.build(source, target)
    assert result.ok, result.issues
    assert not [issue for issue in result.issues if "overflow" in issue], result.issues
    with zipfile.ZipFile(target) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    _document, slides, _engine, _size, _timings = pipeline.layout_document(source)
    boxes = {}
    for box in slides[0].walk():
        node = getattr(box, "node", None)
        for name in sorted(getattr(node, "class_set", set()) or ()):
            boxes.setdefault(name, []).append(box)
    return xml, boxes


def all_runs(source: str):
    """Every laid-out run in the deck, in order: ``[(text, style), …]``."""
    _document, slides, _engine, _size, _timings = pipeline.layout_document(source)
    runs = []
    for box in slides[0].walk():
        for line in box.lines or []:
            for text, style, _width in line.runs:
                if text.strip():
                    runs.append((text, style))
    return runs


def write_case(css: str, body: str) -> str:
    directory = tempfile.mkdtemp()
    source = os.path.join(directory, "case.html")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write(HEAD % (css, body))
    return source


# --------------------------------------------------------------- P0: crashes
@pytest.mark.parametrize("expression", [
    "repeat(auto-fit,minmax(200px,1fr))",
    "repeat(auto-fill,minmax(180px,1fr))",
    "repeat(2,minmax(100px,1fr))",
    "minmax(200px,1fr) 1fr",
    "200px minmax(100px,1fr)",
    "repeat(auto-fit,minmax(min-content,1fr))",
])
def test_grid_minmax_never_crashes(expression):
    tracks = values.parse_track_list(expression, size=900.0, gap=10.0)
    assert tracks, expression
    build(f".g{{display:grid;grid-template-columns:{expression}}}",
          '<div class="g"><div>a</div><div>b</div><div>c</div></div>')


def test_auto_fit_column_count_uses_the_minimum():
    # 900pt box, 10pt gap, 200px minimum = 150pt floor -> 5 columns.
    tracks = values.parse_track_list("repeat(auto-fit,minmax(200px,1fr))", size=900.0, gap=10.0)
    assert len(tracks) == 5
    assert tracks[0] == pytest.approx((900.0 - 10.0 * 4) / 5.0, rel=1e-3)


# ------------------------------------------------- P0: semantic tag defaults
@pytest.mark.parametrize("tag,size,weight", [
    ("h1", 32.0, 700), ("h2", 24.0, 700), ("h3", 19.0, 600), ("h6", 12.0, 600),
])
def test_heading_scale(tag, size, weight):
    runs = all_runs(write_case("", f"<{tag}>{tag} text</{tag}>"))
    assert runs, f"no runs for <{tag}>"
    _text, style = runs[0]
    assert style.font_size == pytest.approx(size, abs=1.0), (tag, style.font_size)
    assert style.font_weight == weight, (tag, style.font_weight)


def _all_boxes(boxes):
    seen = []
    for group in boxes.values():
        for box in group:
            if box not in seen:
                seen.append(box)
    return seen


@pytest.mark.parametrize("markup,expect_bold,expect_italic", [
    ("<p>plain <b>B</b></p>", True, False),
    ("<p>plain <strong>S</strong></p>", True, False),
    ("<p>plain <i>I</i></p>", False, True),
])
def test_inline_semantics(markup, expect_bold, expect_italic):
    runs = [(text.strip(), style) for text, style in all_runs(write_case("", markup))
            if text.strip() and text.strip() != "plain"]
    assert runs, "no run for the emphasised fragment"
    style = runs[0][1]
    assert (style.font_weight >= 600) is expect_bold, style.font_weight
    assert (style.font_style == "italic") is expect_italic, style.font_style


def test_author_css_still_wins_over_ua():
    xml, _boxes = build("h1{font-size:52px;font-weight:400}", "<h1>Custom</h1>")
    assert 'b="1"' not in xml
    assert 'sz="3900"' in xml


def test_inline_style_wins_over_ua():
    xml, _boxes = build("", '<p style="font-weight:300">Light</p>')
    assert 'b="1"' not in xml


# ------------------------------------------------------------ P1: text paint
def test_line_through_is_native():
    xml, _boxes = build(".s{text-decoration:line-through;font-size:20px}",
                        '<p class="s">struck</p>')
    assert 'strike="sngStrike"' in xml


def test_sub_sup_use_baseline_shift():
    xml, _boxes = build("", "<p>H<sub>2</sub>O and x<sup>2</sup></p>")
    assert "baseline" in xml


def test_ordered_list_uses_native_numbering():
    xml, _boxes = build("", '<ol start="5"><li>five</li><li>six</li></ol>')
    assert 'type="arabicPeriod"' in xml
    assert 'startAt="5"' in xml


def test_roman_numbering_scheme():
    xml, _boxes = build("", '<ol style="list-style-type:upper-roman"><li>x</li></ol>')
    assert 'type="romanUcPeriod"' in xml


# --------------------------------------------------------------- P1: layout
def test_grid_column_span():
    _xml, boxes = build(
        ".g{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}"
        ".w{grid-column:span 2;height:20px}.b{height:20px}",
        '<div class="g"><div class="w"></div><div class="b"></div><div class="b"></div></div>',
    )
    assert boxes["w"][0].width > boxes["b"][0].width * 1.8


def test_grid_explicit_placement():
    _xml, boxes = build(
        ".g{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}"
        ".a{grid-column:2;height:20px}.b{height:20px}",
        '<div class="g"><div class="b"></div><div class="a"></div></div>',
    )
    assert boxes["a"][0].x > boxes["b"][0].x


def test_grid_align_content_centers_rows():
    _xml, boxes = build(
        ".g{display:grid;grid-template-columns:1fr;grid-template-rows:40px;"
        "height:300px;align-content:center}.b{height:20px}",
        '<div class="g"><div class="b"></div></div>',
    )
    assert boxes["b"][0].y - boxes["g"][0].y > 40


def test_percentage_height_uses_the_parent_not_the_canvas():
    _xml, boxes = build(
        ".p{height:300px}.c{height:50%}",
        '<div class="p"><div class="c"></div></div>',
    )
    assert boxes["c"][0].height == pytest.approx(112.5, abs=4.0)


def test_aspect_ratio_sizes_the_box():
    _xml, boxes = build(".a{aspect-ratio:2/1;width:300px}", '<div class="a"></div>')
    assert boxes["a"][0].height == pytest.approx(112.5, abs=3.0)


def test_translate_percent_centers_the_box():
    _xml, boxes = build(
        ".c{position:absolute;left:50%;top:40px;transform:translateX(-50%);"
        "width:200px;height:60px}",
        '<div class="c"></div>',
    )
    expected = (960.0 - 200.0 * 0.75) / 2.0
    assert boxes["c"][0].x == pytest.approx(expected, abs=6.0)


# -------------------------------------------------------------- P1: painting
def test_per_corner_radius_uses_custom_geometry():
    xml, _boxes = build(".c{height:80px;background:#eee;border-radius:24px 0 0 0}",
                        '<div class="c"></div>')
    assert "custGeom" in xml


def test_elliptical_radius_uses_custom_geometry():
    xml, _boxes = build(".c{height:80px;background:#eee;border-radius:50%/20%}",
                        '<div class="c"></div>')
    assert "custGeom" in xml


def test_uniform_radius_stays_a_rounded_rect():
    xml, _boxes = build(".c{height:80px;background:#eee;border-radius:12px}",
                        '<div class="c"></div>')
    assert "roundRect" in xml


def test_text_shadow_lands_on_the_run():
    xml, _boxes = build(".s{text-shadow:2px 2px 3px #888;font-size:20px}",
                        '<p class="s">Shadow</p>')
    assert re.search(r"<a:rPr[^>]*>(?:(?!</a:rPr>).)*<a:effectLst>", xml, re.S)


# ------------------------------------------------------------------ SVG fixes
def test_svg_gradient_survives_the_html_parser():
    xml, _boxes = build(
        ".s{width:400px;height:120px;display:block}",
        '<svg class="s" viewBox="0 0 400 120"><defs><linearGradient id="g1">'
        '<stop offset="0" stop-color="#f00"/><stop offset="1" stop-color="#00f"/>'
        '</linearGradient></defs><rect x="20" y="20" width="360" height="80" '
        'fill="url(#g1)"/></svg>',
    )
    assert "gradFill" in xml


def test_svg_dasharray_becomes_a_preset_dash():
    xml, _boxes = build(
        ".s{width:400px;height:120px;display:block}",
        '<svg class="s" viewBox="0 0 400 120"><line x1="20" y1="60" x2="380" y2="60" '
        'stroke="#1D4ED8" stroke-width="4" stroke-dasharray="12 8"/></svg>',
    )
    assert "prstDash" in xml


def test_svg_text_becomes_editable_text():
    xml, _boxes = build(
        ".s{width:400px;height:120px;display:block}",
        '<svg class="s" viewBox="0 0 400 120"><text x="40" y="70" font-size="16" '
        'fill="#111">Label</text></svg>',
    )
    assert "<a:t>Label</a:t>" in xml
