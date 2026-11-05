"""Regression tests for native PowerPoint animation and transitions.

Assertions read the emitted ``p:timing`` / ``p:transition`` XML (the same tree
PowerPoint writes) and then re-open the package with python-pptx to prove it is
still a valid file.
"""

from __future__ import annotations

import os
import tempfile
import zipfile

import pytest
from pptx import Presentation

from pptpress import animate, pipeline

HEAD = """<!doctype html><html data-size="16:9"><head><meta charset="utf-8"><style>
body{margin:0}
.slide{width:1280px;height:720px;padding:40px;background:#fff;
font-family:Inter,'Segoe UI',sans-serif}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.card{height:70px;background:#eee}
</style></head><body><section class="slide"%s>%s</section></body></html>"""


def build(slide_attrs="", body=""):
    directory = tempfile.mkdtemp()
    source = os.path.join(directory, "case.html")
    target = os.path.join(directory, "case.pptx")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write(HEAD % (slide_attrs, body))
    result = pipeline.build(source, target)
    assert result.ok, result.issues
    with zipfile.ZipFile(target) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    return xml, Presentation(target)


def cards(count):
    return "".join(f'<div class="card">{index}</div>' for index in range(count))


# ---------------------------------------------------------------- transitions
@pytest.mark.parametrize("name,tag", [
    ("fade", "p:fade"),
    ("push", "p:push"),
    ("push-left", "p:push"),
    ("wipe", "p:wipe"),
    ("wipe-left", "p:wipe"),
    ("cover", "p:cover"),
    ("split", "p:split"),
    ("cut", "p:cut"),
])
def test_transition_is_written(name, tag):
    xml, _presentation = build(f' data-transition="{name}"', "<h1>One</h1>")
    assert "<p:transition" in xml
    assert tag in xml, tag


def test_transition_direction():
    xml, _presentation = build(' data-transition="push-left"', "<h1>One</h1>")
    assert 'dir="l"' in xml


def test_transition_speed():
    xml, _presentation = build(
        ' data-transition="fade" data-transition-speed="slow"', "<h1>One</h1>")
    assert 'spd="slow"' in xml


def test_transition_precedes_timing():
    # The schema requires p:transition before p:timing.
    xml, _presentation = build(
        ' data-transition="fade"',
        '<div class="card" data-anim="fade"></div>',
    )
    assert xml.index("<p:transition") < xml.index("<p:timing")


def test_no_transition_by_default():
    xml, _presentation = build("", "<h1>One</h1>")
    assert "<p:transition" not in xml


def test_unknown_transition_is_ignored():
    xml, _presentation = build(' data-transition="sparkle"', "<h1>One</h1>")
    assert "<p:transition" not in xml


# ------------------------------------------------------------------- effects
def test_entrance_effect_structure():
    xml, presentation = build("", '<div class="card" data-anim="fade-up"></div>')
    assert "<p:timing>" in xml
    assert "<p:tnLst>" in xml and "nodeType=\"tmRoot\"" in xml
    assert "<p:spTgt" in xml
    assert "style.visibility" in xml
    assert 'transition="in"' in xml
    assert "<p:anim " in xml or "<p:anim>" in xml
    assert len(presentation.slides) == 1


def test_exit_effect_hides_the_shape():
    xml, _presentation = build("", '<div class="card" data-anim="fade-out"></div>')
    assert 'val="hidden"' in xml
    assert 'transition="out"' in xml


def test_emphasis_effect_rotates():
    xml, _presentation = build("", '<div class="card" data-anim="spin"></div>')
    assert "<p:animRot" in xml


def test_no_animation_means_no_timing_tree():
    xml, _presentation = build("", "<h1>Nothing to animate</h1>")
    assert "<p:timing>" not in xml


def test_unknown_effect_is_ignored():
    xml, _presentation = build("", '<div class="card" data-anim="explode"></div>')
    assert "<p:timing>" not in xml


def test_delay_in_milliseconds():
    xml, _presentation = build("", '<div class="card" data-anim="fade" data-anim-delay="0.3"></div>')
    assert 'delay="300"' in xml


def test_bare_number_reads_as_seconds_below_twenty():
    spec = animate.parse_spec(_Fake({"data-anim": "fade", "data-anim-delay": "0.6"}))
    assert spec.delay == pytest.approx(0.6)


def test_millisecond_suffix():
    spec = animate.parse_spec(_Fake({"data-anim": "fade", "data-anim-delay": "300ms"}))
    assert spec.delay == pytest.approx(0.3)


def test_custom_duration():
    xml, _presentation = build("", '<div class="card" data-anim="fade" data-anim-dur="1.2"></div>')
    assert 'dur="1200"' in xml


# ------------------------------------------------------------------ grouping
def test_click_then_with_is_one_click():
    body = ('<div class="card" data-anim="fade"></div>'
            '<div class="card" data-anim="fade" data-anim-trigger="with"></div>')
    xml, _presentation = build("", body)
    assert xml.count('delay="indefinite"') == 1
    assert 'nodeType="withEffect"' in xml


def test_two_clicks():
    body = ('<div class="card" data-anim="fade"></div>'
            '<div class="card" data-anim="fade"></div>')
    xml, _presentation = build("", body)
    assert xml.count('delay="indefinite"') == 2


def test_after_chains_onto_previous_group():
    body = ('<div class="card" data-anim="fade"></div>'
            '<div class="card" data-anim="fade" data-anim-trigger="after"></div>')
    xml, _presentation = build("", body)
    assert 'evt="onEnd"' in xml
    assert xml.count('delay="indefinite"') == 1


def test_explicit_group_number_joins():
    body = ('<div class="card" data-anim="fade" data-anim-group="1"></div>'
            '<div class="card" data-anim="fade" data-anim-group="1"></div>')
    xml, _presentation = build("", body)
    assert xml.count('delay="indefinite"') == 1


# ------------------------------------------------------------------- stagger
def test_stagger_reveals_children_in_sequence():
    xml, presentation = build(
        "", f'<div class="grid" data-anim="fade-up" data-anim-stagger="0.12">{cards(4)}</div>')
    assert xml.count('delay="indefinite"') == 1
    assert xml.count('presetClass="entr"') == 8     # four cards, each + its label
    assert 'delay="120"' in xml
    assert 'delay="360"' in xml
    assert len(presentation.slides) == 1


def test_stagger_default_step():
    xml, _presentation = build(
        "", f'<div class="grid" data-anim="fade" data-anim-stagger>{cards(3)}</div>')
    assert 'delay="240"' in xml


def test_stagger_with_one_child_does_not_split():
    xml, _presentation = build(
        "", f'<div class="grid" data-anim="fade" data-anim-stagger="0.2">{cards(1)}</div>')
    assert xml.count('delay="indefinite"') == 1


def test_without_stagger_the_container_is_one_unit():
    xml, _presentation = build(
        "", f'<div class="grid" data-anim="fade">{cards(4)}</div>')
    assert xml.count('delay="indefinite"') == 1
    assert xml.count('presetClass="entr"') == 8


# ------------------------------------------------------------------ coverage
def test_list_items_can_animate_individually():
    body = ('<ul><li data-anim="fade-up">One</li>'
            '<li data-anim="fade-up">Two</li></ul>')
    xml, _presentation = build("", body)
    assert xml.count('delay="indefinite"') == 2


def test_heading_animation_targets_its_text_box():
    xml, _presentation = build("", '<h1 data-anim="fade">Title</h1>')
    assert "<p:timing>" in xml
    assert "<p:spTgt" in xml


@pytest.mark.parametrize("name", sorted(animate.EFFECTS))
def test_every_effect_builds_and_opens(name):
    xml, presentation = build("", f'<div class="card" data-anim="{name}"></div>')
    assert "<p:timing>" in xml
    assert len(presentation.slides) == 1


def test_mixed_deck_keeps_animation_off_quiet_slides():
    html = """<!doctype html><html data-size="16:9"><head><meta charset="utf-8"><style>
    body{margin:0}.slide{width:1280px;height:720px;background:#fff;padding:30px}
    .card{height:60px;background:#eee}
    </style></head><body>
    <section class="slide" data-transition="fade">
      <div class="card" data-anim="fade-up">A</div>
    </section>
    <section class="slide"><div class="card">B</div></section>
    </body></html>"""
    directory = tempfile.mkdtemp()
    source = os.path.join(directory, "m.html")
    target = os.path.join(directory, "m.pptx")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write(html)
    result = pipeline.build(source, target)
    assert result.ok, result.issues
    with zipfile.ZipFile(target) as archive:
        first = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        second = archive.read("ppt/slides/slide2.xml").decode("utf-8")
    assert "<p:timing>" in first and "<p:transition" in first
    assert "<p:timing>" not in second and "<p:transition" not in second
    assert len(Presentation(target).slides) == 2


class _Fake:
    def __init__(self, attributes):
        self._attributes = attributes

    def attr(self, name):
        return self._attributes.get(name)
