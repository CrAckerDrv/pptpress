"""SVG icon handling: inline SVG -> PNG (via a tiny built-in renderer).

Icons are the only element that is rasterised. Everything else stays native.
The renderer supports the subset used by icon sets (Tabler, Lucide, Feather):
paths (M/L/H/V/C/S/Q/T/A/Z + relative), circles, rects, polylines, polygons,
lines and groups, with stroke or fill painting.
"""

from __future__ import annotations

import io
import math
import re

from lxml import etree

from . import util

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


class _PathParser:
    def __init__(self, data):
        self.tokens = _NUM.findall(data or "")
        self.commands = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]", data or "")
        self.index = 0

    def _next(self):
        value = float(self.tokens[self.index])
        self.index += 1
        return value


def parse_svg(raw, color=None, size=256):
    """Rasterise an SVG string to a PNG byte string with a transparent backdrop."""
    from PIL import Image, ImageDraw

    root = etree.fromstring(raw.encode("utf-8") if isinstance(raw, str) else raw)
    view = _viewbox(root)
    scale = size / max(1e-6, max(view[2], view[3]))
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def transform_point(px, py):
        x = (px - view[0]) * scale
        y = (py - view[1]) * scale
        return (x, y)

    def paint_color(element, fallback):
        raw_color = color or element.get("stroke") or element.get("fill") or fallback
        if raw_color in (None, "none", "currentColor", "inherit"):
            raw_color = fallback
        parsed = util.parse_color(raw_color)
        return parsed or util.parse_color(fallback) or (0, 0, 0, 1)

    _walk(root, draw, transform_point, paint_color, color, scale, stroke_scale=scale)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _viewbox(root):
    raw = root.get("viewBox") or root.get("viewbox")
    if raw:
        values = [float(v) for v in _NUM.findall(raw)]
        if len(values) == 4:
            return values
    width = _NUM.findall(root.get("width") or "24")
    height = _NUM.findall(root.get("height") or "24")
    try:
        return [0.0, 0.0, float(width[0]), float(height[0])]
    except (IndexError, ValueError):
        return [0.0, 0.0, 24.0, 24.0]


def _parse_style(element):
    raw = element.get("style") or ""
    style = {}
    for part in raw.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            style[key.strip()] = value.strip()
    return style


def _paint_of(element, style, key, default=None):
    return style.get(key, element.get(key, default))


def _walk(element, draw, to_point, paint_color, forced, scale, stroke_scale):
    for child in element:
        if not isinstance(child.tag, str):
            continue
        tag = etree.QName(child).localname
        style = _parse_style(child)
        if tag in ("defs", "title", "desc", "style", "metadata"):
            continue
        if tag == "g":
            _walk(child, draw, to_point, paint_color, forced, scale, stroke_scale)
            continue
        stroke = _paint_of(child, style, "stroke")
        fill = _paint_of(child, style, "fill")
        stroke_width = _paint_of(child, style, "stroke-width", "2")
        try:
            width_px = float(_NUM.findall(str(stroke_width))[0]) * stroke_scale
        except (IndexError, ValueError):
            width_px = 2.0 * stroke_scale
        width_px = max(1.0, width_px)
        stroke_color = None
        if stroke not in (None, "none"):
            stroke_color = paint_color(child, _to_hex(forced) if forced else "#000000")
        fill_color = None
        if fill not in (None, "none"):
            if fill == "currentColor" or fill is None:
                fill_color = paint_color(child, _to_hex(forced) if forced else "#000000")
            else:
                fill_color = util.parse_color(fill)
            if fill_color is None:
                fill_color = paint_color(child, _to_hex(forced) if forced else "#000000")
        if stroke_color is None and fill_color is None:
            stroke_color = paint_color(child, _to_hex(forced) if forced else "#000000")
        linecap = _paint_of(child, style, "stroke-linecap", "round")
        joined = []
        if tag == "path":
            joined = _flatten_path(child.get("d") or "", to_point)
        elif tag == "circle":
            cx = float(child.get("cx") or 0)
            cy = float(child.get("cy") or 0)
            r = float(child.get("r") or 0)
            joined = _flatten_circle(cx, cy, r, to_point)
        elif tag == "ellipse":
            cx = float(child.get("cx") or 0)
            cy = float(child.get("cy") or 0)
            rx = float(child.get("rx") or 0)
            ry = float(child.get("ry") or 0)
            joined = _flatten_ellipse(cx, cy, rx, ry, to_point)
        elif tag == "rect":
            x = float(child.get("x") or 0)
            y = float(child.get("y") or 0)
            w = float(child.get("width") or 0)
            h = float(child.get("height") or 0)
            rx = float(child.get("rx") or 0)
            joined = _flatten_rect(x, y, w, h, rx, to_point)
        elif tag in ("polyline", "polygon"):
            raw = _NUM.findall(child.get("points") or "")
            points = [to_point(float(raw[i]), float(raw[i + 1])) for i in range(0, len(raw) - 1, 2)]
            joined = [("line", points, True, False)]
        elif tag == "line":
            x1 = float(child.get("x1") or 0)
            y1 = float(child.get("y1") or 0)
            x2 = float(child.get("x2") or 0)
            y2 = float(child.get("y2") or 0)
            joined = [("line", [to_point(x1, y1), to_point(x2, y2)], True, True)]
        for subpath in joined:
            _draw_subpath(draw, subpath, stroke_color, fill_color, width_px, linecap)
        if tag == "g" or child.find("{http://www.w3.org/2000/svg}g") is not None:
            _walk(child, draw, to_point, paint_color, forced, scale, stroke_scale)


def _to_hex(color):
    return util.to_hex(color) if color else "#000000"


def _draw_subpath(draw, subpath, stroke_color, fill_color, width_px, linecap):
    kind, points, closed, open_line = subpath
    if not points:
        return
    if fill_color is not None and (closed or "fill" in ()):
        if len(points) >= 3 and closed:
            rgb = tuple(int(c) for c in fill_color[:3])
            try:
                draw.polygon(points, fill=rgb)
            except (TypeError, ValueError):
                pass
    if stroke_color is None:
        return
    rgb = tuple(int(c) for c in stroke_color[:3])
    radius = width_px / 2.0
    if len(points) == 1:
        x, y = points[0]
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=rgb)
        return
    for index in range(len(points) - 1):
        _thick_line(draw, points[index], points[index + 1], rgb, width_px)
    if closed:
        _thick_line(draw, points[-1], points[0], rgb, width_px)
    if linecap == "round":
        for x, y in points:
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=rgb)


def _thick_line(draw, start, end, color, width_px):
    radius = width_px / 2.0
    draw.line([start, end], fill=color, width=int(round(width_px)), joint="curve")
    if radius > 0.8:
        for point in (start, end):
            draw.ellipse(
                [point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius],
                fill=color,
            )


def _flatten_path(data, to_point, steps=10):
    """Flatten an SVG path into polyline subpaths in device coordinates."""
    subpaths = []
    tokens = _NUM.findall(data)
    commands = re.findall(r"[A-Za-z]", data)
    if not commands:
        return subpaths
    cursor = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    points = []
    closed = False
    previous_command = ""
    previous_control = None
    token_index = 0

    def take(count):
        nonlocal token_index
        values = [float(tokens[token_index + i]) for i in range(count)]
        token_index += count
        return values

    for command in commands:
        relative = command.islower()
        letter = command.upper()
        if letter == "M":
            x, y = take(2)
            if relative:
                x, y = current[0] + x, current[1] + y
            if points:
                subpaths.append(("line", points, closed, False))
            points = [to_point(x, y)]
            current = (x, y)
            start = (x, y)
            closed = False
            # Extra coordinate pairs after M are implicit lineto.
            while token_index + 1 < len(tokens) and _command_boundary(commands, command, token_index):
                break
        elif letter == "L":
            x, y = take(2)
            if relative:
                x, y = current[0] + x, current[1] + y
            points.append(to_point(x, y))
            current = (x, y)
        elif letter == "H":
            (x,) = take(1)
            x = current[0] + x if relative else x
            points.append(to_point(x, current[1]))
            current = (x, current[1])
        elif letter == "V":
            (y,) = take(1)
            y = current[1] + y if relative else y
            points.append(to_point(current[0], y))
            current = (current[0], y)
        elif letter in ("C", "S", "Q", "T"):
            if letter == "C":
                x1, y1, x2, y2, x, y = take(6)
                if relative:
                    x1 += current[0]; y1 += current[1]; x2 += current[0]; y2 += current[1]; x += current[0]; y += current[1]
                control1 = (x1, y1)
                control2 = (x2, y2)
                previous_control = control2
            elif letter == "S":
                x2, y2, x, y = take(4)
                if relative:
                    x2 += current[0]; y2 += current[1]; x += current[0]; y += current[1]
                if previous_command in ("C", "S") and previous_control:
                    control1 = (2 * current[0] - previous_control[0], 2 * current[1] - previous_control[1])
                else:
                    control1 = current
                control2 = (x2, y2)
                previous_control = control2
            elif letter == "Q":
                qx, qy, x, y = take(4)
                if relative:
                    qx += current[0]; qy += current[1]; x += current[0]; y += current[1]
                control1 = (current[0] + 2 / 3 * (qx - current[0]), current[1] + 2 / 3 * (qy - current[1]))
                control2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
                previous_control = (qx, qy)
            else:
                x, y = take(2)
                if relative:
                    x += current[0]; y += current[1]
                if previous_command in ("Q", "T") and previous_control:
                    qx = 2 * current[0] - previous_control[0]
                    qy = 2 * current[1] - previous_control[1]
                else:
                    qx, qy = current
                control1 = (current[0] + 2 / 3 * (qx - current[0]), current[1] + 2 / 3 * (qy - current[1]))
                control2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
                previous_control = (qx, qy)
            for step in range(1, steps + 1):
                t = step / steps
                px = (
                    (1 - t) ** 3 * current[0]
                    + 3 * (1 - t) ** 2 * t * control1[0]
                    + 3 * (1 - t) * t ** 2 * control2[0]
                    + t ** 3 * x
                )
                py = (
                    (1 - t) ** 3 * current[1]
                    + 3 * (1 - t) ** 2 * t * control1[1]
                    + 3 * (1 - t) * t ** 2 * control2[1]
                    + t ** 3 * y
                )
                points.append(to_point(px, py))
            current = (x, y)
        elif letter == "A":
            rx, ry, rotation, large_arc, sweep, x, y = take(7)
            if relative:
                x += current[0]; y += current[1]
            arc_points = _flatten_arc(current, (x, y), rx, ry, rotation, large_arc, sweep, steps * 2)
            points.extend(to_point(px, py) for px, py in arc_points)
            current = (x, y)
        elif letter == "Z":
            closed = True
            subpaths.append(("line", points, True, False))
            points = [to_point(start[0], start[1])] if points else []
            current = start
            closed = False
            continue
        previous_command = letter
    if points:
        subpaths.append(("line", points, closed, False))
    # Remove the synthetic restart point left by Z closures.
    cleaned = []
    for kind, pts, is_closed, open_line in subpaths:
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) >= 2:
            cleaned.append((kind, pts, is_closed, open_line))
    return cleaned


def _command_boundary(commands, command, token_index):
    return False


def _flatten_arc(start, end, rx, ry, rotation, large_arc, sweep, steps):
    """Approximate an SVG elliptical arc with line segments."""
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [end]
    phi = math.radians(rotation)
    dx = (start[0] - end[0]) / 2.0
    dy = (start[1] - end[1]) / 2.0
    x1 = math.cos(phi) * dx + math.sin(phi) * dy
    y1 = -math.sin(phi) * dx + math.cos(phi) * dy
    lam = (x1 ** 2) / (rx ** 2) + (y1 ** 2) / (ry ** 2)
    if lam > 1:
        factor = math.sqrt(lam)
        rx *= factor
        ry *= factor
    sign = -1 if large_arc == sweep else 1
    numerator = max(0.0, rx ** 2 * ry ** 2 - rx ** 2 * y1 ** 2 - ry ** 2 * x1 ** 2)
    denominator = rx ** 2 * y1 ** 2 + ry ** 2 * x1 ** 2
    coefficient = sign * math.sqrt(numerator / denominator) if denominator else 0.0
    cx1 = coefficient * rx * y1 / ry
    cy1 = -coefficient * ry * x1 / rx
    cx = math.cos(phi) * cx1 - math.sin(phi) * cy1 + (start[0] + end[0]) / 2.0
    cy = math.sin(phi) * cx1 + math.cos(phi) * cy1 + (start[1] + end[1]) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = (math.hypot(ux, uy) * math.hypot(vx, vy)) or 1.0
        value = max(-1.0, min(1.0, dot / norm))
        result = math.acos(value)
        return -result if (ux * vy - uy * vx) < 0 else result

    theta1 = angle(1, 0, (x1 - cx1) / rx if rx else 0, (y1 - cy1) / ry if ry else 0)
    theta2 = angle((x1 - cx1) / rx if rx else 0, (y1 - cy1) / ry if ry else 0,
                   (-x1 - cx1) / rx if rx else 0, (-y1 - cy1) / ry if ry else 0)
    if not sweep and theta2 > 0:
        theta2 -= 2 * math.pi
    elif sweep and theta2 < 0:
        theta2 += 2 * math.pi
    points = []
    for step in range(1, steps + 1):
        t = theta1 + (theta2 - theta1) * step / steps
        px = cx + rx * math.cos(t) * math.cos(phi) - ry * math.sin(t) * math.sin(phi)
        py = cy + rx * math.cos(t) * math.sin(phi) + ry * math.sin(t) * math.cos(phi)
        points.append((px, py))
    if points:
        points[-1] = end
    return points


def _flatten_circle(cx, cy, r, to_point, steps=40):
    points = [
        to_point(cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]
    return [("line", points, True, False)]


def _flatten_ellipse(cx, cy, rx, ry, to_point, steps=40):
    points = [
        to_point(cx + rx * math.cos(2 * math.pi * i / steps), cy + ry * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]
    return [("line", points, True, False)]


def _flatten_rect(x, y, w, h, rx, to_point):
    if rx <= 0:
        points = [to_point(x, y), to_point(x + w, y), to_point(x + w, y + h), to_point(x, y + h)]
        return [("line", points, True, False)]
    rx = min(rx, w / 2, h / 2)
    steps = 6
    points = []
    corners = [
        (x + w - rx, y + rx, -math.pi / 2, 0),
        (x + w - rx, y + h - rx, 0, math.pi / 2),
        (x + rx, y + h - rx, math.pi / 2, math.pi),
        (x + rx, y + rx, math.pi, 3 * math.pi / 2),
    ]
    for cx, cy, start, end in corners:
        for step in range(steps + 1):
            angle = start + (end - start) * step / steps
            points.append(to_point(cx + rx * math.cos(angle), cy + rx * math.sin(angle)))
    return [("line", points, True, False)]


def svg_to_png(raw, output_path, color=None, scale=4):
    """Rasterise ``raw`` SVG to ``output_path`` (PNG). Returns the path or None."""
    try:
        payload = parse_svg(raw, color=color, size=24 * scale)
    except Exception:
        return None
    try:
        with open(output_path, "wb") as handle:
            handle.write(payload)
    except OSError:
        return None
    return output_path
