"""Layout engine: CSS-styled HTML -> positioned boxes in points.

Supported and verified by the test-suite:

* block flow with anonymous inline runs (mixed text + blocks inside one container)
* flexbox (row / row-reverse / column / column-reverse, wrap, gap, grow,
  justify-content, align-items, align-self)
* CSS grid with fixed / ``fr`` / ``auto`` / ``repeat()`` tracks
* absolute positioning relative to the nearest positioned ancestor
* text metrics from the real fonts (PIL/FreeType), wrapping, alignment,
  letter-spacing, line-height, text-transform, underline
* boxes: padding, margin, border sides, border-radius, box/text shadows,
  gradients, background images, opacity, rotation
* images with ``object-fit``, inline SVG icons, tables with merged cells
* lists rendered as native, editable PPTX bullet paragraphs

The engine intentionally ignores what PowerPoint cannot express natively
(transforms on text runs, filters, animations, etc.); those degrade gracefully.
"""

from __future__ import annotations

import math
import os
import re

from . import util, values
from .dom import Node, TextNode
from .slides import slide_nodes

INLINE_TAGS = {
    "span", "b", "strong", "i", "em", "u", "s", "small", "sub", "sup", "mark",
    "a", "code", "label", "abbr", "cite", "q", "time", "kbd", "br", "wbr", "font",
    "del", "ins",
}
REPLACED_INLINE = {"img", "svg"}
BLOCK_TAGS = {
    "div", "section", "article", "header", "footer", "main", "aside", "nav",
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li", "table", "figure",
    "figcaption", "blockquote", "pre", "dl", "dt", "dd", "form", "fieldset",
    "address", "hr",
}
HEADING_SIZE = {"h1": 32.0, "h2": 24.0, "h3": 19.0, "h4": 16.0, "h5": 14.0, "h6": 12.0}
HEADING_WEIGHT = {"h1": 700, "h2": 700, "h3": 600, "h4": 600, "h5": 600, "h6": 600}

_CJK_RANGES = (
    (0x2E80, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFE30, 0xFE4F),
    (0xFF00, 0xFFEF), (0x20000, 0x2FA1F), (0x1F000, 0x1FAFF),
)
_NO_BREAK_BEFORE = set("，。、；：？！）》」』】〉”’%‰%,.!?;:)]}…·")
_NO_BREAK_AFTER = set("（《「『【〈“‘([{")

BULLET_FOR_STYLE = {
    "disc": "•",
    "circle": "◦",
    "square": "▪",
    "none": "",
}

# Ordered lists must stay *auto numbering* in PowerPoint, so the numbers renumber
# themselves when a slide is edited. Mapping them to a literal "1." character
# would freeze every item at one.
AUTONUM_FOR_STYLE = {
    "decimal": "arabicPeriod",
    "decimal-leading-zero": "arabicPeriod",
    "lower-alpha": "alphaLcPeriod",
    "upper-alpha": "alphaUcPeriod",
    "lower-roman": "romanLcPeriod",
    "upper-roman": "romanUcPeriod",
    "lower-latin": "alphaLcPeriod",
    "upper-latin": "alphaUcPeriod",
}


def _is_cjk(char):
    code = ord(char)
    return any(low <= code <= high for low, high in _CJK_RANGES)


class Style:
    """Resolved style for one node, all lengths in points."""

    __slots__ = (
        "display", "position", "flex_direction", "justify_content", "align_items",
        "flex_wrap", "gap_row", "gap_col", "width", "height", "min_width",
        "max_width", "min_height", "max_height", "margin", "padding", "border",
        "radius", "background", "shadows", "color", "font_size", "font_family",
        "font_weight", "font_style", "line_height", "letter_spacing", "text_align",
        "text_transform", "opacity", "z_index", "transform", "overflow",
        "grid_columns", "grid_rows", "vertical_align", "flex_grow", "align_self",
        "object_fit", "white_space", "text_decoration", "box_sizing", "text_indent",
        "list_style", "is_list", "list_indent", "paint", "top", "right", "bottom", "left",
        "text_shadow", "baseline_shift", "object_position", "font_variant_numeric",
        "list_start", "grid_column", "grid_row", "align_content", "aspect_ratio",
    )

    def __init__(self):
        self.display = "block"
        self.position = "static"
        self.flex_direction = "row"
        self.justify_content = "start"
        self.align_items = "stretch"
        self.flex_wrap = "nowrap"
        self.gap_row = 0.0
        self.gap_col = 0.0
        self.width = None
        self.height = None
        self.min_width = 0.0
        self.max_width = None
        self.min_height = 0.0
        self.max_height = None
        self.margin = (0.0, 0.0, 0.0, 0.0)
        self.padding = (0.0, 0.0, 0.0, 0.0)
        self.border = None
        self.radius = None
        self.background = None
        self.shadows = []
        self.color = (17, 17, 17, 1.0)
        self.font_size = 12.0
        self.font_family = "Inter, sans-serif"
        self.font_weight = 400
        self.font_style = "normal"
        self.line_height = 1.3
        self.letter_spacing = 0.0
        self.text_align = "left"
        self.text_transform = "none"
        self.opacity = 1.0
        self.z_index = 0
        self.transform = {"rotate": 0.0, "scale": (1.0, 1.0), "translate": (0.0, 0.0)}
        self.overflow = "visible"
        self.grid_columns = None
        self.grid_rows = None
        self.vertical_align = "top"
        self.flex_grow = 0.0
        self.align_self = None
        self.object_fit = "cover"
        self.white_space = "normal"
        self.text_decoration = "none"
        self.box_sizing = "border-box"
        self.text_indent = 0.0
        self.list_style = "disc"
        self.is_list = False
        self.list_indent = 0.0
        self.paint = False
        self.top = None
        self.right = None
        self.bottom = None
        self.left = None
        self.text_shadow = None
        self.baseline_shift = 0.0      # >0 superscript, <0 subscript (fraction of size)
        self.object_position = None    # (x, y) keywords or percentages for object-fit
        self.font_variant_numeric = "normal"
        self.list_start = 1
        self.grid_column = (None, 1)   # (start, span); start is 1-based or None
        self.grid_row = (None, 1)
        self.align_content = "start"
        self.aspect_ratio = None       # width / height

    # -- derived ---------------------------------------------------------
    @property
    def bold(self):
        return self.font_weight >= 600

    @property
    def italic(self):
        return self.font_style in ("italic", "oblique")

    @property
    def rotated(self):
        return abs(self.transform.get("rotate") or 0.0) > 0.01

    @property
    def horizontal_padding(self):
        return self.padding[1] + self.padding[3]

    @property
    def vertical_padding(self):
        return self.padding[0] + self.padding[2]

    @property
    def horizontal_border(self):
        if not self.border:
            return 0.0
        return sum(side.width for side in (self.border[1], self.border[3]) if side and side.visible)

    @property
    def vertical_border(self):
        if not self.border:
            return 0.0
        return sum(side.width for side in (self.border[0], self.border[2]) if side and side.visible)


# --------------------------------------------------------------------------
# style resolution
# --------------------------------------------------------------------------
def _split_values(text):
    if not text:
        return []
    return [part for part in re.split(r"\s+", text.strip()) if part]


def _resolve_length(text, base_pt=None, font_size_pt=12.0):
    length = values.parse_length(text)
    if length is None or length.keyword in ("auto", "none", "normal", "fit-content"):
        return None
    if length.percent:
        return (base_pt or 0.0) * length.value / 100.0
    return length.resolve(base_pt=base_pt, font_size_pt=font_size_pt)


# One ``Percent`` type for the whole engine: the layout module's isinstance()
# checks and values.parse_transform() must agree, otherwise percentage
# translates silently degrade to zero.
Percent = values.Percent


def _percent_of(text):
    length = values.parse_length(text)
    if length is not None and length.percent:
        return values.Percent(length.value / 100.0)
    return None


def build_style(node, resolver, context, parent_style=None):
    """Resolve every CSS property this engine understands for ``node``."""
    computed = resolver.computed(node)
    style = Style()
    parent_font = parent_style.font_size if parent_style else 12.0

    # ---- typography ---------------------------------------------------
    raw_font = computed.get("font-size")
    size = None
    if raw_font:
        length = values.parse_length(raw_font)
        if length is not None and length.keyword is None:
            if length.percent:
                size = parent_font * length.value / 100.0
            elif length.unit == "em":
                size = parent_font * length.value
            else:
                size = length.resolve(font_size_pt=parent_font)
    if size is None:
        if node.tag_name in HEADING_SIZE:
            size = HEADING_SIZE[node.tag_name] if parent_style is None else parent_font * 1.6
        else:
            size = parent_font if parent_style else 12.0
    style.font_size = max(1.0, size)

    raw_weight = (computed.get("font-weight") or "").strip().lower()
    weight = None
    if raw_weight:
        if raw_weight in ("bold", "bolder"):
            weight = 700
        elif raw_weight == "lighter":
            weight = 300
        elif raw_weight.isdigit():
            weight = int(raw_weight)
    if weight is None and node.tag_name in HEADING_WEIGHT and parent_style is None:
        weight = HEADING_WEIGHT[node.tag_name]
    if weight is None and node.tag_name in ("b", "strong", "th"):
        weight = 700
    style.font_weight = weight if weight is not None else 400

    style.font_style = (computed.get("font-style") or ("italic" if node.tag_name in ("i", "em") else "normal")).lower()
    style.font_family = computed.get("font-family") or (parent_style.font_family if parent_style else "Inter, sans-serif")
    color = util.parse_color(computed.get("color"))
    style.color = color or (parent_style.color if parent_style else (17, 17, 17, 1.0))

    raw_line = (computed.get("line-height") or "normal").strip()
    if raw_line in ("normal", "", "inherit"):
        style.line_height = 1.32
    else:
        length = values.parse_length(raw_line)
        if length is None:
            style.line_height = 1.32
        elif length.percent:
            style.line_height = length.value / 100.0
        elif length.unit in ("px", "pt", "in", "cm", "mm", "pc") and length.value > 4:
            style.line_height = length.resolve() / style.font_size
        else:
            style.line_height = length.value
        style.line_height = util.clamp(style.line_height, 0.6, 3.0)

    spacing = values.parse_length(computed.get("letter-spacing"))
    if spacing is not None and spacing.keyword is None:
        style.letter_spacing = spacing.resolve(font_size_pt=style.font_size) or 0.0

    style.text_align = values.parse_text_align(computed.get("text-align"))
    style.text_transform = (computed.get("text-transform") or "none").lower()
    style.white_space = (computed.get("white-space") or "normal").lower()
    decoration = computed.get("text-decoration-line") or computed.get("text-decoration") or "none"
    style.text_decoration = decoration.lower()
    if node.tag_name == "u":
        style.text_decoration = "underline"
    if node.tag_name in ("sub", "sup"):
        # Native baseline shift: PowerPoint keeps the run editable instead of
        # faking it with a smaller font on a raised line.
        style.baseline_shift = -0.25 if node.tag_name == "sub" else 0.30
    style.text_indent = _resolve_length(computed.get("text-indent"), 0.0, style.font_size) or 0.0
    style.vertical_align = (computed.get("vertical-align") or "top").lower()
    numeric = (computed.get("font-variant-numeric") or "normal").lower()
    style.font_variant_numeric = numeric
    shadow = computed.get("text-shadow")
    if shadow:
        parsed = values.parse_shadow(shadow, style.font_size)
        if parsed:
            style.text_shadow = parsed[0]

    # ---- box model ----------------------------------------------------
    display = (computed.get("display") or "").strip().lower()
    style.display = display or _default_display(node)
    if "abs" in node.class_set and (computed.get("position") or "static").lower() == "static":
        style.position = "absolute"
    else:
        style.position = (computed.get("position") or "static").lower()

    style.flex_direction = (computed.get("flex-direction") or "row").lower()
    style.justify_content = values.parse_justify_content(computed.get("justify-content"))
    style.align_items = values.parse_align_items(computed.get("align-items"))
    style.align_content = values.parse_align_content(computed.get("align-content"))
    style.flex_wrap = (computed.get("flex-wrap") or "nowrap").lower()
    style.grid_column = values.parse_grid_column(computed.get("grid-column"))
    style.grid_row = values.parse_grid_column(computed.get("grid-row"))
    ratio = values.parse_aspect_ratio(computed.get("aspect-ratio"))
    style.aspect_ratio = ratio
    position_raw = computed.get("object-position")
    if position_raw:
        style.object_position = values.parse_object_position(position_raw)
    align_self = computed.get("align-self")
    style.align_self = values.parse_align_items(align_self) if align_self else None
    style.overflow = (computed.get("overflow") or "visible").lower()
    style.object_fit = (computed.get("object-fit") or "cover").lower()
    style.box_sizing = (computed.get("box-sizing") or "border-box").lower()

    gap_raw = computed.get("gap") or computed.get("grid-gap")
    if gap_raw:
        parts = [p for p in _split_values(gap_raw)]
        resolved = [_resolve_length(p, None, style.font_size) for p in parts]
        resolved = [r for r in resolved if r is not None]
        if resolved:
            style.gap_row = resolved[0]
            style.gap_col = resolved[1] if len(resolved) > 1 else resolved[0]
    for key, attr in (("row-gap", "gap_row"), ("column-gap", "gap_col")):
        value = _resolve_length(computed.get(key), None, style.font_size)
        if value is not None:
            setattr(style, attr, value)

    style.margin = _sides(computed, "margin", style.font_size, percent_base=context["content_width"])
    style.padding = _sides(computed, "padding", style.font_size, percent_base=context["content_width"])
    style.border = _border_sides(computed, style)
    radius = values.parse_radius(computed.get("border-radius"))
    if radius:
        style.radius = radius

    background = values.parse_background(computed.get("background") or computed.get("background-color"))
    image_raw = computed.get("background-image")
    if image_raw and "url(" in image_raw:
        extra = values.parse_background(image_raw)
        if extra is not None and extra.image:
            if background is None:
                background = extra
            elif not background.image and not background.gradients:
                background.image = extra.image
    if background is not None:
        if computed.get("background-size"):
            background.size = computed.get("background-size")
        if computed.get("background-position"):
            background.position = computed.get("background-position")
        if computed.get("background-repeat"):
            background.repeat = computed.get("background-repeat")
        style.background = background

    shadow_raw = computed.get("box-shadow")
    if shadow_raw:
        style.shadows = values.parse_shadow(shadow_raw, style.font_size)
    text_shadow = computed.get("text-shadow")
    if text_shadow:
        style.shadows = values.parse_shadow(text_shadow, style.font_size) or style.shadows

    transform_raw = computed.get("transform")
    if transform_raw:
        style.transform = values.parse_transform(transform_raw)

    opacity = computed.get("opacity")
    if opacity:
        try:
            style.opacity = util.clamp(float(opacity), 0.0, 1.0)
        except ValueError:
            pass
    z_index = (computed.get("z-index") or "").strip()
    if z_index.lstrip("-").isdigit():
        style.z_index = int(z_index)

    style.grid_columns = computed.get("grid-template-columns")
    style.grid_rows = computed.get("grid-template-rows")

    # ---- sizing -------------------------------------------------------
    content_width = context["content_width"]
    content_height = context["content_height"]
    width_percent = _percent_of(computed.get("width"))
    height_percent = _percent_of(computed.get("height"))
    style.width = width_percent if width_percent is not None else _resolve_length(
        computed.get("width"), content_width, style.font_size
    )
    style.height = height_percent if height_percent is not None else _resolve_length(
        computed.get("height"), content_height, style.font_size
    )
    if style.width is not None and style.width <= 0:
        style.width = None
    if style.height is not None and style.height <= 0:
        style.height = None
    style.min_width = _resolve_length(computed.get("min-width"), content_width, style.font_size) or 0.0
    style.max_width = _resolve_length(computed.get("max-width"), content_width, style.font_size)
    style.min_height = _resolve_length(computed.get("min-height"), content_height, style.font_size) or 0.0
    style.max_height = _resolve_length(computed.get("max-height"), content_height, style.font_size)

    flex = (computed.get("flex") or "").strip().lower()
    if flex:
        match = re.match(r"^([\d.]+)", flex)
        if match and flex not in ("none", "0"):
            style.flex_grow = float(match.group(1)) if float(match.group(1)) > 0 else 1.0
        elif flex in ("auto", "1"):
            style.flex_grow = 1.0
    grow = (computed.get("flex-grow") or "").strip()
    if grow:
        try:
            style.flex_grow = float(grow)
        except ValueError:
            pass

    style.list_style = (computed.get("list-style-type") or "disc").lower()
    if node.tag_name == "li":
        style.is_list = True
        style.list_indent = 0.0
        style.list_start = _list_start(node)
    elif parent_style is not None and getattr(parent_style, "is_list", False):
        style.list_style = parent_style.list_style
        style.is_list = True
    list_style = computed.get("list-style")
    if list_style and node.tag_name in ("ul", "ol"):
        marker = list_style.strip().lower()
        style.list_style = marker.split()[0] if marker else style.list_style

    # Absolute offsets resolved against the containing block.
    style.top = _resolve_length(computed.get("top"), content_height, style.font_size)
    style.right = _resolve_length(computed.get("right"), content_width, style.font_size)
    style.bottom = _resolve_length(computed.get("bottom"), content_height, style.font_size)
    style.left = _resolve_length(computed.get("left"), content_width, style.font_size)

    style.paint = _has_paint(style)
    return style


def _has_paint(style):
    if style.border and any(side and side.visible for side in style.border):
        return True
    background = style.background
    if background is not None:
        if background.gradients or background.image:
            return True
        if background.color is not None and util.alpha_of(background.color) > 0.004:
            return True
    return bool(style.shadows)


def _sides(computed, prefix, font_size, percent_base):
    box = [0.0, 0.0, 0.0, 0.0]
    shorthand = computed.get(prefix)
    if shorthand:
        lengths = []
        for token in _split_values(shorthand):
            length = values.parse_length(token)
            if length is None:
                continue
            if length.percent:
                lengths.append(percent_base * length.value / 100.0)
            elif length.keyword == "auto":
                lengths.append(0.0)
            else:
                lengths.append(length.resolve(font_size_pt=font_size) or 0.0)
        expanded = values.expand_box(lengths)
        if expanded:
            box = [max(0.0, value) for value in expanded]
    for index, key in enumerate((f"{prefix}-top", f"{prefix}-right", f"{prefix}-bottom", f"{prefix}-left")):
        raw = computed.get(key)
        if raw is None:
            continue
        value = _resolve_length(raw, percent_base, font_size)
        if value is not None:
            box[index] = max(0.0, value)
        elif raw.strip() == "auto":
            box[index] = 0.0
    return tuple(box)


def _border_sides(computed, style):
    default_color = util.parse_color(computed.get("border-color")) if computed.get("border-color") else None
    sides = [None, None, None, None]
    shorthand = computed.get("border")
    if shorthand:
        side = values.parse_border_side(shorthand, default_color or style.color)
        sides = [side, side, side, side]
    names = ("top", "right", "bottom", "left")
    for index, name in enumerate(names):
        specific = computed.get(f"border-{name}")
        if specific:
            sides[index] = values.parse_border_side(specific, default_color or style.color)
            continue
        width_raw = computed.get(f"border-{name}-width")
        if not width_raw:
            continue
        width = _resolve_length(width_raw, None, style.font_size) or 0.0
        style_raw = (computed.get(f"border-{name}-style") or "solid").lower()
        color_raw = computed.get(f"border-{name}-color")
        color = util.parse_color(color_raw) if color_raw else (default_color or style.color)
        if width > 0 and style_raw not in ("none", "hidden"):
            sides[index] = values.Border(width, style_raw, color)
        elif sides[index] is None:
            sides[index] = values.Border(0.0, "none", None)
    if any(side and side.visible for side in sides):
        return tuple(sides)
    return None


def _default_display(node):
    tag = node.tag_name
    if tag in ("style", "script", "head", "title", "meta", "link", "aside"):
        return "none"
    if tag in INLINE_TAGS or tag in REPLACED_INLINE:
        return "inline"
    if tag in ("tr",):
        return "table-row"
    if tag in ("td", "th"):
        return "table-cell"
    if tag in ("table",):
        return "table"
    if tag == "li":
        return "list-item"
    return "block"


# --------------------------------------------------------------------------
# text engine
# --------------------------------------------------------------------------
class TextLine:
    __slots__ = ("runs", "width", "height")

    def __init__(self, runs, width, height):
        self.runs = runs
        self.width = width
        self.height = height


class TextEngine:
    def __init__(self, metrics):
        self.metrics = metrics

    def width(self, text, style):
        return self.metrics.text_width_pt(
            text, style.font_family, style.font_size, style.bold, style.italic, style.letter_spacing
        )

    def tokens(self, runs):
        output = []
        pending_space = False
        for run in runs:
            text, style = run[0], run[1]
            if not text:
                continue
            if pending_space:
                # Whitespace at the end of one run separates it from the next
                # run too (``like a <em>page</em>``), so re-emit it here.
                output.append((" ", style, self.width(" ", style), "space"))
                pending_space = False
            for token, token_style, width, kind in self._segment(text, style):
                output.append((token, token_style, width, kind))
                pending_space = kind == "space"
            if text[-1] in " \t\r\n\f" and not pending_space:
                pending_space = True
        return _glue_punctuation(output)

    def _glue(self, token, style):
        return token, style, self.width(token, style)

    def _segment(self, text, style):
        transformed = _transform(text, style)
        if style.white_space in ("pre", "pre-wrap"):
            for position, piece in enumerate(transformed.split("\n")):
                if position:
                    yield ("\n", style, 0.0, "break")
                if piece:
                    yield (piece, style, self.width(piece, style), "word")
            return
        if style.white_space == "nowrap":
            collapsed = transformed.replace("\n", " ").replace("\t", " ")
            if collapsed:
                yield (collapsed, style, self.width(collapsed, style), "word")
            return
        if transformed == "\n":
            # An explicit ``<br>`` arrives as its own run; it must stay a break.
            yield ("\n", style, 0.0, "break")
            return
        # CSS collapses runs of whitespace (including source newlines and the
        # indentation around them) into a single inter-word space, so keep at
        # most one pending space and flush it only before real content.
        buffer = []
        pending_space = [False]

        def flush_word():
            if buffer:
                token = "".join(buffer)
                buffer.clear()
                yield (token, style, self.width(token, style), "word")

        for char in transformed:
            if char in " \t\r\n\f":
                if buffer:
                    yield from flush_word()
                pending_space[0] = True
                continue
            if pending_space[0]:
                pending_space[0] = False
                yield (" ", style, self.width(" ", style), "space")
            if char == "\u00a0":
                yield from flush_word()
                yield ("\u00a0", style, self.width("\u00a0", style), "word")
            elif char in _NO_BREAK_BEFORE:
                if buffer:
                    buffer.append(char)
                    yield from flush_word()
                else:
                    yield (char, style, self.width(char, style), "word")
            elif char in _NO_BREAK_AFTER:
                buffer.append(char)
            elif _is_cjk(char):
                yield from flush_word()
                yield (char, style, self.width(char, style), "word")
            elif char == "-" and buffer:
                buffer.append(char)
                yield from flush_word()
            else:
                buffer.append(char)
        yield from flush_word()

    def wrap(self, runs, max_width):
        runs = _normalize_runs(runs)
        tokens = self.tokens(runs)
        lines = []
        current = []
        width = 0.0
        limit = max(1.0, max_width)
        for text, style, token_width, kind in tokens:
            if kind == "break":
                trimmed, trimmed_width = _trim(current)
                lines.append((trimmed, trimmed_width))
                current = []
                width = 0.0
                continue
            if kind == "space":
                if current:
                    current.append((text, style, token_width))
                    width += token_width
                continue
            if current and width + token_width > limit + 0.01:
                trimmed, trimmed_width = _trim(current)
                if trimmed:
                    lines.append((trimmed, trimmed_width))
                current = []
                width = 0.0
            current.append((text, style, token_width))
            width += token_width
        trimmed, trimmed_width = _trim(current)
        lines.append((trimmed, trimmed_width))
        result = []
        for line_runs, line_width in lines:
            if not line_runs:
                style = runs[0][1] if runs else Style()
                result.append(TextLine([], 0.0, self._line_height(style)))
                continue
            height = max(self._line_height(style) for _t, style, _w in line_runs)
            result.append(TextLine(_merge_runs(line_runs), line_width, height))
        return result

    def _line_height(self, style):
        designed = style.font_size * style.line_height
        natural = self.metrics.natural_line_height_pt(style.font_family, style.font_size)
        return max(designed, natural)


def _glue_punctuation(tokens):
    """Attach closing CJK punctuation to the token before it.

    A browser never starts a line with ``。`` or ``，``: the character is held with
    the preceding glyph when the line breaks. Doing the same here keeps exported
    lines from ending with a lone full stop on the next line.
    """
    glued = []
    for token, style, width, kind in tokens:
        if (
            kind == "word"
            and token
            and token[0] in _NO_BREAK_BEFORE
            and glued
            and glued[-1][3] == "word"
            and glued[-1][1] is style
        ):
            previous = glued[-1]
            text = previous[0] + token
            glued[-1] = (text, style, previous[2] + width, "word")
            continue
        glued.append((token, style, width, kind))
    return glued


def _normalize_runs(runs):
    """Accept ``(text, style)`` or ``(text, style, width)`` runs alike."""
    normalized = []
    for run in runs:
        if len(run) >= 3:
            normalized.append((run[0], run[1]))
        elif len(run) == 2:
            normalized.append((run[0], run[1]))
    return [run for run in normalized if run[0]]


def _transform(text, style):
    mode = style.text_transform
    if mode == "uppercase":
        return text.upper()
    if mode == "lowercase":
        return text.lower()
    if mode == "capitalize":
        return " ".join(word[:1].upper() + word[1:] if word else word for word in text.split(" "))
    return text


def _trim(runs):
    while runs and runs[-1][0] == " ":
        runs = runs[:-1]
    width = sum(run[2] for run in runs)
    return runs, width


def _merge_runs(runs):
    merged = []
    for text, style, width in runs:
        if merged and merged[-1][1] is style:
            merged[-1] = (merged[-1][0] + text, style, merged[-1][2] + width)
        else:
            merged.append((text, style, width))
    return merged


# --------------------------------------------------------------------------
# layout boxes
# --------------------------------------------------------------------------
class LayoutBox:
    __slots__ = (
        "node", "style", "rect", "content_rect", "children", "kind", "lines",
        "image_src", "table", "svg_node", "text", "extra", "order", "z",
    )

    def __init__(self, node, style, rect, kind="block"):
        self.node = node
        self.style = style
        self.rect = rect
        self.content_rect = rect
        self.children = []
        self.kind = kind
        self.lines = None
        self.image_src = None
        self.table = None
        self.svg_node = None
        self.text = ""
        self.extra = {}
        self.order = 0
        self.z = 0

    # -- geometry --------------------------------------------------------
    @property
    def x(self):
        return self.rect[0]

    @property
    def y(self):
        return self.rect[1]

    @property
    def width(self):
        return self.rect[2]

    @property
    def height(self):
        return self.rect[3]

    @property
    def bottom(self):
        return self.rect[1] + self.rect[3]

    @property
    def right(self):
        return self.rect[0] + self.rect[2]

    def shift(self, dx, dy):
        if not dx and not dy:
            return
        self.rect = (self.rect[0] + dx, self.rect[1] + dy, self.rect[2], self.rect[3])
        self.content_rect = (
            self.content_rect[0] + dx,
            self.content_rect[1] + dy,
            self.content_rect[2],
            self.content_rect[3],
        )
        for child in self.children:
            child.shift(dx, dy)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def __repr__(self):
        return f"<Box {self.kind} {self.node.tag_name if self.node else '?'} {self.rect}>"


class SlideBox:
    def __init__(self, width, height, background=None):
        self.width = width
        self.height = height
        self.background = background
        self.children = []
        self.speaker_notes = ""
        self.title = ""
        self.index = 0
        self.style = None
        self.meta = {}
        self.node = None      # the <section> this slide came from

    def walk(self):
        for child in self.children:
            yield from child.walk()


class _Item:
    """One entry in a container's flow: a block element or an inline group."""

    __slots__ = ("kind", "node", "style", "nodes")

    def __init__(self, kind, node=None, style=None, nodes=None):
        self.kind = kind
        self.node = node
        self.style = style
        self.nodes = nodes


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------
class LayoutEngine:
    def __init__(self, resolver, metrics, slide_width, slide_height, base_dir=""):
        self.resolver = resolver
        self.metrics = metrics
        self.text_engine = TextEngine(metrics)
        self.slide_width = slide_width
        self.slide_height = slide_height
        self.base_dir = base_dir or ""
        self.warnings = []
        self._image_cache = {}

    # -- entry -----------------------------------------------------------
    def layout_document(self, document):
        result = []
        for index, node in enumerate(slide_nodes(document)):
            result.append(self.layout_slide(node, index))
        return result

    def layout_slide(self, node, index):
        slide = SlideBox(self.slide_width, self.slide_height)
        slide.index = index
        slide.node = node
        context = {"content_width": self.slide_width, "content_height": self.slide_height}
        style = build_style(node, self.resolver, context)
        slide.style = style
        if style.background is not None:
            slide.background = style.background
        backdrop = _opaque_color(slide.background) or (255, 255, 255, 1.0)
        box_x = style.padding[3]
        box_y = style.padding[0]
        inner_w = self.slide_width - style.padding[1] - style.padding[3]
        inner_h = self.slide_height - style.padding[0] - style.padding[2]
        children = self._layout_flow(node, style, box_x, box_y, inner_w, inner_h)
        slide.children = self._stack(children)
        for child in slide.children:
            self._annotate_backdrop(child, backdrop)
        slide.children = self._stack(children)
        slide.speaker_notes = self._notes_of(node)
        title = node.find_first({"h1", "h2", "h3"}, max_depth=3)
        slide.title = title.text() if title is not None else ""
        return slide

    def _notes_of(self, node):
        aside = node.find_first({"aside"}, max_depth=4)
        if aside is None:
            return ""
        for descendant in aside.iter_elements():
            if "notes" in descendant.class_set:
                return descendant.text()
        return aside.text()

    def _stack(self, items):
        """Assign paint order: later siblings on top, absolute last."""
        flat = []
        for item in items:
            if item.kind == "row":
                flat.extend(item.children)
            else:
                flat.append(item)
        ordered = sorted(flat, key=lambda box: (box.z, box.order))
        for position, box in enumerate(ordered):
            box.order = position
        return ordered

    def _annotate_backdrop(self, box, backdrop):
        """Record what each text box actually sits on.

        Nested opaque surfaces (cards, panels, dark sections) change the effective
        background, so the writer needs the *local* backdrop — not the slide's — to
        keep text readable and to pick sane defaults for semi-transparent text.
        """
        own = box.style.background if box.style is not None else None
        if box.style is not None and box.style.paint:
            surface = _opaque_color(own)
            if surface is not None:
                backdrop = surface
        box.extra["backdrop"] = backdrop
        for child in box.children:
            self._annotate_backdrop(child, backdrop)

    # -- flow ------------------------------------------------------------
    def _flow_items(self, node, style, inner_width, inner_height):
        """Split children into block items and anonymous inline groups.

        Text nodes that belong to ``node`` itself join the surrounding inline
        group, exactly like a browser's anonymous inline boxes.
        """
        items = []
        pending = []
        context = {"content_width": inner_width, "content_height": inner_height or self.slide_height}

        def flush():
            if pending:
                items.append(_Item("inline", nodes=list(pending)))
                pending.clear()

        for child in node.child_nodes:
            if not child.tag_name:
                if child.text and child.text.strip():
                    pending.append((child, style))
                continue
            child_style = build_style(child, self.resolver, context, style)
            if child_style.display == "none":
                continue
            if child_style.position in ("absolute", "fixed"):
                flush()
                continue
            if self._is_inline_level(child, child_style):
                pending.append((child, child_style))
                continue
            flush()
            items.append(_Item("block", node=child, style=child_style))
        flush()
        return items

    def _is_inline_level(self, node, style):
        display = style.display
        if display in ("inline", "inline-block"):
            return True
        if display in ("block", "flex", "grid", "list-item", "table", "table-row", "table-cell"):
            return False
        return node.tag_name in INLINE_TAGS or node.tag_name in REPLACED_INLINE

    def _layout_flow(self, node, style, x, y, width, height):
        """Lay out the children of ``node`` and return a flat list of boxes."""
        items = self._flow_items(node, style, width, height)
        boxes = []
        cursor = y
        if style.display == "flex":
            boxes.extend(self._layout_flex(items, style, x, y, width, height))
        elif style.display == "grid":
            boxes.extend(self._layout_grid(items, style, x, y, width, height))
        else:
            for item in items:
                if item.kind == "block":
                    margin = item.style.margin
                    box = self.layout_element(
                        item.node, item.style, x, cursor, width, content_height_base=height
                    )
                    if box is None:
                        continue
                    boxes.append(box)
                    cursor = box.bottom + margin[2] + style.gap_row
                else:
                    produced, row_height = self._layout_inline_nodes(item.nodes, style, x, cursor, width)
                    boxes.extend(produced)
                    cursor += row_height + style.gap_row
        # absolutely positioned children sit on top of everything else
        position_context = {"content_width": width, "content_height": height or self.slide_height}
        for child in node.element_children():
            child_style = build_style(child, self.resolver, position_context, style)
            if child_style.position in ("absolute", "fixed") and child_style.display != "none":
                absolute = self._layout_absolute(child, child_style, x, y, width, height)
                if absolute is not None:
                    absolute.z = max(absolute.z, 10)
                    boxes.append(absolute)
        return [box for box in boxes if box is not None]

    # -- inline groups ---------------------------------------------------
    def _layout_inline_nodes(self, nodes, parent_style, x, y, width):
        """Lay out an anonymous inline group; returns (boxes, height)."""
        runs = []
        simple = True
        for node, style in nodes:
            if not node.tag_name:
                if node.text:
                    runs.append((node.text, style))
                continue
            if node.tag_name == "br":
                runs.append(("\n", style))
                continue
            if node.tag_name in INLINE_TAGS:
                runs.extend(self._runs_of(node, style))
                continue
            simple = False
            break
        if simple:
            if not runs:
                return [], 0.0
            box = self._text_box(None, parent_style, x, y, width, runs)
            return [box], box.height
        return self._layout_row(nodes, parent_style, x, y, width)

    def _layout_row(self, nodes, parent_style, x, y, width, gap=None, align_items="start"):
        produced = []
        cursor_x = x
        line_top = y
        line_height = 0.0
        pending = []
        gap = parent_style.gap_col if gap is None else gap

        def flush_text():
            nonlocal cursor_x, line_height, line_top
            if not pending:
                return
            runs = []
            for node, style in pending:
                if not node.tag_name:
                    if node.text:
                        runs.append((node.text, style))
                    continue
                runs.extend(self._runs_of(node, style))
            pending.clear()
            if not runs:
                return
            available = max(8.0, x + width - cursor_x)
            if cursor_x > x and available < 24:
                cursor_x = x
                line_top += line_height + gap
                line_height = 0.0
                available = width
            box = self._text_box(None, parent_style, cursor_x, line_top, available, runs)
            produced.append(box)
            cursor_x += box.width + gap
            line_height = max(line_height, box.height)

        for node, style in nodes:
            if not node.tag_name or node.tag_name in INLINE_TAGS:
                pending.append((node, style))
                continue
            flush_text()
            box = self.layout_element(node, style, cursor_x, line_top, width)
            if box is None:
                continue
            if cursor_x > x and cursor_x + box.width > x + width + 0.5:
                line_top += line_height + gap
                cursor_x = x
                line_height = 0.0
            box.shift(cursor_x - box.x, line_top - box.y)
            produced.append(box)
            cursor_x += box.width + style.margin[1] + style.margin[3] + gap
            line_height = max(line_height, box.height + style.margin[0] + style.margin[2])
        flush_text()
        if align_items in ("center", "end") and produced:
            for box in produced:
                offset = (line_height - box.height) / 2.0 if align_items == "center" else line_height - box.height
                if offset > 0.5:
                    box.shift(0.0, offset)
        return produced, line_height

    def _runs_of(self, node, style):
        """Collect (text, style) runs, descending through inline children."""
        runs = []
        for child in node.child_nodes:
            if not child.tag_name:
                if child.text:
                    runs.append((child.text, style))
                continue
            if child.tag_name == "br":
                runs.append(("\n", style))
                continue
            if child.tag_name in ("style", "script"):
                continue
            child_style = build_style(child, self.resolver, {"content_width": 0, "content_height": 0}, style)
            if child_style.display == "none":
                continue
            if child.tag_name in ("img", "svg"):
                continue
            runs.extend(self._runs_of(child, child_style))
        return runs

    def _text_box(self, node, style, x, y, width, runs, align=None):
        lines = self.text_engine.wrap(runs, width)
        height = sum(line.height for line in lines)
        text_style = style
        if align:
            text_style = _clone_style(style, text_align=align)
        box = LayoutBox(node, text_style, (x, y, width, height), kind="text")
        box.lines = lines
        box.text = "".join(text for line in lines for text, _s, _w in line.runs)
        if getattr(style, "is_list", False):
            marker = (style.list_style or "disc").lower()
            autonum = AUTONUM_FOR_STYLE.get(marker)
            if autonum:
                # Ordered list: let PowerPoint number the items itself. The start
                # value is resolved while the <li> still has its <ol> parent in
                # scope (the text box is built from an anonymous run node).
                box.extra["autonum"] = autonum
                box.extra["bullet_start"] = getattr(style, "list_start", 1) or 1
            else:
                box.extra["bullet"] = BULLET_FOR_STYLE.get(marker, "•")
        if node is not None and node.attr("data-nowrap") is not None:
            box.extra["nowrap"] = True
        return box

    def _mark_nowrap(self, box, node):
        """Single-line chips must not be re-wrapped by the PPTX writer."""
        if box is not None and node is not None and node.tag_name not in BLOCK_TAGS:
            box.extra.setdefault("nowrap", True)
        return box

    # -- one element ------------------------------------------------------
    def layout_element(self, node, style, x, y, available_width, fixed_height=None,
                       content_height_base=None):
        margin = style.margin
        width = style.width
        if width is None:
            width = available_width - margin[1] - margin[3]
        elif isinstance(width, Percent):
            width = (available_width - margin[1] - margin[3]) * float(width)
        width = max(1.0, width)
        if style.min_width:
            width = max(width, style.min_width)
        if style.max_width:
            width = min(width, style.max_width)

        left = x + margin[3]
        top = y + margin[0]
        border_w = style.horizontal_border
        border_h = style.vertical_border
        inner_width = max(1.0, width - style.horizontal_padding - border_w)

        height = fixed_height
        explicit_height = None
        if style.height is not None:
            if isinstance(style.height, Percent):
                # A percentage height resolves against the *containing block*, not
                # the canvas: a 50% box inside a 300px card is 112.5pt, not 270pt.
                base = fixed_height if fixed_height else (content_height_base or self.slide_height)
                explicit_height = base * float(style.height)
            else:
                explicit_height = style.height
        if explicit_height is None and style.aspect_ratio:
            # height = width / ratio, so aspect-ratio alone can size a box.
            explicit_height = inner_width / style.aspect_ratio
        if height is None:
            height = explicit_height
        inner_height = None
        if height is not None:
            inner_height = max(0.0, height - style.vertical_padding - border_h)

        content_x = left + style.padding[3] + (style.border[3].width if style.border and style.border[3] else 0.0)
        content_y = top + style.padding[0] + (style.border[0].width if style.border and style.border[0] else 0.0)

        if node.tag_name == "img":
            return self._image_box(node, style, left, top, width, inner_height)
        if node.tag_name == "svg":
            return self._svg_box(node, style, left, top, width, inner_height)
        if node.tag_name == "table":
            return self._table_box(node, style, left, top, width, inner_height)

        box = LayoutBox(node, style, (left, top, width, 0.0), kind="block")
        children = self._layout_flow(node, style, content_x, content_y, inner_width, inner_height)
        box.children = self._stack(children)

        used = 0.0
        if box.children:
            used = max(child.bottom for child in box.children) - content_y
        if inner_height is not None:
            content_height = inner_height
        else:
            content_height = max(used, 0.0)
        height = content_height + style.vertical_padding + border_h
        if inner_height is None and style.min_height:
            height = max(height, style.min_height)
        if explicit_height is not None:
            height = max(height, explicit_height)
        if style.max_height:
            height = min(height, style.max_height)

        box.rect = (left, top, width, height)
        box.content_rect = (
            content_x,
            content_y,
            inner_width,
            max(0.0, height - style.vertical_padding - border_h),
        )
        self._apply_translate(box)
        self._vertical_align(box)
        self._check_overflow(box)
        return box

    def _apply_translate(self, box):
        """Shift a box by its ``transform: translate()`` once its size is known.

        Percentage components (``translateX(-50%)``) are resolved here because
        they are a fraction of the element's *own* box, which only exists now.
        """
        transform = getattr(box.style, "transform", None) or {}
        raw = transform.get("translate")
        if not raw:
            return
        offset_x, offset_y = values.resolve_translate(transform, box.width, box.height)
        if abs(offset_x) < 0.01 and abs(offset_y) < 0.01:
            return
        box.shift(offset_x, offset_y)

    def _vertical_align(self, box):
        """Honour vertical-align / flex justify on fixed-height containers."""
        style = box.style
        content_height = box.content_rect[3]
        if not box.children or content_height <= 0:
            return
        used = max(child.bottom for child in box.children) - box.content_rect[1]
        free = content_height - used
        if free <= 0.5:
            return
        anchor = None
        if style.display == "flex" and style.flex_direction.startswith("column"):
            if style.justify_content == "space-center":
                anchor = "middle"
            elif style.justify_content == "end":
                anchor = "bottom"
        elif style.display != "flex":
            if style.vertical_align in ("middle", "center"):
                anchor = "middle"
            elif style.vertical_align in ("bottom", "end"):
                anchor = "bottom"
        if anchor == "middle":
            for child in box.children:
                child.shift(0.0, free / 2.0)
        elif anchor == "bottom":
            for child in box.children:
                child.shift(0.0, free)

    def _check_overflow(self, box):
        if box.node is None or box.children is None:
            return
        content_height = box.content_rect[3]
        if content_height <= 0:
            return
        used = max((child.bottom for child in box.children), default=box.content_rect[1]) - box.content_rect[1]
        if used > content_height + 1.0 and box.style.overflow in ("hidden", "auto", "scroll"):
            for child in box.children:
                child.extra["clipped"] = True
        if used > content_height + 1.0:
            label = (box.node.text() if box.node is not None else "")[:28]
            self.warnings.append(
                f"content overflow ({used - content_height:.0f}pt) in <{box.node.tag_name}> {label}"
            )

    # -- flex -------------------------------------------------------------
    def _layout_flex(self, items, style, x, y, width, height):
        blocks = [item for item in items if item.kind == "block"]
        inline_items = [item for item in items if item.kind == "inline"]
        if inline_items and not blocks:
            nodes = [node for item in inline_items for node in item.nodes]
            produced = self._layout_row(nodes, style, x, y, width) if any(
                node.tag_name in REPLACED_INLINE or (st.display == "inline-block") for node, st in nodes
            ) else ([], 0.0)
            if produced[0]:
                return produced[0]
            runs = []
            for node, node_style in nodes:
                runs.extend(self._runs_of(node, node_style))
            return [self._text_box(None, style, x, y, width, runs)] if runs else []
        is_column = style.flex_direction.startswith("column")
        ordered = list(reversed(blocks)) if style.flex_direction.endswith("reverse") else blocks
        if not ordered:
            return []
        gap = style.gap_row if is_column else style.gap_col
        if is_column:
            return self._flex_column(ordered, style, x, y, width, height, gap)
        return self._flex_row(ordered, style, x, y, width, height, gap)

    def _flex_row(self, items, style, x, y, width, height, gap):
        fixed = 0.0
        flexible = []
        for item in items:
            margins = item.style.margin[1] + item.style.margin[3]
            fixed += margins
            if item.style.width is not None and item.style.width > 1.0:
                fixed += item.style.width
            else:
                flexible.append(item)
        free = width - gap * max(0, len(items) - 1) - fixed
        weights = {id(item): (item.style.flex_grow or 1.0) for item in flexible}
        total_weight = sum(weights.values()) or 1.0
        widths = []
        for item in items:
            if id(item) in weights:
                widths.append(max(0.0, free) * weights[id(item)] / total_weight)
            else:
                widths.append(item.style.width)

        measured = []
        cursor = x
        for item, main in zip(items, widths):
            margin_left = item.style.margin[3]
            box = self.layout_element(item.node, item.style, cursor + margin_left, y, main)
            if box is None:
                cursor += main + item.style.margin[1] + item.style.margin[3] + gap
                continue
            measured.append((item, box, main))
            cursor += main + item.style.margin[1] + item.style.margin[3] + gap

        if not measured:
            return []
        row_height = height
        if row_height is None:
            row_height = max(box.height + item.style.margin[0] + item.style.margin[2] for item, box, _m in measured)
        row_height = max(row_height, 0.0)

        produced = []
        for item, box, main in measured:
            align = item.style.align_self or style.align_items
            own = box.height + item.style.margin[0] + item.style.margin[2]
            if align == "stretch" and height is not None and box.style.height is None:
                target = max(0.0, row_height - item.style.margin[0] - item.style.margin[2])
                rebuilt = self.layout_element(item.node, item.style, box.x, box.y, main, fixed_height=target)
                box = rebuilt or box
            elif align == "center":
                box.shift(0.0, (row_height - own) / 2.0)
            elif align == "end":
                box.shift(0.0, row_height - own)
            produced.append(box)
        return produced

    def _flex_column(self, items, style, x, y, width, height, gap):
        measured = []
        cursor = y
        for item in items:
            target_width = item.style.width if (item.style.width or 0) > 1.0 else width
            box = self.layout_element(item.node, item.style, x, cursor, target_width)
            if box is None:
                continue
            measured.append(box)
            cursor = box.bottom + gap
        if not measured:
            return []
        if height is not None and height > 0:
            used = sum(box.height for box in measured) + gap * max(0, len(measured) - 1)
            free = height - used
            if free > 0:
                if style.justify_content == "space-center":
                    for box in measured:
                        box.shift(0.0, free / 2.0)
                elif style.justify_content == "end":
                    for box in measured:
                        box.shift(0.0, free)
                elif style.justify_content == "space-between" and len(measured) > 1:
                    step = free / (len(measured) - 1)
                    for index, box in enumerate(measured):
                        box.shift(0.0, step * index)
        for index, item in enumerate(items):
            align = item.style.align_self or style.align_items
            if index >= len(measured):
                break
            box = measured[index]
            target_width = item.style.width if (item.style.width or 0) > 1.0 else None
            if target_width is None and align == "stretch":
                continue
            if align == "center":
                box.shift((width - box.width) / 2.0, 0.0)
            elif align == "end":
                box.shift(width - box.width, 0.0)
        return measured

    # -- grid -------------------------------------------------------------
    def _layout_grid(self, items, style, x, y, width, height):
        blocks = [item for item in items if item.kind == "block"]
        if not blocks:
            return []
        columns = values.parse_track_list(style.grid_columns or "", size=width, gap=style.gap_col)
        if not columns:
            columns = [width]
        cells = _place_grid_cells(blocks, len(columns))
        rows = max((row for row, _col, _item, _span, _rspan in cells), default=-1) + 1
        if rows <= 0:
            return []

        def column_x(index):
            return x + sum(columns[:index]) + style.gap_col * index

        def span_width(index, span):
            span = max(1, min(span, len(columns) - index)) if len(columns) > index else 1
            total = sum(columns[index:index + span])
            return total + style.gap_col * (span - 1)

        # Pass 1: measure each cell at the grid's origin to find row heights.
        row_heights = [0.0] * rows
        for row, col, item, span, _rspan in cells:
            probe = self.layout_element(
                item.node, item.style, column_x(col), y, span_width(col, span)
            )
            if probe is not None:
                row_heights[row] = max(row_heights[row], probe.height)

        total_height = sum(row_heights) + style.gap_row * max(0, rows - 1)
        offset = y
        if height is not None and height > total_height and style.align_content != "start":
            free = height - total_height
            if style.align_content == "center":
                offset += free / 2.0
            elif style.align_content == "end":
                offset += free
            elif style.align_content == "space-between" and rows > 1:
                style = _clone_style(style, gap_row=style.gap_row + free / (rows - 1))

        row_offsets = []
        cursor = offset
        for row_index in range(rows):
            row_offsets.append(cursor)
            cursor += row_heights[row_index] + style.gap_row

        # Pass 2: lay out again at the final row offset with the final height, so
        # children land where they are drawn (a stretched card re-centres its
        # content, a tall neighbour does not shift this cell's text).
        produced = []
        for row, col, item, span, rspan in cells:
            row_height = sum(row_heights[row:row + rspan])
            row_height += style.gap_row * max(0, rspan - 1)
            align = item.style.align_self or style.align_items
            fixed_height = row_height if align == "stretch" else None
            box = self.layout_element(
                item.node, item.style, column_x(col), row_offsets[row],
                span_width(col, span), fixed_height=fixed_height,
                content_height_base=height,
            )
            if box is None:
                continue
            if fixed_height is None and rspan == 1:
                box.rect = (box.rect[0], box.rect[1], box.rect[2], max(box.height, row_height))
            produced.append(box)
        return produced

    # -- absolute ---------------------------------------------------------
    def _layout_absolute(self, node, style, x, y, width, height):
        box_width = style.width
        shrink = False
        if box_width is None:
            if style.left is not None and style.right is not None:
                box_width = width - style.left - style.right
            else:
                box_width = self._shrink_width(node, style, width)
                shrink = True
        elif isinstance(box_width, Percent):
            box_width = width * float(box_width)
        box_height = style.height
        if box_height is None and style.top is not None and style.bottom is not None:
            box_height = height - style.top - style.bottom
        elif isinstance(box_height, Percent):
            box_height = (height or self.slide_height) * float(box_height)

        pos_x = x + (style.left or 0.0)
        if style.left is None and style.right is not None:
            pos_x = x + width - style.right - box_width
        pos_y = y + (style.top or 0.0)
        if style.top is None and style.bottom is not None:
            probe = self.layout_element(node, style, pos_x, pos_y, box_width, box_height)
            measured = probe.height if probe is not None else (box_height or 0.0)
            pos_y = y + (height or self.slide_height) - style.bottom - measured
        box = self.layout_element(node, style, pos_x, pos_y, box_width, box_height)
        if box is not None and shrink:
            # A shrink-to-fit chip or folio must never wrap: it has no column to
            # wrap into, so the writer is told to widen the frame instead.
            self._mark_nowrap_tree(box)
        return box

    def _mark_nowrap_tree(self, box):
        if box.kind == "text":
            box.extra["nowrap"] = True
        for child in box.children:
            self._mark_nowrap_tree(child)

    def _shrink_width(self, node, style, available):
        has_block = any(
            not self._is_inline_level(child, build_style(child, self.resolver, {
                "content_width": available, "content_height": 0
            }, style))
            for child in node.element_children()
        )
        if has_block or node.tag_name in ("img", "table", "svg"):
            return available
        runs = self._runs_of(node, style)
        text = "".join(text for text, _s in runs)
        if not text.strip():
            return style.horizontal_padding + style.horizontal_border
        widest = 0.0
        for line in text.split("\n"):
            # Measure the *rendered* text: text-transform can widen a line
            # (uppercase), and an absolutely positioned chip must still fit.
            widest = max(widest, self.text_engine.width(_transform(line, style), style))
        total = widest + style.horizontal_padding + style.horizontal_border
        # PowerPoint wraps text slightly wider than the browser metric; leave a
        # few points of slack so a "shrink to fit" chip never breaks in two.
        width = min(available, max(1.0, total * 1.06 + 2.0))
        return width

    # -- replaced elements -------------------------------------------------
    def _image_box(self, node, style, x, y, width, height):
        src = node.attr("src") or ""
        box = LayoutBox(node, style, (x, y, width, height or width * 0.5625), kind="image")
        box.image_src = src
        intrinsic = self._image_size(src)
        if intrinsic:
            box.extra["intrinsic"] = intrinsic
            if height is None:
                ratio = intrinsic[1] / intrinsic[0] if intrinsic[0] else 0.5625
                box.rect = (x, y, width, width * ratio)
        box.extra["fit"] = style.object_fit
        return box

    def _svg_box(self, node, style, x, y, width, height):
        raw_view = node.attr("viewBox") or node.attr("viewbox") or "0 0 24 24"
        numbers = [float(value) for value in re.split(r"[\s,]+", raw_view.strip()) if _is_number(value)]
        if len(numbers) != 4 or not numbers[2] or not numbers[3]:
            numbers = [0.0, 0.0, 24.0, 24.0]
        aspect = numbers[3] / numbers[2]
        box_height = height if height else width * aspect
        box = LayoutBox(node, style, (x, y, width, box_height), kind="svg")
        box.svg_node = node
        box.extra["viewbox"] = numbers
        return box

    def _table_box(self, node, style, x, y, width, height):
        rows = []
        header_rows = 0
        for child in node.element_children():
            if child.tag_name == "thead":
                for row in child.element_children():
                    if row.tag_name == "tr":
                        rows.append(row)
                        header_rows += 1
            elif child.tag_name == "tbody":
                for row in child.element_children():
                    if row.tag_name == "tr":
                        rows.append(row)
            elif child.tag_name == "tr":
                rows.append(child)
        if not rows:
            return None
        columns = max(
            sum(_colspan(cell) for cell in row.element_children() if cell.tag_name in ("td", "th"))
            for row in rows
        )
        if columns <= 0:
            return None
        table = {"rows": [], "styles": [], "spans": [], "header_rows": header_rows}
        content_widths = [0.0] * columns
        for row in rows:
            cells = []
            styles = []
            spans = []
            column = 0
            for cell in row.element_children():
                if cell.tag_name not in ("td", "th"):
                    continue
                cell_style = build_style(cell, self.resolver, {
                    "content_width": width / columns, "content_height": 0
                }, style)
                span = _colspan(cell)
                cells.append(cell)
                styles.append(cell_style)
                spans.append(span)
                runs = self._runs_of(cell, cell_style)
                text_width = max(
                    (self.text_engine.width(line, cell_style) for line, _s in [(t, cell_style) for t in "".join(
                        text for text, _s in runs if text
                    ).split("\n")]),
                    default=0.0,
                )
                target = min(column, columns - 1)
                content_widths[target] = max(content_widths[target], text_width / max(1, span))
                column += span
            table["rows"].append(cells)
            table["styles"].append(styles)
            table["spans"].append(spans)

        widths = []
        for value in content_widths:
            widths.append(max(40.0, value + 20.0))
        total = sum(widths) or 1.0
        if total < width:
            scale = width / total
            widths = [value * scale for value in widths]
        else:
            scale = width / total
            widths = [value * scale for value in widths]
        table["column_widths"] = widths

        row_heights = []
        for row_index, cells in enumerate(table["rows"]):
            tallest = 0.0
            for column_index, cell in enumerate(cells):
                cell_style = table["styles"][row_index][column_index]
                span = table["spans"][row_index][column_index]
                cell_width = sum(widths[column_index:column_index + span]) or widths[-1]
                runs = self._runs_of(cell, cell_style)
                lines = self.text_engine.wrap(runs, max(8.0, cell_width - 12.0))
                tallest = max(
                    tallest,
                    sum(line.height for line in lines) + cell_style.padding[0] + cell_style.padding[2] + 2.0,
                )
            row_heights.append(max(tallest, table["styles"][row_index][0].font_size * 1.9))
        table["row_heights"] = row_heights

        box = LayoutBox(node, style, (x, y, width, sum(row_heights)), kind="table")
        box.table = table
        return box

    def _image_size(self, src):
        if not src or src.startswith(("http://", "https://", "data:")):
            return None
        if src in self._image_cache:
            return self._image_cache[src]
        path = self.resolve_asset(src)
        size = None
        if path and os.path.exists(path):
            try:
                from PIL import Image

                with Image.open(path) as image:
                    size = image.size
            except Exception:
                size = None
        self._image_cache[src] = size
        return size

    def resolve_asset(self, src):
        if not src:
            return None
        if os.path.isabs(src):
            return src if os.path.exists(src) else None
        for candidate in (
            os.path.join(self.base_dir, src),
            os.path.join(self.base_dir, "assets", src),
            os.path.join(self.base_dir, "..", src),
        ):
            if os.path.exists(candidate):
                return os.path.normpath(candidate)
        return None


def _opaque_color(background):
    """The flat colour a background actually paints, or None if not flat."""
    if background is None:
        return None
    if background.gradients or background.image:
        return None
    if background.color is None:
        return None
    if util.alpha_of(background.color) < 0.999:
        return None
    return background.color


def _place_grid_cells(blocks, column_count):
    """Resolve grid placement into ``(row, column, item, colspan, rowspan)``.

    Explicit ``grid-column: 2`` / ``grid-row: 1`` / ``span N`` are honoured, then
    the remaining items fill the first free cell in source order (CSS auto
    placement, row-major).
    """
    taken = {}
    placed = []
    pending = []
    for item in blocks:
        start, span = getattr(item.style, "grid_column", (None, 1))
        row_start, rowspan = getattr(item.style, "grid_row", (None, 1))
        if start is None and row_start is None:
            pending.append((item, span, rowspan))
            continue
        row = (row_start - 1) if row_start else 0
        column = (start - 1) if start else 0
        if start is None:
            while any((row, column + offset) in taken for offset in range(span)):
                column += 1
        while True:
            clash = False
            for row_offset in range(rowspan):
                for column_offset in range(span):
                    if (row + row_offset, column + column_offset) in taken:
                        clash = True
            if not clash:
                break
            if start is None:
                column += 1
            else:
                row += 1
        for row_offset in range(rowspan):
            for column_offset in range(span):
                taken[(row + row_offset, column + column_offset)] = item
        placed.append((row, column, item, span, rowspan))

    row = 0
    column = 0
    for item, span, rowspan in pending:
        while True:
            if column + span > column_count:
                row += 1
                column = 0
                continue
            clash = any(
                (row + row_offset, column + column_offset) in taken
                for row_offset in range(rowspan)
                for column_offset in range(span)
            )
            if not clash:
                break
            column += 1
        for row_offset in range(rowspan):
            for column_offset in range(span):
                taken[(row + row_offset, column + column_offset)] = item
        placed.append((row, column, item, span, rowspan))
        column += span

    placed.sort(key=lambda entry: (entry[0], entry[1]))
    return placed


def _colspan(cell):
    raw = cell.attr("colspan") or "1"
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _list_start(node):
    """``<ol start="5">`` -> 5; anything else -> 1.

    The ``start`` attribute lives on the list element, not on the ``<li>`` that
    carries the bullet, so walk up until a list is found.
    """
    current = node
    depth = 0
    while current is not None and depth < 4:
        if getattr(current, "tag_name", None) in ("ol", "ul"):
            raw = current.attr("start")
            try:
                return max(0, int(raw)) if raw else 1
            except (TypeError, ValueError):
                return 1
        current = getattr(current, "parent_node", None)
        depth += 1
    return 1


def _clone_style(style, **overrides):
    clone = Style()
    for slot in Style.__slots__:
        setattr(clone, slot, getattr(style, slot))
    for key, value in overrides.items():
        setattr(clone, key, value)
    return clone


def _is_number(text):
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False
