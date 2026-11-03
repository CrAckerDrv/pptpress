"""Tests for the PPT Press engine.

Run with ``python -m pytest tests -q``.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pptx import Presentation

from pptpress import pipeline, themes, util, values


DECK = """
<!doctype html>
<html data-size="16:9">
<head><meta charset="utf-8"><style>
  :root { --ink:#101820; --brand:#E4572E; }
  .slide { font-family:'Inter',sans-serif; background:#FBF9F4; color:var(--ink);
           padding:40px 48px; }
  h1 { font-size:44px; margin:0 0 10px; }
  p  { font-size:15px; color:#5A6472; line-height:1.6; }
  .row { display:flex; gap:16px; margin-top:20px; }
  .card { flex:1; padding:16px; border:1px solid #E6E0D4; border-radius:10px; background:#fff; }
  .card h3 { font-size:16px; margin:0 0 6px; }
  .badge { position:absolute; right:48px; top:40px; padding:6px 12px; border-radius:999px;
           background:var(--brand); color:#fff; font-size:11px; }
  table { width:100%; border-collapse:collapse; margin-top:16px; }
  th, td { padding:8px; border-bottom:1px solid #E6E0D4; font-size:13px; text-align:left; }
</style></head>
<body>
  <section class="slide">
    <div class="badge">NEW</div>
    <h1>Engine test deck</h1>
    <p>One paragraph, two sentences. 中文混排也要正确换行。</p>
    <div class="row">
      <div class="card"><h3>Alpha</h3><p>First card body text.</p></div>
      <div class="card"><h3>Beta</h3><p>Second card body text.</p></div>
    </div>
    <table><thead><tr><th>Name</th><th>Value</th></tr></thead>
      <tbody><tr><td>Speed</td><td>80ms</td></tr></tbody></table>
  </section>
  <section class="slide"><h1>Second page</h1><p>Body</p>
    <aside class="notes">Speaker notes here.</aside>
  </section>
</body></html>
"""


@pytest.fixture()
def deck_file():
    handle = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    handle.write(DECK)
    handle.close()
    yield handle.name
    os.unlink(handle.name)


def test_colors():
    assert util.parse_color("#fff") == (255, 255, 255, 1.0)
    assert util.parse_color("rgb(10, 20, 30)") == (10, 20, 30, 1.0)
    assert util.parse_color("rgba(10,20,30,0.5)")[3] == 0.5
    assert util.to_dml((228, 87, 46, 1.0)) == "E4572E"
    assert util.parse_color("not-a-color") is None


def test_gradient_parsing():
    gradient = values.parse_gradient("linear-gradient(90deg, #8B7CFF 0%, #4DE3D0 100%)")
    assert gradient is not None
    assert gradient.kind == "linear"
    assert len(gradient.stops) == 2
    assert gradient.at(0.0)[:3] == (139, 124, 255)
    assert gradient.at(1.0)[:3] == (77, 227, 208)


def test_track_list():
    tracks = values.parse_track_list("repeat(3, 1fr)", size=300.0, gap=0.0)
    assert len(tracks) == 3
    assert pytest.approx(sum(tracks), rel=1e-6) == 300.0


def test_build_produces_editable_objects(deck_file):
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "deck.pptx")
        result = pipeline.build(deck_file, target)
        assert result.ok, result.issues
        assert len(result.slides) == 2
        assert not [issue for issue in result.issues if "overflow" in issue]

        presentation = Presentation(target)
        assert len(presentation.slides) == 2
        shapes = list(presentation.slides[0].shapes)
        assert shapes, "slide has no shapes"
        # Nothing may be a flat page image: every picture is either an icon or a
        # real image, never a full-slide screenshot.
        for shape in shapes:
            if shape.shape_type == 13:  # PICTURE
                area = shape.width * shape.height
                slide_area = presentation.slide_width * presentation.slide_height
                assert area < slide_area * 0.5
        # Text must survive as editable runs, not outlines.
        texts = [shape.text for shape in shapes if shape.has_text_frame]
        assert any("Engine test deck" in text for text in texts)
        assert any("Speaker notes here." in slide.notes_slide.notes_text_frame.text
                   for slide in presentation.slides)


def test_text_is_not_rasterised(deck_file):
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "deck.pptx")
        pipeline.build(deck_file, target)
        presentation = Presentation(target)
        has_text = any(
            shape.has_text_frame and shape.text_frame.text.strip()
            for shape in presentation.slides[0].shapes
        )
        assert has_text


def test_theme_roundtrip(deck_file):
    theme = themes.load("noir")
    css = theme.to_css()
    assert "--color-primary" in css
    assert theme.colors["background"].startswith("#")
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "deck.pptx")
        result = pipeline.build(deck_file, target, theme=theme)
        assert result.ok


def test_absolute_positioning(deck_file):
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "deck.pptx")
        result = pipeline.build(deck_file, target)
        slide = result.slides[0]
        badges = [box for box in slide.walk() if box.node is not None and "badge" in box.node.class_set]
        assert badges
        badge = badges[0]
        assert badge.right <= slide.width + 0.5
        assert badge.x > slide.width * 0.5


def test_no_overflow_warnings(deck_file):
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "deck.pptx")
        result = pipeline.build(deck_file, target)
    assert not [issue for issue in result.issues if "overflow" in issue]


def test_preview_writes_svg(deck_file):
    with tempfile.TemporaryDirectory() as tmp:
        result = pipeline.preview(deck_file, tmp)
        assert result.ok
        assert len(result.images) == 2
        with open(result.images[0], "r", encoding="utf-8") as handle:
            body = handle.read()
        assert body.startswith("<svg")


def test_example_decks_build():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    examples = os.path.join(root, "examples")
    if not os.path.isdir(examples):
        pytest.skip("examples folder is not present")
    html_files = sorted(name for name in os.listdir(examples) if name.endswith(".html"))
    if not html_files:
        pytest.skip("no example decks")
    with tempfile.TemporaryDirectory() as tmp:
        for name in html_files:
            target = os.path.join(tmp, name.replace(".html", ".pptx"))
            result = pipeline.build(os.path.join(examples, name), target)
            assert result.ok, (name, result.issues)
            assert not [issue for issue in result.issues if "overflow" in issue], (name, result.issues)
