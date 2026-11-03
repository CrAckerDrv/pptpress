"""Inline SVG -> native DrawingML shapes.

Decorative SVG (bars, rings, arrows, illustrations) is converted into real
PowerPoint shapes with custom geometry, so a deck never contains a flattened
picture where a vector could be edited.

Only the geometric subset used by the pattern library is supported:

* ``rect`` (+ ``rx``/``ry``), ``circle``, ``ellipse``, ``line``,
  ``polyline``, ``polygon`` and ``path`` (M/L/H/V/C/S/Q/T/A/Z, absolute and
  relative)
* solid ``fill``/``stroke`` with ``stroke-width``, ``stroke-linecap``,
  ``fill-opacity``/``stroke-opacity``/``opacity`` and ``<g>`` inheritance
* ``transform="translate(...) scale(...) rotate(...)"`` on groups
* ``<linearGradient>`` referenced by ``fill="url(#id)"``

Anything outside that subset raises :class:`Unsupported`, and the caller falls
back to rasterising the icon.
"""

from __future__ import annotations

import math
import re

from lxml import etree

from . import util

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_IDENT = re.compile(r"[A-Za-z]")


class Unsupported(Exception):
    """Raised when an SVG feature cannot be expressed as native shapes."""


# --------------------------------------------------------------------------
# data model
# --------------------------------------------------------------------------
class SvgShape:
    """One painted SVG primitive in viewBox coordinates."""

    __slots__ = ("commands", "closed", "fill", "stroke", "stroke_width", "opacity",
                 "linecap", "gradient", "tag", "rx", "ry", "x", "y", "w", "h")

    def __init__(self):
        self.commands = []      # [("M", (x, y)), ("L", (x, y)), ("C", (x1,y1,x2,y2,x,y)), ("Z", ())]
        self.closed = False
        self.fill = None
        self.stroke = None
        self.stroke_width = 0.0
        self.opacity = 1.0
        self.linecap = "butt"
        self.gradient = None    # list[(offset, color)]
        self.tag = ""
        self.rx = 0.0
        self.ry = 0.0
        self.x = self.y = self.w = self.h = 0.0


class SvgDocument:
    def __init__(self, width, height, shapes, viewbox):
        self.width = width
        self.height = height
        self.shapes = shapes
        self.viewbox = viewbox


class SvgText:
    """An SVG ``<text>`` element: becomes a native, editable text box.

    Charts and diagrams put their labels inside the SVG. Keeping those labels as
    real text (rather than dropping or rasterising them) is what makes the
    exported chart editable: the numbers and titles can be typed over.
    """

    __slots__ = ("lines", "x", "y", "size", "color", "weight", "anchor", "family",
                 "opacity", "italic", "x_values")

    def __init__(self):
        self.lines = []
        self.x = 0.0
        self.y = 0.0
        self.size = 12.0
        self.color = (0, 0, 0, 1.0)
        self.weight = 400
        self.anchor = "start"
        self.family = "Inter"
        self.opacity = 1.0
        self.italic = False
        self.x_values = []


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def parse(raw):
    """Parse an inline SVG string into :class:`SvgDocument`."""
    if isinstance(raw, str):
        raw_bytes = raw.encode("utf-8")
    else:
        raw_bytes = raw
    root = etree.fromstring(raw_bytes)
    if etree.QName(root).localname != "svg":
        raise Unsupported("root element is not <svg>")
    viewbox = _viewbox(root)
    gradients = _gradients(root)
    shapes = []
    # The root <svg> carries the presentation attributes that every child
    # inherits (usually ``fill="none" stroke="currentColor" stroke-width="2"``).
    seed = _inherited(root, {})
    _walk(root, _Transform(), shapes, gradients, seed)
    if not shapes:
        raise Unsupported("no drawable shapes")
    return SvgDocument(viewbox[2], viewbox[3], shapes, viewbox)


def _inherited(element, inherited):
    """Merge one element's presentation attributes over ``inherited``."""
    style = _style_of(element)
    own = dict(inherited)
    current = _attr(element, style, "color")
    if current is not None:
        own["color"] = current
    for key in ("fill", "stroke", "stroke-width", "opacity", "fill-opacity",
                "stroke-opacity", "stroke-linecap", "stroke-linejoin"):
        value = _attr(element, style, key)
        if value is not None:
            own[key] = value
    return own


def _viewbox(root):
    raw = root.get("viewBox") or root.get("viewbox")
    if raw:
        values = [float(v) for v in _NUM.findall(raw)]
        if len(values) == 4 and values[2] > 0 and values[3] > 0:
            return values
    width = _NUM.findall(root.get("width") or "24")
    height = _NUM.findall(root.get("height") or "24")
    try:
        return [0.0, 0.0, float(width[0]), float(height[0])]
    except (IndexError, ValueError):
        return [0.0, 0.0, 24.0, 24.0]


class _Transform:
    """2x3 affine transform: x' = a*x + c*y + e ; y' = b*x + d*y + f."""

    __slots__ = ("a", "b", "c", "d", "e", "f")

    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
        self.a, self.b, self.c, self.d, self.e, self.f = a, b, c, d, e, f

    def apply(self, x, y):
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def multiply(self, other):
        return _Transform(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def scale_factor(self):
        return math.sqrt(abs(self.a * self.d - self.b * self.c)) or 1.0


def _parse_transform(text):
    if not text:
        return _Transform()
    result = _Transform()
    for name, args in re.findall(r"([A-Za-z]+)\(([^()]*)\)", text):
        numbers = [float(v) for v in _NUM.findall(args)]
        name = name.lower()
        if name == "translate":
            tx = numbers[0] if numbers else 0.0
            ty = numbers[1] if len(numbers) > 1 else 0.0
            result = result.multiply(_Transform(1, 0, 0, 1, tx, ty))
        elif name == "scale":
            sx = numbers[0] if numbers else 1.0
            sy = numbers[1] if len(numbers) > 1 else sx
            result = result.multiply(_Transform(sx, 0, 0, sy, 0, 0))
        elif name == "rotate":
            angle = math.radians(numbers[0]) if numbers else 0.0
            cos, sin = math.cos(angle), math.sin(angle)
            rotation = _Transform(cos, sin, -sin, cos, 0, 0)
            if len(numbers) >= 3:
                cx, cy = numbers[1], numbers[2]
                rotation = _Transform(1, 0, 0, 1, cx, cy).multiply(rotation).multiply(
                    _Transform(1, 0, 0, 1, -cx, -cy)
                )
            result = result.multiply(rotation)
        elif name == "matrix" and len(numbers) >= 6:
            result = result.multiply(_Transform(*numbers[:6]))
        elif name in ("skewx", "skewy"):
            raise Unsupported(f"transform {name} is not supported")
    return result


def _gradients(root):
    gradients = {}
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        local = etree.QName(element).localname
        if local not in ("linearGradient", "radialGradient"):
            continue
        ident = element.get("id")
        if not ident:
            continue
        stops = []
        for stop in element:
            if etree.QName(stop).localname != "stop":
                continue
            offset = _parse_offset(stop.get("offset") or "0")
            color = _paint(stop.get("stop-color") or "#000000")
            opacity = _number(stop.get("stop-opacity"), 1.0)
            if color is not None and opacity < 1:
                color = util.with_alpha(color, util.alpha_of(color) * opacity)
            if color is not None:
                stops.append((offset, color))
        if len(stops) >= 2:
            gradients[ident] = stops
    return gradients


def _parse_offset(text):
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _number(text, default=0.0):
    if text is None:
        return default
    values = _NUM.findall(str(text))
    return float(values[0]) if values else default


def _style_of(element):
    style = {}
    raw = element.get("style") or ""
    for part in raw.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            style[key.strip().lower()] = value.strip()
    return style


def _attr(element, style, key, default=None):
    if key in style:
        return style[key]
    return element.get(key, default)


def _paint_fill(text, current="#000000"):
    if text is None:
        return None
    raw = text.strip()
    if raw in ("", "none"):
        return None
    if raw == "currentColor":
        return util.parse_color(current)
    match = re.match(r"^url\(\s*#([^)\s]+)\s*\)$", raw)
    if match:
        return None
    return util.parse_color(raw)


def _paint(text, current="#000000"):
    return _paint_fill(text, current)


def _walk(element, transform, shapes, gradients, inherited):
    for child in element:
        if not isinstance(child.tag, str):
            continue
        local = etree.QName(child).localname
        if local in ("defs", "title", "desc", "metadata", "style", "linearGradient", "radialGradient", "clipPath"):
            continue
        own = _inherited(child, inherited)
        child_transform = transform.multiply(_parse_transform(child.get("transform")))
        if local == "g":
            _walk(child, child_transform, shapes, gradients, own)
            continue
        if local == "text":
            labels = _make_text(child, own)
            for label in labels:
                _transform_text(label, child_transform)
                shapes.append(label)
            continue
        shape = _make_shape(local, child, gradients, own)
        if shape is None:
            continue
        _transform_shape(shape, child_transform)
        shapes.append(shape)


def _make_text(element, inherited):
    """Convert an SVG ``<text>`` into one label (or one per ``<tspan>``).

    Each label becomes its own editable text box, so a chart's axis ticks,
    series names and value callouts remain typeable in PowerPoint.
    """
    style = _style_of(element)
    base_x = _number(element.get("x"), 0.0)
    base_y = _number(element.get("y"), 0.0)
    font_size = _number(_attr(element, style, "font-size"), 12.0)
    raw_weight = str(_attr(element, style, "font-weight") or "400").strip().lower()
    bold = raw_weight in ("bold", "bolder", "600", "700", "800", "900")
    italic = str(_attr(element, style, "font-style") or "").strip().lower() in ("italic", "oblique")
    anchor = str(_attr(element, style, "text-anchor") or "start").strip()
    family = _attr(element, style, "font-family")
    family = family.split(",")[0].strip().strip("'\"") if family else "Inter"
    fill_raw = _attr(element, style, "fill") or "currentColor"
    color = _paint_fill(fill_raw, inherited.get("color", "#000000"))
    color = color or util.parse_color(inherited.get("color", "#000000")) or (0, 0, 0, 1.0)
    opacity = _number(_attr(element, style, "opacity"), 1.0)

    labels = []

    def make(text, x, y):
        label = SvgText()
        label.lines = [" ".join(text.split())]
        label.x = x
        label.y = y
        label.size = font_size
        label.color = color
        label.weight = 700 if bold else 400
        label.italic = italic
        label.anchor = anchor
        label.family = family
        label.opacity = opacity
        labels.append(label)

    if element.text and element.text.strip():
        make(element.text, base_x, base_y)
    for child in element:
        if not isinstance(child.tag, str):
            continue
        if etree.QName(child).localname != "tspan":
            continue
        if child.text and child.text.strip():
            make(child.text, _number(child.get("x"), base_x), _number(child.get("y"), base_y))
    return labels


def _transform_text(label, transform):
    label.x, label.y = transform.apply(label.x, label.y)
    label.size *= transform.scale_factor()


def _make_shape(tag, element, gradients, inherited):
    fill_raw = inherited.get("fill", "#000000")
    stroke_raw = inherited.get("stroke", "none")
    shape = SvgShape()
    shape.tag = tag
    shape.opacity = _number(inherited.get("opacity"), 1.0)
    fill_opacity = _number(inherited.get("fill-opacity"), 1.0)
    stroke_opacity = _number(inherited.get("stroke-opacity"), 1.0)
    shape.linecap = inherited.get("stroke-linecap", "butt")

    gradient_match = re.match(r"^url\(\s*#([^)\s]+)\s*\)$", (fill_raw or "").strip())
    if gradient_match:
        stops = gradients.get(gradient_match.group(1))
        if not stops:
            raise Unsupported("missing gradient definition")
        shape.gradient = stops
    else:
        fill = _paint(fill_raw, current=inherited.get("color", "#000000"))
        if fill is not None and fill_opacity < 1.0:
            fill = util.with_alpha(fill, util.alpha_of(fill) * fill_opacity)
        shape.fill = fill
    stroke = _paint(stroke_raw, current=inherited.get("color", "#000000"))
    if stroke is not None and stroke_opacity < 1.0:
        stroke = util.with_alpha(stroke, util.alpha_of(stroke) * stroke_opacity)
    shape.stroke = stroke
    shape.stroke_width = _number(inherited.get("stroke-width"), 0.0)

    if tag == "rect":
        x = _number(element.get("x"))
        y = _number(element.get("y"))
        width = _number(element.get("width"))
        height = _number(element.get("height"))
        if width <= 0 or height <= 0:
            return None
        rx = _number(element.get("rx"), 0.0)
        ry = _number(element.get("ry"), rx or 0.0)
        if rx <= 0 and ry <= 0:
            shape.commands = [("M", (x, y)), ("L", (x + width, y)), ("L", (x + width, y + height)), ("L", (x, y + height)), ("Z", ())]
            shape.closed = True
        else:
            rx = min(rx or ry, width / 2.0)
            ry = min(ry or rx, height / 2.0)
            shape.commands = _rounded_rect(x, y, width, height, rx, ry)
            shape.closed = True
        shape.x, shape.y, shape.w, shape.h = x, y, width, height
        shape.rx, shape.ry = rx, ry
    elif tag in ("circle", "ellipse"):
        cx = _number(element.get("cx"))
        cy = _number(element.get("cy"))
        if tag == "circle":
            rx = ry = _number(element.get("r"))
        else:
            rx = _number(element.get("rx"))
            ry = _number(element.get("ry"))
        if rx <= 0 or ry <= 0:
            return None
        shape.commands = _ellipse(cx, cy, rx, ry)
        shape.closed = True
        shape.x, shape.y, shape.w, shape.h = cx - rx, cy - ry, rx * 2, ry * 2
        shape.rx, shape.ry = rx, ry
    elif tag == "line":
        x1 = _number(element.get("x1"))
        y1 = _number(element.get("y1"))
        x2 = _number(element.get("x2"))
        y2 = _number(element.get("y2"))
        shape.commands = [("M", (x1, y1)), ("L", (x2, y2))]
        if shape.stroke is None:
            return None
        shape.x = min(x1, x2)
        shape.y = min(y1, y2)
        shape.w = abs(x2 - x1)
        shape.h = abs(y2 - y1)
    elif tag in ("polyline", "polygon"):
        numbers = [float(v) for v in _NUM.findall(element.get("points") or "")]
        points = list(zip(numbers[0::2], numbers[1::2]))
        if len(points) < 2:
            return None
        shape.commands = [("M", points[0])] + [("L", point) for point in points[1:]]
        if tag == "polygon":
            shape.commands.append(("Z", ()))
            shape.closed = True
        shape.x = min(p[0] for p in points)
        shape.y = min(p[1] for p in points)
        shape.w = max(p[0] for p in points) - shape.x
        shape.h = max(p[1] for p in points) - shape.y
    elif tag == "path":
        data = element.get("d") or ""
        if not data.strip():
            return None
        shape.commands = _parse_path(data)
        shape.closed = any(command[0] == "Z" for command in shape.commands)
        xs = [value for command in shape.commands if command[0] != "Z" for value in command[1][0::2]]
        ys = [value for command in shape.commands if command[0] != "Z" for value in command[1][1::2]]
        if not xs or not ys:
            return None
        shape.x, shape.y = min(xs), min(ys)
        shape.w, shape.h = max(xs) - shape.x, max(ys) - shape.y
    else:
        return None
    if shape.fill is None and shape.gradient is None and shape.stroke is None:
        return None
    return shape


def _rounded_rect(x, y, width, height, rx, ry):
    k = 0.5522847498
    commands = [("M", (x + rx, y))]
    commands.append(("L", (x + width - rx, y)))
    commands.append(("C", (x + width - rx + k * rx, y, x + width, y + ry - k * ry, x + width, y + ry)))
    commands.append(("L", (x + width, y + height - ry)))
    commands.append(("C", (x + width, y + height - ry + k * ry, x + width - rx + k * rx, y + height, x + width - rx, y + height)))
    commands.append(("L", (x + rx, y + height)))
    commands.append(("C", (x + rx - k * rx, y + height, x, y + height - ry + k * ry, x, y + height - ry)))
    commands.append(("L", (x, y + ry)))
    commands.append(("C", (x, y + ry - k * ry, x + rx - k * rx, y, x + rx, y)))
    commands.append(("Z", ()))
    return commands


def _ellipse(cx, cy, rx, ry):
    k = 0.5522847498
    return [
        ("M", (cx + rx, cy)),
        ("C", (cx + rx, cy + k * ry, cx + k * rx, cy + ry, cx, cy + ry)),
        ("C", (cx - k * rx, cy + ry, cx - rx, cy + k * ry, cx - rx, cy)),
        ("C", (cx - rx, cy - k * ry, cx - k * rx, cy - ry, cx, cy - ry)),
        ("C", (cx + k * rx, cy - ry, cx + rx, cy - k * ry, cx + rx, cy)),
        ("Z", ()),
    ]


def _parse_path(data):
    tokens = _NUM.findall(data)
    commands = _IDENT.findall(data)
    if not commands:
        return []
    result = []
    index = 0
    position = (0.0, 0.0)
    start = (0.0, 0.0)
    previous = ""
    control = None

    def take(count):
        nonlocal index
        values = [float(tokens[index + offset]) for offset in range(count)]
        index += count
        return values

    for command in commands:
        relative = command.islower()
        kind = command.upper()
        if kind == "M":
            x, y = take(2)
            if relative:
                x, y = position[0] + x, position[1] + y
            result.append(("M", (x, y)))
            position = (x, y)
            start = (x, y)
            kind = "L"
        elif kind == "L":
            x, y = take(2)
            if relative:
                x, y = position[0] + x, position[1] + y
            result.append(("L", (x, y)))
            position = (x, y)
        elif kind == "H":
            (x,) = take(1)
            x = position[0] + x if relative else x
            result.append(("L", (x, position[1])))
            position = (x, position[1])
        elif kind == "V":
            (y,) = take(1)
            y = position[1] + y if relative else y
            result.append(("L", (position[0], y)))
            position = (position[0], y)
        elif kind == "C":
            x1, y1, x2, y2, x, y = take(6)
            if relative:
                x1 += position[0]; y1 += position[1]
                x2 += position[0]; y2 += position[1]
                x += position[0]; y += position[1]
            result.append(("C", (x1, y1, x2, y2, x, y)))
            control = (x2, y2)
            position = (x, y)
        elif kind == "S":
            x2, y2, x, y = take(4)
            if relative:
                x2 += position[0]; y2 += position[1]
                x += position[0]; y += position[1]
            if previous in ("C", "S") and control is not None:
                x1 = 2 * position[0] - control[0]
                y1 = 2 * position[1] - control[1]
            else:
                x1, y1 = position
            result.append(("C", (x1, y1, x2, y2, x, y)))
            control = (x2, y2)
            position = (x, y)
        elif kind == "Q":
            qx, qy, x, y = take(4)
            if relative:
                qx += position[0]; qy += position[1]
                x += position[0]; y += position[1]
            result.append(("C", _quadratic_to_cubic(position, (qx, qy), (x, y))))
            control = (qx, qy)
            position = (x, y)
        elif kind == "T":
            x, y = take(2)
            if relative:
                x += position[0]; y += position[1]
            if previous in ("Q", "T") and control is not None:
                qx = 2 * position[0] - control[0]
                qy = 2 * position[1] - control[1]
            else:
                qx, qy = position
            result.append(("C", _quadratic_to_cubic(position, (qx, qy), (x, y))))
            control = (qx, qy)
            position = (x, y)
        elif kind == "A":
            rx, ry, rotation, large, sweep, x, y = take(7)
            if relative:
                x += position[0]; y += position[1]
            for curve in _arc_to_cubics(position, (x, y), rx, ry, rotation, bool(large), bool(sweep)):
                result.append(("C", curve))
            position = (x, y)
        elif kind == "Z":
            result.append(("Z", ()))
            position = start
        previous = kind
    return result


def _quadratic_to_cubic(start, control, end):
    c1 = (start[0] + 2.0 / 3.0 * (control[0] - start[0]), start[1] + 2.0 / 3.0 * (control[1] - start[1]))
    c2 = (end[0] + 2.0 / 3.0 * (control[0] - end[0]), end[1] + 2.0 / 3.0 * (control[1] - end[1]))
    return (c1[0], c1[1], c2[0], c2[1], end[0], end[1])


def _arc_to_cubics(start, end, rx, ry, rotation, large, sweep):
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(start[0], start[1], end[0], end[1], end[0], end[1])]
    phi = math.radians(rotation)
    dx = (start[0] - end[0]) / 2.0
    dy = (start[1] - end[1]) / 2.0
    x1 = math.cos(phi) * dx + math.sin(phi) * dy
    y1 = -math.sin(phi) * dx + math.cos(phi) * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        factor = math.sqrt(lam)
        rx *= factor
        ry *= factor
    numerator = max(0.0, rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1)
    denominator = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coefficient = math.sqrt(numerator / denominator) if denominator else 0.0
    if large == sweep:
        coefficient = -coefficient
    cx1 = coefficient * rx * y1 / ry
    cy1 = -coefficient * ry * x1 / rx
    cx = math.cos(phi) * cx1 - math.sin(phi) * cy1 + (start[0] + end[0]) / 2.0
    cy = math.sin(phi) * cx1 + math.cos(phi) * cy1 + (start[1] + end[1]) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = (math.hypot(ux, uy) * math.hypot(vx, vy)) or 1.0
        value = max(-1.0, min(1.0, dot / norm))
        sign = -1.0 if (ux * vy - uy * vx) < 0 else 1.0
        return sign * math.acos(value)

    theta1 = angle(1, 0, (x1 - cx1) / rx if rx else 0, (y1 - cy1) / ry if ry else 0)
    theta2 = angle(
        (x1 - cx1) / rx if rx else 0, (y1 - cy1) / ry if ry else 0,
        (-x1 - cx1) / rx if rx else 0, (-y1 - cy1) / ry if ry else 0,
    )
    if not sweep and theta2 > 0:
        theta2 -= 2 * math.pi
    elif sweep and theta2 < 0:
        theta2 += 2 * math.pi
    segments = max(1, int(math.ceil(abs(theta2 - theta1) / (math.pi / 2))))
    step = (theta2 - theta1) / segments
    curves = []
    angle_start = theta1
    for _ in range(segments):
        angle_end = angle_start + step
        alpha = (4.0 / 3.0) * math.tan(step / 4.0)
        p1 = (
            math.cos(phi) * rx * math.cos(angle_start) - math.sin(phi) * ry * math.sin(angle_start) + cx,
            math.sin(phi) * rx * math.cos(angle_start) + math.cos(phi) * ry * math.sin(angle_start) + cy,
        )
        p2 = (
            math.cos(phi) * rx * math.cos(angle_end) - math.sin(phi) * ry * math.sin(angle_end) + cx,
            math.sin(phi) * rx * math.cos(angle_end) + math.cos(phi) * ry * math.sin(angle_end) + cy,
        )
        d1 = (
            -math.cos(phi) * rx * math.sin(angle_start) - math.sin(phi) * ry * math.cos(angle_start),
            -math.sin(phi) * rx * math.sin(angle_start) + math.cos(phi) * ry * math.cos(angle_start),
        )
        d2 = (
            -math.cos(phi) * rx * math.sin(angle_end) - math.sin(phi) * ry * math.cos(angle_end),
            -math.sin(phi) * rx * math.sin(angle_end) + math.cos(phi) * ry * math.cos(angle_end),
        )
        c1 = (p1[0] + alpha * d1[0], p1[1] + alpha * d1[1])
        c2 = (p2[0] - alpha * d2[0], p2[1] - alpha * d2[1])
        curves.append((c1[0], c1[1], c2[0], c2[1], p2[0], p2[1]))
        angle_start = angle_end
    if curves:
        curves[-1] = curves[-1][:4] + (end[0], end[1])
    return curves


def _transform_shape(shape, transform):
    converted = []
    for kind, values in shape.commands:
        if kind == "Z":
            converted.append((kind, ()))
            continue
        points = []
        for index in range(0, len(values), 2):
            points.extend(transform.apply(values[index], values[index + 1]))
        converted.append((kind, tuple(points)))
    shape.commands = converted
    scale = transform.scale_factor()
    shape.stroke_width *= scale
    shape.x, shape.y = transform.apply(shape.x, shape.y)
    shape.w *= scale
    shape.h *= scale


# --------------------------------------------------------------------------
# DrawingML emission
# --------------------------------------------------------------------------
def emit(slide, document, box, shape_name="svg"):
    """Create native shapes for ``document`` inside ``box``.

    Returns the number of shapes created. The caller falls back to rasterising
    when the SVG cannot be represented.
    """
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu

    x, y, width, height = box.rect
    view_x, view_y, view_w, view_h = document.viewbox
    if view_w <= 0 or view_h <= 0:
        raise Unsupported("empty viewBox")
    scale = min(width / view_w, height / view_h)
    offset_x = x + (width - view_w * scale) / 2.0
    offset_y = y + (height - view_h * scale) / 2.0
    created = 0
    for shape in document.shapes:
        if isinstance(shape, SvgText):
            if _emit_text(slide, shape, offset_x, offset_y, view_x, view_y, scale, shape_name):
                created += 1
            continue
        px = offset_x + (shape.x - view_x) * scale
        py = offset_y + (shape.y - view_y) * scale
        pw = max(0.5, shape.w * scale)
        ph = max(0.5, shape.h * scale)
        preset = None
        if shape.tag == "rect" and shape.rx <= 0 and shape.ry <= 0:
            preset = MSO_SHAPE.RECTANGLE
        elif shape.tag == "rect":
            preset = MSO_SHAPE.ROUNDED_RECTANGLE
        elif shape.tag in ("circle", "ellipse"):
            preset = MSO_SHAPE.OVAL
        if preset is not None:
            element = slide.shapes.add_shape(
                preset,
                Emu(util.pt2emu(px)), Emu(util.pt2emu(py)),
                Emu(max(1, util.pt2emu(pw))), Emu(max(1, util.pt2emu(ph))),
            )
            if preset == MSO_SHAPE.ROUNDED_RECTANGLE:
                try:
                    element.adjustments[0] = min(0.5, shape.rx / max(1e-3, min(shape.w, shape.h)))
                except (IndexError, ValueError, TypeError):
                    pass
        else:
            element = _custom_shape(
                slide, shape, px, py, pw, ph,
                origin=(offset_x, offset_y), view=(view_x, view_y), scale=scale,
            )
            if element is None:                continue
        _apply_paint(element, shape, scale)
        _strip_style(element)
        element.name = f"{shape_name}-{shape.tag}"
        element.shadow.inherit = False
        created += 1
    return created


def _emit_text(slide, label, offset_x, offset_y, view_x, view_y, scale, shape_name):
    """Write an SVG label as a native text box (editable, no rasterising)."""
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Emu

    from . import xmlutil

    # ``scale`` already converts viewBox units to points, so the font size needs
    # no further conversion: an 11-unit label in a 600-wide viewBox renders as
    # 11 * (frame width in pt / 600) pt — the same proportion as the browser.
    size_pt = max(3.0, label.size * scale)
    lines = label.lines or []
    if not lines:
        return False
    line_height = size_pt * 1.25
    longest = max((_visual_len(line) for line in lines), default=1)
    # Generous width: labels are single lines and must never wrap, so the frame
    # is sized from an em-count estimate with headroom for font substitution.
    box_width = max(18.0, longest * size_pt * 1.9 + 6.0)
    box_height = line_height * len(lines) + 2.0

    anchor_x = label.x
    px = offset_x + (anchor_x - view_x) * scale
    py = offset_y + (label.y - view_y) * scale - line_height * 0.82
    if label.anchor == "middle":
        px -= box_width / 2.0
    elif label.anchor == "end":
        px -= box_width

    textbox = slide.shapes.add_textbox(
        Emu(util.pt2emu(px)), Emu(util.pt2emu(py)),
        Emu(max(1, util.pt2emu(box_width))), Emu(max(1, util.pt2emu(box_height))),
    )
    textbox.name = f"{shape_name}-text"
    frame = textbox.text_frame
    frame.word_wrap = False
    frame.vertical_anchor = MSO_ANCHOR.TOP
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.auto_size = MSO_AUTO_SIZE.NONE
    body_pr = frame._txBody.find(qn("a:bodyPr"))
    if body_pr is not None:
        for child in list(body_pr):
            if child.tag in (qn("a:normAutofit"), qn("a:spAutoFit"), qn("a:noAutofit")):
                body_pr.remove(child)
        etree.SubElement(body_pr, qn("a:noAutofit"))

    align = {"middle": PP_ALIGN.CENTER, "end": PP_ALIGN.RIGHT}.get(label.anchor, PP_ALIGN.LEFT)
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.line_spacing = Emu(util.pt2emu(line_height))
        paragraph.space_before = Emu(0)
        paragraph.space_after = Emu(0)
        p_pr = paragraph._p.get_or_add_pPr()
        etree.SubElement(p_pr, qn("a:buNone"))
        run = paragraph.add_run()
        run.text = line
        xmlutil.set_run_font(
            run, label.family, size_pt,
            bold=label.weight >= 600, italic=label.italic,
            color=util.with_alpha(label.color, util.alpha_of(label.color) * label.opacity),
        )
    textbox.shadow.inherit = False
    return True


def _visual_len(text):
    """Advance width in em, counting CJK as one em and Latin as ~half."""
    total = 0.0
    for char in text:
        total += 1.0 if util.is_wide_char(char) else 0.55
    return max(1.0, total)


def _strip_style(element):
    """Drop the shape's theme style reference (accent fill / preset shadow)."""
    from pptx.oxml.ns import qn

    for style in element._element.findall(qn("p:style")):
        element._element.remove(style)


def _custom_shape(slide, shape, px, py, pw, ph, origin, view, scale):
    from lxml import etree as lxml_etree
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
    from pptx.util import Emu

    self_import = __import__(__name__, fromlist=["_to_emu"])
    frame = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Emu(util.pt2emu(px)), Emu(util.pt2emu(py)),
        Emu(max(1, util.pt2emu(pw))), Emu(max(1, util.pt2emu(ph))),
    )
    sp_pr = frame._element.spPr
    for child in list(sp_pr):
        if child.tag == qn("a:prstGeom"):
            sp_pr.remove(child)

    local_w = max(1, util.pt2emu(pw))
    local_h = max(1, util.pt2emu(ph))
    geom = lxml_etree.SubElement(sp_pr, qn("a:custGeom"))
    lxml_etree.SubElement(geom, qn("a:avLst"))
    lxml_etree.SubElement(geom, qn("a:gdLst"))
    lxml_etree.SubElement(geom, qn("a:ahLst"))
    lxml_etree.SubElement(geom, qn("a:rect"), l="0", t="0", r="0", b="0")
    path_lst = lxml_etree.SubElement(geom, qn("a:pathLst"))

    subpaths = [[]]
    for kind, values in shape.commands:
        if kind == "Z":
            subpaths.append([])
            continue
        subpaths[-1].append((kind, values))
    emitted = 0
    frame_rect = (shape.x, shape.y, max(1e-6, shape.w), max(1e-6, shape.h))
    for commands in subpaths:
        if not commands:
            continue
        path = lxml_etree.SubElement(path_lst, qn("a:path"), w=str(local_w), h=str(local_h))
        for command, values in commands:
            if command == "M":
                node = lxml_etree.SubElement(path, qn("a:moveTo"))
                _point(node, values, frame_rect, local_w, local_h)
            elif command == "L":
                node = lxml_etree.SubElement(path, qn("a:lnTo"))
                _point(node, values, frame_rect, local_w, local_h)
            elif command == "C":
                node = lxml_etree.SubElement(path, qn("a:cubicBezTo"))
                _point(node, values[0:2], frame_rect, local_w, local_h)
                _point(node, values[2:4], frame_rect, local_w, local_h)
                _point(node, values[4:6], frame_rect, local_w, local_h)
        if shape.closed:
            lxml_etree.SubElement(path, qn("a:close"))
        emitted += 1
    if not emitted:
        return None
    from . import xmlutil

    for child in list(sp_pr):
        sp_pr.remove(child)
        xmlutil.ordered_insert(sp_pr, child)
    del self_import
    return frame


def _point(parent, values, frame_rect, local_w, local_h):
    """Write an ``<a:pt>`` in the path's own EMU space.

    ``frame_rect`` is the shape's bounding box in viewBox units, so each vertex
    is normalised into that box before being scaled to EMU. Doing it this way
    keeps custom geometry correct for paths that do not start at the origin.
    """
    from lxml import etree as lxml_etree
    from pptx.oxml.ns import qn

    origin_x, origin_y, width, height = frame_rect
    # A perfectly vertical or horizontal line has a zero-width/height bounding
    # box; normalising by a tiny epsilon keeps its vertices pinned to the frame
    # edge instead of collapsing them into the origin.
    point_x = (values[0] - origin_x) / max(width, 1e-6) * local_w if width > 1e-6 else 0.0
    point_y = (values[1] - origin_y) / max(height, 1e-6) * local_h if height > 1e-6 else 0.0
    lxml_etree.SubElement(
        parent,
        qn("a:pt"),
        x=str(int(round(point_x))),
        y=str(int(round(point_y))),
    )


def _apply_paint(element, shape, scale):
    from . import xmlutil

    opacity = util.clamp(getattr(shape, "opacity", 1.0) or 1.0, 0.0, 1.0)
    if shape.gradient:
        stops = []
        for offset, color in shape.gradient:
            stops.append(
                type("Stop", (), {"color": util.with_alpha(color, util.alpha_of(color) * opacity),
                                  "position": offset})()
            )

        class _Gradient:
            kind = "linear"
            angle = 90.0
            width = 0.0
            height = 0.0

        gradient = _Gradient()
        gradient.stops = stops
        xmlutil.ordered_insert(element._element.spPr, xmlutil.gradient_element(gradient))
    elif shape.fill is not None:
        element.fill.solid()
        element.fill.fore_color.rgb = _rgb(shape.fill)
        alpha = util.alpha_of(shape.fill) * opacity
        if alpha < 0.999:
            _alpha(element, alpha)
    else:
        element.fill.background()

    if shape.stroke is not None and shape.stroke_width > 0:
        # ``scale`` already converts viewBox units to points, so the stroke width
        # is multiplied once (not twice) to stay visually faithful.
        element.line.width = util.pt2emu(max(0.2, shape.stroke_width * scale))
        element.line.color.rgb = _rgb(shape.stroke)
        stroke_alpha = util.alpha_of(shape.stroke) * opacity
        if stroke_alpha < 0.999:
            _line_alpha(element, stroke_alpha)
    else:
        xmlutil.no_line(element)


def _line_alpha(element, alpha):
    from lxml import etree as lxml_etree
    from pptx.oxml.ns import qn

    ln = element._element.spPr.find(qn("a:ln"))
    if ln is None:
        return
    fill = ln.find(qn("a:solidFill"))
    if fill is None:
        return
    for srgb in fill.findall(qn("a:srgbClr")):
        existing = srgb.find(qn("a:alpha"))
        value = str(int(round(alpha * 100000)))
        if existing is None:
            lxml_etree.SubElement(srgb, qn("a:alpha"), val=value)
        else:
            existing.set("val", value)


def _rgb(color):
    from pptx.dml.color import RGBColor

    return RGBColor(int(color[0]), int(color[1]), int(color[2]))


def _alpha(element, alpha):
    from lxml import etree as lxml_etree
    from pptx.oxml.ns import qn

    for fill in element._element.spPr.findall(qn("a:solidFill")):
        for srgb in fill.findall(qn("a:srgbClr")):
            lxml_etree.SubElement(srgb, qn("a:alpha"), val=str(int(round(alpha * 100000))))
