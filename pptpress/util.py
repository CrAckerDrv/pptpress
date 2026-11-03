"""Small, dependency-free helpers: colours, units, numbers.

All geometry in this package is expressed in **points** (pt). Authoring is done
in CSS pixels (1px = 0.75pt), matching a 1280x720 px canvas = 13.333x7.5 inch
widescreen slide.
"""

from __future__ import annotations

import math
import re

EMU_PER_PT = 12700
EMU_PER_PX = 9525
PT_PER_PX = 0.75
MAX_EMU = 56 * 914400  # PowerPoint hard limit for a shape offset/extent


# --------------------------------------------------------------------------
# numbers
# --------------------------------------------------------------------------
def clamp(value, low, high):
    return low if value < low else high if value > high else value


def pt2emu(pt):
    return int(round(pt * EMU_PER_PT))


def px2pt(px):
    return px * PT_PER_PX


def fmt_num(value):
    """Compact decimal formatting used in generated XML/JSON."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def fmt_pct(value):
    return f"{value:.2f}".rstrip("0").rstrip(".") + "%"


# --------------------------------------------------------------------------
# colours
# --------------------------------------------------------------------------
_NAMED = {
    "transparent": (0, 0, 0, 0.0),
    "none": (0, 0, 0, 0.0),
    "black": (0, 0, 0, 1.0),
    "white": (255, 255, 255, 1.0),
    "red": (255, 0, 0, 1.0),
    "green": (0, 128, 0, 1.0),
    "blue": (0, 0, 255, 1.0),
    "yellow": (255, 255, 0, 1.0),
    "orange": (255, 165, 0, 1.0),
    "gray": (128, 128, 128, 1.0),
    "grey": (128, 128, 128, 1.0),
    "silver": (192, 192, 192, 1.0),
    "navy": (0, 0, 128, 1.0),
    "teal": (0, 128, 128, 1.0),
    "purple": (128, 0, 128, 1.0),
    "maroon": (128, 0, 0, 1.0),
    "olive": (128, 128, 0, 1.0),
    "lime": (0, 255, 0, 1.0),
    "aqua": (0, 255, 255, 1.0),
    "cyan": (0, 255, 255, 1.0),
    "fuchsia": (255, 0, 255, 1.0),
    "magenta": (255, 0, 255, 1.0),
    "pink": (255, 192, 203, 1.0),
    "brown": (165, 42, 42, 1.0),
    "gold": (255, 215, 0, 1.0),
    "indigo": (75, 0, 130, 1.0),
    "violet": (238, 130, 238, 1.0),
    "beige": (245, 245, 220, 1.0),
    "ivory": (255, 255, 240, 1.0),
    "coral": (255, 127, 80, 1.0),
    "salmon": (250, 128, 114, 1.0),
    "khaki": (240, 230, 140, 1.0),
    "plum": (221, 160, 221, 1.0),
    "orchid": (218, 112, 214, 1.0),
    "crimson": (220, 20, 60, 1.0),
    "tomato": (255, 99, 71, 1.0),
    "turquoise": (64, 224, 208, 1.0),
    "skyblue": (135, 206, 235, 1.0),
    "slategray": (112, 128, 144, 1.0),
    "whitesmoke": (245, 245, 245, 1.0),
    "lightgray": (211, 211, 211, 1.0),
    "darkgray": (169, 169, 169, 1.0),
    "dimgray": (105, 105, 105, 1.0),
}

_RGB_RE = re.compile(r"^rgba?\(\s*([^)]*)\)$", re.I)
_HSL_RE = re.compile(r"^hsla?\(\s*([^)]*)\)$", re.I)
_HEX_RE = re.compile(r"^#([0-9a-f]{3,8})$", re.I)


def _split_args(raw):
    """Split ``rgb()`` style arguments on commas or slashes."""
    raw = raw.replace("/", " ")
    parts = [p for p in re.split(r"[\s,]+", raw.strip()) if p]
    return parts


def _parse_channel(text, scale=255.0):
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0 * scale
    return float(text)


def _parse_alpha(text):
    text = text.strip()
    if not text:
        return 1.0
    if text.endswith("%"):
        return clamp(float(text[:-1]) / 100.0, 0.0, 1.0)
    return clamp(float(text), 0.0, 1.0)


def _hsl_to_rgb(h, s, l):
    h = (h % 360) / 360.0
    s = clamp(s, 0.0, 1.0)
    l = clamp(l, 0.0, 1.0)
    if s == 0:
        v = l * 255.0
        return (v, v, v)
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def channel(t):
        t = t % 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 0.5:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    return (channel(h + 1 / 3) * 255.0, channel(h) * 255.0, channel(h - 1 / 3) * 255.0)


def parse_color(value, default=None):
    """Return ``(r, g, b, a)`` with channels 0-255 and alpha 0-1, or default."""
    if value is None:
        return default
    if isinstance(value, (tuple, list)):
        r, g, b = (float(v) for v in value[:3])
        a = float(value[3]) if len(value) > 3 else 1.0
        return (clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255), clamp(a, 0, 1))
    text = str(value).strip()
    if not text or text.lower() in ("none", "transparent"):
        return (0, 0, 0, 0.0) if text else default
    low = text.lower().replace(" ", "").replace("_", "")
    if low in _NAMED:
        return _NAMED[low]
    match = _HEX_RE.match(text)
    if match:
        digits = match.group(1)
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) not in (6, 8):
            return default
        r = int(digits[0:2], 16)
        g = int(digits[2:4], 16)
        b = int(digits[4:6], 16)
        a = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
        return (r, g, b, a)
    match = _RGB_RE.match(text)
    if match:
        parts = _split_args(match.group(1))
        if len(parts) < 3:
            return default
        return (
            clamp(_parse_channel(parts[0]), 0, 255),
            clamp(_parse_channel(parts[1]), 0, 255),
            clamp(_parse_channel(parts[2]), 0, 255),
            _parse_alpha(parts[3] if len(parts) > 3 else ""),
        )
    match = _HSL_RE.match(text)
    if match:
        parts = _split_args(match.group(1))
        if len(parts) < 3:
            return default
        hue = float(parts[0].replace("deg", ""))
        sat = _parse_channel(parts[1], 1.0)
        light = _parse_channel(parts[2], 1.0)
        r, g, b = _hsl_to_rgb(hue, sat, light)
        return (r, g, b, _parse_alpha(parts[3] if len(parts) > 3 else ""))
    return default


def to_hex(color):
    r, g, b = (int(round(clamp(c, 0, 255))) for c in color[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def to_dml(color):
    """Six-digit uppercase hex without ``#``, as DrawingML ``val`` requires."""
    r, g, b = (int(round(clamp(c, 0, 255))) for c in color[:3])
    return f"{r:02X}{g:02X}{b:02X}"


def to_css(color):
    r, g, b = (int(round(clamp(c, 0, 255))) for c in color[:3])
    alpha = 1.0 if len(color) < 4 else clamp(color[3], 0.0, 1.0)
    if alpha >= 1.0:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r},{g},{b},{alpha:.3f})"


def alpha_of(color):
    return 1.0 if color is None or len(color) < 4 else clamp(color[3], 0.0, 1.0)


def with_alpha(color, alpha):
    r, g, b = color[:3]
    return (r, g, b, clamp(alpha, 0.0, 1.0))


def mix(color_a, color_b, ratio=0.5):
    """Blend ``color_b`` over ``color_a`` by ratio (0 = a, 1 = b)."""
    ratio = clamp(ratio, 0.0, 1.0)
    a_alpha = alpha_of(color_a)
    b_alpha = alpha_of(color_b)
    out_alpha = a_alpha + (b_alpha - a_alpha) * ratio
    if out_alpha <= 0:
        return (0, 0, 0, 0.0)
    out = []
    for index in range(3):
        blended = color_a[index] * a_alpha * (1 - ratio) + color_b[index] * b_alpha * ratio
        out.append(clamp(blended / out_alpha, 0, 255))
    return (out[0], out[1], out[2], out_alpha)


def luminance(color):
    """WCAG relative luminance (0 = black, 1 = white)."""

    def channel(value):
        value = clamp(value / 255.0, 0.0, 1.0)
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color[0]) + 0.7152 * channel(color[1]) + 0.0722 * channel(color[2])


def contrast_ratio(fg, bg):
    la, lb = luminance(fg), luminance(bg)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def readable_on(background, light=(255, 255, 255), dark=(17, 17, 17)):
    return light if luminance(background) < 0.45 else dark


_WIDE_RANGES = (
    (0x1100, 0x115F), (0x2E80, 0xA4CF), (0xAC00, 0xD7A3), (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F), (0xFF00, 0xFF60), (0xFFE0, 0xFFE6), (0x1F300, 0x1FAFF),
    (0x3000, 0x303F),
)


def is_wide_char(char):
    """True for full-width glyphs (CJK, Hangul, emoji)."""
    code = ord(char)
    return any(low <= code <= high for low, high in _WIDE_RANGES)
