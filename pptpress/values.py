"""CSS value parsing: lengths, box shorthands, colours, gradients, transforms.

Everything is normalised to points (``pt``) so the layout and export stages can
reason about one unit. Percentages are resolved lazily by the caller.
"""

from __future__ import annotations

import re

from . import util


class Percent(float):
    """A percentage width/height kept as a 0..1 fraction until layout time.

    Subclassing ``float`` keeps the value arithmetic-friendly while letting the
    engine tell ``height:100%`` (a fraction) apart from ``height:1px`` (a very
    thin line) — both would otherwise look like a number below 1.
    """

    __slots__ = ()

LENGTH_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+))(px|pt|em|rem|%|vw|vh|vmin|vmax|in|cm|mm|pc|q)?$", re.I)

_ABS_UNITS = {
    "px": util.PT_PER_PX,
    "pt": 1.0,
    "in": 72.0,
    "cm": 28.3464567,
    "mm": 2.83464567,
    "pc": 12.0,
    "q": 0.708661417,
}

KEYWORDS = {
    "auto", "none", "normal", "inherit", "initial", "unset", "min-content",
    "max-content", "fit-content", "transparent", "currentcolor",
}


class Length:
    """A parsed length with unit awareness."""

    __slots__ = ("value", "unit", "percent", "keyword")

    def __init__(self, value=0.0, unit="px", percent=False, keyword=None):
        self.value = value
        self.unit = unit
        self.percent = percent
        self.keyword = keyword

    @property
    def auto(self):
        return self.keyword == "auto"

    def resolve(self, base_pt=0.0, font_size_pt=None, viewport=None):
        """Resolve to points. ``base_pt`` is the percentage reference."""
        if self.keyword == "auto":
            return None
        if self.percent:
            if base_pt is None:
                return 0.0
            return base_pt * self.value / 100.0
        if self.unit == "em":
            return self.value * (font_size_pt if font_size_pt is not None else 16.0 * util.PT_PER_PX)
        if self.unit == "rem":
            return self.value * 16.0 * util.PT_PER_PX
        if self.unit in ("vw", "vh", "vmin", "vmax"):
            width, height = viewport or (960.0, 540.0)
            if self.unit == "vw":
                return width * self.value / 100.0
            if self.unit == "vh":
                return height * self.value / 100.0
            if self.unit == "vmin":
                return min(width, height) * self.value / 100.0
            return max(width, height) * self.value / 100.0
        return self.value * _ABS_UNITS.get(self.unit, util.PT_PER_PX)

    def is_zero(self):
        return self.keyword in ("none",) or (self.keyword is None and abs(self.value) < 1e-9)

    def __repr__(self):
        return f"Length({self.value}{'%' if self.percent else self.unit})"


def parse_length(text, default=None):
    if text is None:
        return default
    raw = str(text).strip().lower()
    if not raw:
        return default
    if raw in ("auto", "none", "normal", "inherit", "initial", "unset", "fit-content"):
        return Length(0.0, "px", keyword=raw)
    match = LENGTH_RE.match(raw)
    if not match:
        number = _leading_number(raw)
        if number is None:
            return default
        return Length(number, "px")
    number = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    if unit == "%":
        return Length(number, "px", percent=True)
    return Length(number, unit)


def _leading_number(text):
    match = re.match(r"^([+-]?(?:\d+\.?\d*|\.\d+))", text)
    return float(match.group(1)) if match else None


def parse_length_list(text):
    if not text:
        return []
    parts = re.split(r"\s+", text.strip())
    return [parse_length(part) for part in parts if part]


def expand_box(values):
    """CSS 1-4 value shorthand -> (top, right, bottom, left)."""
    items = [v for v in values if v is not None]
    if not items:
        return None
    if len(items) == 1:
        return (items[0], items[0], items[0], items[0])
    if len(items) == 2:
        return (items[0], items[1], items[0], items[1])
    if len(items) == 3:
        return (items[0], items[1], items[2], items[1])
    return (items[0], items[1], items[2], items[3])


_LENGTH_ONLY = re.compile(r"^[+-]?[\d.]+(px|pt|em|rem|%)?$", re.I)

BORDER_STYLES = {
    "none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge",
    "inset", "outset",
}


class Border:
    __slots__ = ("width", "style", "color")

    def __init__(self, width=0.0, style="none", color=None):
        self.width = width
        self.style = style
        self.color = color

    @property
    def visible(self):
        return self.width > 0.05 and self.style not in ("none", "hidden")


def parse_border_side(text, default_color=None):
    from . import css as css_module

    if not text:
        return None
    raw = str(text).strip()
    if raw.lower() in ("none", "0", "hidden"):
        return Border(0.0, "none", None)
    tokens = re.findall(r"rgba?\([^)]*\)|hsla?\([^)]*\)|[^\s]+", raw)
    width = 0.0
    style = "solid"
    color = None
    for token in tokens:
        lowered = token.lower()
        if lowered in BORDER_STYLES:
            style = lowered
            continue
        if _LENGTH_ONLY.match(lowered):
            length = parse_length(lowered)
            if length is not None:
                width = length.resolve()
                continue
        parsed = util.parse_color(token)
        if parsed is not None:
            color = parsed
    if style in ("none", "hidden") and width == 0:
        return Border(0.0, "none", None)
    return Border(width, style, color or default_color)


def parse_border_shorthand(text, default_color=None):
    side = parse_border_side(text, default_color)
    return (side, side, side, side) if side else None


def parse_radius(text):
    """Parse ``border-radius`` into four corners, each ``(rx, ry)``.

    ``rx``/``ry`` are either absolute points or a :class:`Percent` fraction of the
    box width/height. Keeping percentages unresolved is what makes
    ``border-radius:50%`` a real ellipse and ``24px 0 0 0`` a per-corner shape —
    both are impossible once the value has been flattened into one number.
    """
    if not text:
        return None
    raw = text.strip()
    horizontal, _, vertical = raw.partition("/")
    horizontal_values = _radius_components(horizontal)
    if not horizontal_values:
        return None
    vertical_values = _radius_components(vertical) if vertical.strip() else list(horizontal_values)
    if not vertical_values:
        vertical_values = list(horizontal_values)
    horizontal_values = _expand_corners(horizontal_values)
    vertical_values = _expand_corners(vertical_values)
    if len(vertical_values) != len(horizontal_values):
        vertical_values = _expand_corners(vertical_values[: len(horizontal_values)] or horizontal_values)
    return [
        (horizontal_values[index], vertical_values[index])
        for index in range(4)
    ]


def _radius_components(text):
    parts = [part for part in re.split(r"\s+", (text or "").strip()) if part]
    out = []
    for part in parts:
        if part.endswith("%"):
            try:
                out.append(Percent(float(part[:-1]) / 100.0))
            except ValueError:
                continue
            continue
        length = parse_length(part)
        if length is None:
            continue
        out.append(length.resolve(font_size_pt=None) or 0.0)
    return out


def _expand_corners(items):
    values = list(items[:4])
    if not values:
        return []
    if len(values) == 1:
        values = values * 4
    elif len(values) == 2:
        values = [values[0], values[1], values[0], values[1]]
    elif len(values) == 3:
        values = [values[0], values[1], values[2], values[1]]
    return values


def resolve_radius(corners, width, height):
    """Turn stored corners into points once the box size is known."""
    if not corners:
        return None
    out = []
    for rx, ry in corners[:4]:
        radius_x = width * float(rx) if isinstance(rx, Percent) else (rx or 0.0)
        radius_y = height * float(ry) if isinstance(ry, Percent) else (ry or 0.0)
        out.append((max(0.0, radius_x), max(0.0, radius_y)))
    return out


class GradientStop:
    __slots__ = ("color", "position")

    def __init__(self, color, position):
        self.color = color
        self.position = position

    def __repr__(self):
        return f"Stop({util.to_hex(self.color)} {self.position:.2f})"


class Gradient:
    """A linear/radial gradient in *points* relative to the painted box."""

    __slots__ = ("kind", "angle", "stops", "width", "height", "center", "shape")

    def __init__(self, kind, stops, angle=180.0, width=0.0, height=0.0, center=(0.5, 0.5), shape="ellipse"):
        self.kind = kind
        self.stops = stops
        self.angle = angle
        self.width = width
        self.height = height
        self.center = center
        self.shape = shape

    def at(self, fraction):
        """Interpolate the gradient colour at 0..1 along its axis."""
        stops = self.stops
        if not stops:
            return (0, 0, 0, 0.0)
        if fraction <= stops[0].position:
            return stops[0].color
        if fraction >= stops[-1].position:
            return stops[-1].color
        for index in range(len(stops) - 1):
            left, right = stops[index], stops[index + 1]
            if left.position <= fraction <= right.position:
                span = right.position - left.position
                ratio = 0.0 if span <= 0 else (fraction - left.position) / span
                return util.mix(left.color, right.color, ratio)
        return stops[-1].color

    def endpoints(self):
        """Return two (x, y) offsets in points spanning the gradient axis."""
        half = (self.width ** 2 + self.height ** 2) ** 0.5 / 2.0
        return (self.center[0], self.center[1])

    def normalized_series(self, samples=12):
        return [self.at(i / (samples - 1)) for i in range(samples)]


def parse_gradient(text):
    """Parse ``linear-gradient(...)``/``radial-gradient(...)`` into a Gradient."""
    if not text:
        return None
    raw = text.strip()
    match = re.match(r"^(repeating-)?(linear|radial)-gradient\s*\((.*)\)$", raw, re.I | re.S)
    if not match:
        return None
    kind = match.group(2).lower()
    body = _split_top_level(match.group(3))
    if not body:
        return None
    angle = 180.0
    shape = "ellipse"
    center = (0.5, 0.5)
    first = body[0].strip().lower()
    if kind == "linear":
        angle_token = _parse_angle(first)
        if angle_token is not None:
            angle = angle_token
            body = body[1:]
    else:
        if "circle" in first or first.startswith("at ") or re.match(r"^[\d.]+(px|%)?", first):
            shape = "circle" if "circle" in first else "ellipse"
            at_match = re.search(r"at\s+([^,]+)$", first)
            if at_match:
                center = _parse_position(at_match.group(1))
            body = body[1:]
    stops = []
    pending = []
    for chunk in body:
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = _split_top_level(chunk, sep=" ")
        color_tokens = [p for p in parts if util.parse_color(p) is not None]
        pos_tokens = [p for p in parts if re.match(r"^[+-]?[\d.]+%?$", p)]
        if color_tokens:
            color = util.parse_color(color_tokens[0])
            positions = pos_tokens[:2]
            if positions:
                for position in positions:
                    stops.append(GradientStop(color, _percent(position)))
            else:
                pending.append(color)
        elif pos_tokens and stops:
            stops[-1].position = _percent(pos_tokens[0])
    if pending and not stops:
        stops = [
            GradientStop(color, index / max(1, len(pending) - 1))
            for index, color in enumerate(pending)
        ]
    if not stops:
        for index, color in enumerate(pending):
            stops.append(GradientStop(color, index / max(1, len(pending) - 1)))
    if len(stops) < 2:
        return None
    _distribute(stops)
    return Gradient(kind, stops, angle=angle, center=center, shape=shape)


def _distribute(stops):
    first = stops[0]
    if first.position is None:
        first.position = 0.0
    previous = first.position
    for stop in stops[1:]:
        if stop.position is None:
            stop.position = previous
        previous = stop.position
    last = stops[-1]
    if last.position <= 1.0 and last.position == first.position:
        step = 1.0 / max(1, len(stops) - 1)
        for index, stop in enumerate(stops):
            stop.position = index * step
    for stop in stops:
        stop.position = min(1.0, max(0.0, stop.position))


def _percent(token):
    match = re.match(r"^([+-]?[\d.]+)(%|px|pt)?$", token.strip())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or "%"
    if unit == "%":
        return value / 100.0
    return value


def _parse_angle(token):
    token = token.strip().lower()
    named = {
        "to top": 0.0,
        "to top right": 45.0,
        "to right top": 45.0,
        "to right": 90.0,
        "to bottom right": 135.0,
        "to right bottom": 135.0,
        "to bottom": 180.0,
        "to bottom left": 225.0,
        "to left bottom": 225.0,
        "to left": 270.0,
        "to top left": 315.0,
        "to left top": 315.0,
    }
    if token in named:
        return named[token]
    match = re.match(r"^([+-]?[\d.]+)(deg|rad|turn|grad)?$", token)
    if match:
        value = float(match.group(1))
        unit = match.group(2) or "deg"
        if unit == "rad":
            return value * 57.2957795
        if unit == "turn":
            return value * 360.0
        if unit == "grad":
            return value * 0.9
        return value
    return None


def _parse_position(text):
    parts = [p for p in text.replace(",", " ").split() if p]
    x = _position_component(parts[0]) if parts else 0.5
    y = _position_component(parts[1]) if len(parts) > 1 else 0.5
    return (x, y)


def _position_component(token):
    token = token.strip().lower()
    named = {"left": 0.0, "top": 0.0, "center": 0.5, "right": 1.0, "bottom": 1.0}
    if token in named:
        return named[token]
    match = re.match(r"^([+-]?[\d.]+)%?$", token)
    if match:
        value = float(match.group(1))
        return value / 100.0 if "%" in token else value
    return 0.5


def _split_top_level(text, sep=","):
    parts = []
    depth = 0
    current = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def gradient_to_css(gradient):
    stops = ", ".join(f"{util.to_css(stop.color)} {stop.position * 100:.1f}%" for stop in gradient.stops)
    if gradient.kind == "linear":
        return f"linear-gradient({gradient.angle:.1f}deg, {stops})"
    return f"radial-gradient(circle at 50% 50%, {stops})"


class Background:
    """Resolved background: solid colour, gradient and/or image URL."""

    __slots__ = ("color", "gradients", "image", "size", "position", "repeat")

    def __init__(self, color=None, gradients=None, image=None, size="auto", position="0% 0%", repeat="no-repeat"):
        self.color = color
        self.gradients = gradients or []
        self.image = image
        self.size = size or "auto"
        self.position = position or "0% 0%"
        self.repeat = repeat or "no-repeat"

    @property
    def is_image(self):
        return bool(self.image)

    @property
    def is_gradient(self):
        return bool(self.gradients)

    def scale_mode(self):
        size = (self.size or "auto").lower()
        if "contain" in size:
            return "contain"
        if "cover" in size:
            return "cover"
        return "cover"

    def focus(self):
        return _parse_position(self.position.replace("top", "0%").replace("bottom", "100%").replace("left", "0%").replace("right", "100%"))


def parse_background(value, default_color=None):
    if not value:
        return None
    raw = str(value).strip()
    if raw.lower() in ("none", "transparent"):
        return Background(color=None)
    gradients = []
    images = []
    color = None
    for chunk in _split_top_level(raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        gradient = parse_gradient(chunk)
        if gradient is not None:
            gradients.append(gradient)
            continue
        url_match = re.match(r"^url\(\s*['\"]?([^'\")]+)['\"]?\s*\)$", chunk, re.I)
        if url_match:
            images.append(url_match.group(1))
            continue
        parsed = util.parse_color(chunk)
        if parsed is not None:
            color = parsed
    return Background(color=color, gradients=gradients, image=images[0] if images else None)


def parse_shadow(value, font_size_pt=16.0):
    """Parse a box/text shadow list -> list of dicts."""
    if not value or value.strip().lower() == "none":
        return []
    shadows = []
    for chunk in _split_top_level(value):
        chunk = chunk.strip()
        if not chunk or chunk.lower() == "none":
            continue
        match = re.match(
            r"^(inset\s+)?([-\d.]+(?:px|pt)?)\s+([-\d.]+(?:px|pt)?)\s*([-\d.]+(?:px|pt)?)?\s*([-\d.]+(?:px|pt)?)?\s*(.*)$",
            chunk,
            re.I,
        )
        if not match:
            continue
        inset = bool(match.group(1))
        try:
            x = parse_length(match.group(2)).resolve(font_size_pt=font_size_pt)
            y = parse_length(match.group(3)).resolve(font_size_pt=font_size_pt)
            blur = parse_length(match.group(4)).resolve(font_size_pt=font_size_pt) if match.group(4) else 0.0
            spread = parse_length(match.group(5)).resolve(font_size_pt=font_size_pt) if match.group(5) else 0.0
        except (AttributeError, TypeError):
            continue
        color = util.parse_color(match.group(6).strip()) if match.group(6).strip() else None
        shadows.append(
            {
                "inset": inset,
                "x": x,
                "y": y,
                "blur": max(0.0, blur or 0.0),
                "spread": spread or 0.0,
                "color": color or (0, 0, 0, 0.25),
            }
        )
    return shadows


def parse_transform(value):
    """Return a dict {'rotate': deg, 'scale': (sx, sy), 'translate': (x, y)}.

    ``translate`` keeps *percent* components unresolved (``Percent`` instances),
    because "translateX(-50%)" means half of the element's own width — a number
    the layout engine only knows after it has measured the box.
    """
    result = {"rotate": 0.0, "scale": (1.0, 1.0), "translate": (0.0, 0.0)}
    if not value or value.strip().lower() == "none":
        return result
    for name, args in re.findall(r"([-\w]+)\(([^()]*)\)", value):
        name = name.lower()
        parts = [p.strip() for p in args.split(",") if p.strip()]
        if name == "rotate":
            angle = _parse_angle(parts[0]) if parts else 0.0
            result["rotate"] += angle or 0.0
        elif name == "scale":
            sx = float(parts[0]) if parts else 1.0
            sy = float(parts[1]) if len(parts) > 1 else sx
            result["scale"] = (result["scale"][0] * sx, result["scale"][1] * sy)
        elif name in ("translate", "translatex", "translatey"):
            offset_x, offset_y = _translate_offsets(name, parts)
            current_x, current_y = result["translate"]
            result["translate"] = (
                _add_offset(current_x, offset_x),
                _add_offset(current_y, offset_y),
            )
    return result


def _add_offset(current, incoming):
    """Add two translate components while keeping ``Percent`` a ``Percent``.

    ``0.0 + Percent(-0.5)`` returns a plain ``float``: ``float.__add__`` drops the
    subclass, so a naive sum silently degrades "translateX(-50%)" to a raw -0.5
    that is later read as "-0.5 pt" instead of "half my own width".
    """
    if isinstance(current, Percent) and not isinstance(incoming, Percent):
        return current
    if isinstance(incoming, Percent) and not isinstance(current, Percent):
        return incoming
    if isinstance(current, Percent) and isinstance(incoming, Percent):
        return Percent(float(current) + float(incoming))
    return (current or 0.0) + (incoming or 0.0)


def _translate_offsets(name, parts):
    """Resolve one translate()/translateX()/translateY() into (x, y) components."""
    first = _translate_component(parts[0]) if parts else 0.0
    second = _translate_component(parts[1]) if len(parts) > 1 else 0.0
    if name == "translatex":
        return first, 0.0
    if name == "translatey":
        return 0.0, first
    return first, second


def _translate_component(token):
    """A length in pt, or a ``Percent`` when the token is a percentage."""
    token = (token or "").strip()
    if token.endswith("%"):
        try:
            return Percent(float(token[:-1]) / 100.0)
        except ValueError:
            return 0.0
    length = parse_length(token)
    return (length.resolve() if length is not None else 0.0) or 0.0


def resolve_translate(transform, width, height):
    """Turn the stored translate into points once the box size is known."""
    raw_x, raw_y = transform.get("translate", (0.0, 0.0))
    offset_x = width * float(raw_x) if isinstance(raw_x, Percent) else (raw_x or 0.0)
    offset_y = height * float(raw_y) if isinstance(raw_y, Percent) else (raw_y or 0.0)
    return offset_x, offset_y


GRID_TEMPLATE_RE = re.compile(r"^(?:(?:repeat|minmax)\([^()]*(?:\([^()]*\)[^()]*)*\)|[^\s]+)\s*.*$", re.I)


def parse_track_list(text, size=0.0, gap=0.0):
    """Expand a grid-template-columns/rows value into resolved track sizes.

    Supports ``1fr``, ``px/pt/%/em`` lengths, ``auto``, ``min-content``,
    ``max-content``, ``minmax()``, ``repeat(n, ...)`` and ``repeat(auto-fit, ...)``.
    """
    if not text:
        return []
    tracks = [_minmax_track(token) for token in _expand_tracks(text, size, gap)]
    resolved = []
    fr_total = 0.0
    fixed_total = gap * max(0, len(tracks) - 1)
    for token in tracks:
        if _is_fr(token):
            value = _fr_value(token)
            fr_total += value
            resolved.append(("fr", value))
        elif token.strip().lower() in ("auto", "min-content", "max-content", "fit-content"):
            resolved.append(("auto", 1.0))
        else:
            length = parse_length(token)
            width = (length.resolve(base_pt=size) if length is not None else 0.0) or 0.0
            fixed_total += width
            resolved.append(("px", width))
    free = max(0.0, size - fixed_total)
    out = []
    for kind, value in resolved:
        if kind == "fr":
            out.append(free * value / fr_total if fr_total else 0.0)
        elif kind == "auto":
            out.append(free / max(1, sum(1 for k, _ in resolved if k == "auto")) if any(k == "auto" for k, _ in resolved) else 0.0)
        else:
            out.append(value)
    return out


def _expand_tracks(text, size, gap):
    """Expand ``repeat()`` into a flat token list, sizing auto-fit by the minimum."""
    tracks = []
    for token in _split_tracks(text):
        repeat_match = re.match(
            r"^repeat\(\s*(auto-fit|auto-fill|\d+)\s*,\s*(.*)\)$", token.strip(), re.I | re.S
        )
        if not repeat_match:
            tracks.append(token)
            continue
        count_token, inner = repeat_match.groups()
        inner_tracks = _split_tracks(inner)
        if count_token.lower() in ("auto-fit", "auto-fill"):
            # auto-fit/auto-fill pick the column count from the track's *minimum*,
            # then each column is allowed to grow into its maximum.
            floor = 0.0
            for item in inner_tracks:
                floor += _track_floor(item, size)
            if floor > 0:
                # +gap twice: one gap between each pair, and the container's own
                # trailing edge has to fit the last column.
                count = max(1, int((size + gap) // (floor + gap)))
            else:
                # No intrinsic minimum (min-content / fr): one column per template
                # track is the only safe answer.
                count = max(1, len(inner_tracks) or 1)
            tracks.extend(inner_tracks * max(1, count))
        else:
            tracks.extend(inner_tracks * max(0, int(count_token)))
    return tracks


def _track_floor(token, size):
    """Smallest width a track may occupy (the ``min`` of ``minmax``)."""
    text = token.strip()
    match = _MINMAX_RE.match(text)
    if match:
        text = match.group(1).strip()
    if _is_fr(text):
        return 0.0
    if text.lower() in ("auto", "min-content", "max-content", "fit-content"):
        return 0.0
    length = parse_length(text)
    return (length.resolve(base_pt=size) if length is not None else 0.0) or 0.0


def _split_tracks(text):
    tracks = []
    depth = 0
    current = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char.isspace() and depth == 0:
            if current:
                tracks.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tracks.append("".join(current))
    return tracks


def _is_fr(token):
    return bool(re.match(r"^[\d.]+fr$", token.strip(), re.I))


_MINMAX_RE = re.compile(r"^minmax\(\s*([^,]+?)\s*,\s*(.+?)\s*\)$", re.I | re.S)


def _minmax_track(token):
    """Reduce ``minmax(a, b)`` to its upper bound.

    Grid treats the track as "at least a, at most b". A fixed-height deck has no
    room to grow, so the upper bound is the one that decides the column width —
    and it is the value the flexible/fixed split below has to look at. Without
    this reduction ``parse_length("minmax(200px,1fr)")`` returns ``None`` and the
    caller crashes on ``None.resolve(...)``.
    """
    match = _MINMAX_RE.match(token.strip())
    if match:
        return match.group(2).strip()
    return token


def _fr_value(token):
    match = re.match(r"^([\d.]+)fr$", token.strip(), re.I)
    return float(match.group(1)) if match else 1.0


def parse_align_items(value):
    raw = (value or "").strip().lower()
    return {
        "center": "center",
        "flex-start": "start",
        "start": "start",
        "self-start": "start",
        "baseline": "start",
        "flex-end": "end",
        "end": "end",
        "self-end": "end",
        "stretch": "stretch",
    }.get(raw, "stretch")


def parse_justify_content(value):
    raw = (value or "").strip().lower()
    if raw in ("space-between", "space-evenly", "space-around"):
        return "space-between"
    if raw in ("center", "start", "end", "flex-start", "flex-end", "left", "right", "normal"):
        if raw in ("center",):
            return "space-center"
        return "end" if raw in ("end", "flex-end", "right") else "start"
    return "start"


def parse_grid_column(value):
    """``span 2`` / ``2 / span 3`` / ``2`` -> ``(start, span)``; ``(None, 1)`` if absent.

    ``start`` is 1-based, ``None`` means "auto placement". ``span`` defaults to 1.
    """
    raw = (value or "").strip().lower()
    if not raw or raw == "auto":
        return (None, 1)
    span = 1
    start = None
    for part in (piece.strip() for piece in raw.split("/")):
        if part.startswith("span"):
            digits = part[4:].strip()
            if digits.isdigit():
                span = max(1, int(digits))
        elif part.isdigit():
            if start is None:
                start = max(1, int(part))
            else:
                span = max(1, int(part))
    return (start, span)


def parse_align_content(value):
    """Grid cross-axis distribution -> ``start`` / ``center`` / ``end`` / ``space-between``."""
    raw = (value or "").strip().lower()
    if raw in ("center",):
        return "center"
    if raw in ("end", "flex-end"):
        return "end"
    if raw in ("space-between", "space-around", "space-evenly"):
        return "space-between"
    return "start"


_OBJECT_POSITION_KEYWORDS = {
    "left": 0.0, "top": 0.0, "center": 50.0,
    "right": 100.0, "bottom": 100.0,
}


def parse_object_position(value):
    """``"right bottom"`` / ``"50% 20%"`` -> ``(x, y)`` as fractions of the slack."""
    raw = (value or "").strip().lower()
    if not raw:
        return (0.5, 0.5)
    parts = [part for part in raw.split() if part]
    if len(parts) == 1:
        parts = parts * 2

    def component(token):
        token = token.strip()
        if token in _OBJECT_POSITION_KEYWORDS:
            return _OBJECT_POSITION_KEYWORDS[token] / 100.0
        if token.endswith("%"):
            try:
                return float(token[:-1]) / 100.0
            except ValueError:
                return 0.5
        try:
            return float(token) / 100.0
        except ValueError:
            return 0.5

    return (component(parts[0]), component(parts[1]))


def parse_aspect_ratio(value):
    """``"16/9"`` / ``"1.5"`` / ``"auto"`` -> a float ratio or ``None``."""
    raw = (value or "").strip().lower()
    if not raw or raw == "auto":
        return None
    if "/" in raw:
        left, _, right = raw.partition("/")
        try:
            numerator = float(left.strip())
            denominator = float(right.strip())
        except ValueError:
            return None
        if numerator > 0 and denominator > 0:
            return numerator / denominator
        return None
    try:
        ratio = float(raw)
    except ValueError:
        return None
    return ratio if ratio > 0 else None


def parse_text_align(value):
    raw = (value or "").strip().lower()
    if raw in ("center", "middle", "justify-all"):
        return "center"
    if raw == "justify":
        return "justify"
    if raw in ("right", "end"):
        return "right"
    if raw == "start":
        return "left"
    return "left"
