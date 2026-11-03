"""Slide discovery: which elements become slides, in which order."""

from __future__ import annotations

SLIDE_TAGS = {"section", "div", "article"}
DEFAULT_CLASSES = {"slide", "deckpress-slide"}


def slide_nodes(document):
    """Return slide nodes in document order.

    Order of preference:
    1. explicit ``.slide``/``.deckpress-slide`` elements;
    2. ``<section>`` children of the deck container;
    3. any ``<section>`` element;
    4. the whole body as a single slide.
    """
    root = document.root
    explicit = [node for node in root.iter_elements() if _is_slide(node)]
    if explicit:
        return _top_level(document, explicit)
    sections = [node for node in root.iter_elements() if node.tag_name == "section"]
    if sections:
        return _top_level(document, sections)
    return [root]


def _is_slide(node):
    return bool(node.class_set & DEFAULT_CLASSES)


def _top_level(document, nodes):
    """Drop slides nested inside another slide (they are content, not pages)."""
    chosen = []
    for node in nodes:
        if any(_is_ancestor(other, node) for other in nodes if other is not node):
            continue
        chosen.append(node)
    return chosen or nodes


def _is_ancestor(candidate, node):
    parent = node.parent_node
    while parent is not None:
        if parent is candidate:
            return True
        parent = parent.parent_node
    return False


def slide_size(document, default=(960.0, 540.0)):
    """Read ``data-size="16:9"``/``"1280x720"`` from the deck root or body."""
    for node in (document.root, getattr(document, "raw_slide_root", None)):
        if node is None:
            continue
        raw = node.attr("data-size") or node.attr("data-aspect")
        if raw:
            return parse_size(raw, default)
    return default


def parse_size(raw, default=(960.0, 540.0)):
    from . import util

    text = str(raw).strip().lower()
    presets = {
        "16:9": (960.0, 540.0),
        "16:10": (960.0, 600.0),
        "4:3": (960.0, 720.0),
        "3:2": (960.0, 640.0),
        "1:1": (720.0, 720.0),
        "9:16": (540.0, 960.0),
        "a4": (842.0, 595.0),
    }
    if text in presets:
        return presets[text]
    match = text.replace(" ", "")
    if "x" in match:
        left, _, right = match.partition("x")
        try:
            return (float(left) * util.PT_PER_PX, float(right) * util.PT_PER_PX)
        except ValueError:
            return default
    if ":" in text:
        left, _, right = text.partition(":")
        try:
            ratio = float(left) / float(right)
        except (ValueError, ZeroDivisionError):
            return default
        return (960.0, 960.0 / ratio)
    return default
