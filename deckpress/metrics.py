"""Text metrics backed by the real installed fonts (PIL/FreeType).

Falls back to a conservative advance-width table when a font file is missing, so
a build never fails because of typography.
"""

from __future__ import annotations

import os

from . import util

_FONT_DIRS = [
    os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts",
    os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts"),
    "/usr/share/fonts/truetype",
    "/Library/Fonts",
    "/System/Library/Fonts",
]

# family keyword -> (regular, bold, italic, bolditalic)
_FAMILY_FILES = {
    "inter": ("Inter-Regular.ttf", "Inter-Bold.ttf", "Inter-Italic.ttf", "Inter-BoldItalic.ttf"),
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "helvetica": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "segoe": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "roboto": ("Roboto-Regular.ttf", "Roboto-Bold.ttf", "Roboto-Italic.ttf", "Roboto-BoldItalic.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "times": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "garamond": ("gara.ttf", "garabd.ttf", "garait.ttf", "garabi.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    "consolas": ("consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
    "courier": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    "franklin": ("framd.ttf", "framd.ttf", "framd.ttf", "framd.ttf"),
    "yahei": ("msyh.ttc", "msyhbd.ttc", "msyh.ttc", "msyhbd.ttc"),
    "微软雅黑": ("msyh.ttc", "msyhbd.ttc", "msyh.ttc", "msyhbd.ttc"),
    "simhei": ("simhei.ttf", "simhei.ttf", "simhei.ttf", "simhei.ttf"),
    "黑体": ("simhei.ttf", "simhei.ttf", "simhei.ttf", "simhei.ttf"),
    "simsun": ("simsun.ttc", "simsun.ttc", "simsun.ttc", "simsun.ttc"),
    "宋体": ("simsun.ttc", "simsun.ttc", "simsun.ttc", "simsun.ttc"),
    "kaiti": ("simkai.ttf", "simkai.ttf", "simkai.ttf", "simkai.ttf"),
    "fangsong": ("simfang.ttf", "simfang.ttf", "simfang.ttf", "simfang.ttf"),
    "dengxian": ("Deng.ttf", "Dengb.ttf", "Deng.ttf", "Dengb.ttf"),
    "等线": ("Deng.ttf", "Dengb.ttf", "Deng.ttf", "Dengb.ttf"),
    "source han": ("SourceHanSansSC-Regular.otf", "SourceHanSansSC-Bold.otf", "SourceHanSansSC-Regular.otf", "SourceHanSansSC-Bold.otf"),
    "思源": ("SourceHanSansSC-Regular.otf", "SourceHanSansSC-Bold.otf", "SourceHanSansSC-Regular.otf", "SourceHanSansSC-Bold.otf"),
}

# Arial/Helvetica advance widths (1/1000 em) for ASCII, used when PIL cannot
# load a font file. Values follow the classic Helvetica AFM metrics.
_ARIAL_WIDTHS = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191,
    "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556, "7": 556,
    "8": 556, "9": 556, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
    "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556, "o": 556,
    "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722,
    "x": 500, "y": 500, "z": 500, "{": 334, "}": 334, "|": 260, "~": 584,
}
_BOLD_FACTOR = 1.045


class FontBook:
    """Resolves CSS font stacks to concrete font files and measures text."""

    def __init__(self):
        self._files = {}
        self._pil_fonts = {}
        self._scan = None
        self._pil = None
        self._cjk_path = "unset"
        try:  # pragma: no cover - platform dependent
            from PIL import ImageFont

            self._pil = ImageFont
        except Exception:  # pragma: no cover
            self._pil = None

    # -- font discovery ---------------------------------------------------
    def _directory_index(self):
        if self._scan is not None:
            return self._scan
        index = {}
        for directory in _FONT_DIRS:
            if not directory or not os.path.isdir(directory):
                continue
            try:
                for name in os.listdir(directory):
                    index.setdefault(name.lower(), os.path.join(directory, name))
            except OSError:
                continue
        self._scan = index
        return index

    def _find_file(self, name):
        if not name:
            return None
        lower = name.lower()
        if os.path.isabs(name) and os.path.exists(name):
            return name
        index = self._directory_index()
        if lower in index:
            return index[lower]
        stem, ext = os.path.splitext(lower)
        for key, path in index.items():
            if key.startswith(stem) and key.endswith(ext):
                return path
        return None

    def face_for(self, stack, bold=False, italic=False):
        """Return (font_file, family_name) for a CSS font stack."""
        families = [part.strip().strip("'\"") for part in (stack or "").split(",") if part.strip()]
        slot = (1 if bold else 0) + (2 if italic else 0)
        for family in families:
            key = family.lower()
            candidates = _FAMILY_FILES.get(key)
            if candidates:
                path = self._find_file(candidates[slot]) or self._find_file(candidates[0])
                if path:
                    return path, family
            path = self._find_file(family.replace(" ", "") + ".ttf") or self._find_file(family)
            if path and path.lower().endswith((".ttf", ".otf", ".ttc")):
                return path, family
        fallback = _FAMILY_FILES["inter"][slot]
        path = self._find_file(fallback) or self._find_file(_FAMILY_FILES["segoe"][slot])
        return path, families[0] if families else "Inter"

    def powerpoint_family(self, stack):
        """Family name to write into the PPTX.

        The first *installed* family in the stack wins, so a deck authored with a
        webfont the renderer lacks (``Inter`` on a stock Windows box) still lands
        on a real face instead of a silent substitution with different metrics —
        the written name and the name used for measurement always agree.
        """
        families = [part.strip().strip("'\"") for part in (stack or "").split(",") if part.strip()]
        generic = {"sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy"}
        candidates = [name for name in families if name.lower() not in generic]
        if not candidates:
            return "Inter"
        for name in candidates:
            if self._installed(name):
                return name
        return candidates[0]

    def _installed(self, family):
        key = family.lower()
        filenames = _FAMILY_FILES.get(key)
        if filenames:
            if any(self._find_file(name) for name in filenames):
                return True
        stem = family.replace(" ", "")
        return bool(self._find_file(stem + ".ttf") or self._find_file(stem) or self._find_file(stem + ".otf"))

    # -- measurement ------------------------------------------------------
    def _pil_font(self, path, size_px, bold):
        key = (path, int(size_px * 8))
        cached = self._pil_fonts.get(key)
        if cached is not None:
            return cached
        font = None
        if self._pil is not None and path:
            try:
                font = self._pil.truetype(path, max(1, int(round(size_px * 8))))
            except Exception:
                font = None
        self._pil_fonts[key] = font
        return font

    def text_width_pt(self, text, stack, size_pt, bold=False, italic=False, letter_spacing_pt=0.0):
        if not text:
            return 0.0
        width = 0.0
        for segment, is_cjk in _split_scripts(text):
            if is_cjk:
                width += self._cjk_width(segment, stack, size_pt, bold)
            else:
                width += self._latin_width(segment, stack, size_pt, bold, italic)
        if letter_spacing_pt:
            width += letter_spacing_pt * len(text)
        return width

    def _latin_width(self, text, stack, size_pt, bold, italic):
        path, _family = self.face_for(stack, bold, italic)
        font = self._pil_font(path, size_pt / util.PT_PER_PX, bold)
        width = None
        if font is not None:
            try:
                width = font.getlength(text) / 8.0 * util.PT_PER_PX
            except Exception:
                width = None
        if width is None:
            width = _estimate_width(text, size_pt) * (_BOLD_FACTOR if bold else 1.0)
        elif bold and not str(path).lower().endswith(("bd.ttf", "b.ttf", "bold.ttf", "bd.ttc")):
            width *= _BOLD_FACTOR
        return width

    def _cjk_width(self, text, stack, size_pt, bold):
        """CJK glyphs are full-width; measure them with a CJK-capable face."""
        path = self._cjk_face(stack)
        font = self._pil_font(path, size_pt / util.PT_PER_PX, bold)
        if font is not None:
            try:
                width = font.getlength(text) / 8.0 * util.PT_PER_PX
                if width > 0:
                    return width
            except Exception:
                pass
        # Fall back to the typographic truth for CJK: one em per ideograph.
        units = 0.0
        for char in text:
            units += 0.5 if char in _HALF_WIDTH_CJK else 1.0
        return units * size_pt

    def _cjk_face(self, stack):
        cached = getattr(self, "_cjk_path", "unset")
        if cached != "unset":
            return cached
        path = None
        for family in ("Microsoft YaHei", "微软雅黑", "SimHei", "黑体", "PingFang SC",
                       "Source Han Sans SC", "Noto Sans CJK SC", "DengXian", "等线"):
            candidate = self._find_file(family.replace(" ", "") + ".ttf") or self._find_file(family)
            if candidate:
                path = candidate
                break
        if path is None:
            for key, candidate in self._directory_index().items():
                if key.startswith(("msyh", "simhei", "deng", "notosanscjk", "sourcehansans")):
                    path = candidate
                    break
        self._cjk_path = path
        return path

    def line_height_px(self, stack, size_px):
        """Approximate the CSS 'normal' line box for a font."""
        path, _family = self.face_for(stack)
        font = self._pil_font(path, size_px, False)
        if font is not None:
            try:
                ascent, descent = font.getmetrics()
                return (ascent + descent) / 8.0
            except Exception:
                pass
        return size_px * 1.32

    def natural_line_height_pt(self, stack, size_pt):
        """Smallest line box that still contains the font's ascent + descent."""
        return self.line_height_px(stack, size_pt / util.PT_PER_PX) * util.PT_PER_PX


def _estimate_width(text, size_pt):
    units = 0.0
    for char in text:
        if char in _ARIAL_WIDTHS:
            units += _ARIAL_WIDTHS[char]
        elif ord(char) < 128:
            units += 520
        elif _is_wide(char):
            units += 1000
        else:
            units += 560
    return units / 1000.0 * size_pt


def _is_wide(char):
    code = ord(char)
    return (
        0x1100 <= code <= 0x115F
        or 0x2E80 <= code <= 0xA4CF
        or 0xAC00 <= code <= 0xD7A3
        or 0xF900 <= code <= 0xFAFF
        or 0xFE30 <= code <= 0xFE6F
        or 0xFF00 <= code <= 0xFF60
        or 0xFFE0 <= code <= 0xFFE6
        or 0x1F300 <= code <= 0x1FAFF
    )


# Characters that occupy half a full-width cell in CJK typography.
_HALF_WIDTH_CJK = set("，。、！？；：（）【】「」『』〈〉《》·“”‘’…—～")


def _split_scripts(text):
    """Split into (segment, is_cjk) so each part is measured by the right face."""
    segments = []
    buffer = []
    current = None
    for char in text:
        flag = _is_wide(char)
        if current is None or flag == current:
            buffer.append(char)
            current = flag
            continue
        segments.append(("".join(buffer), current))
        buffer = [char]
        current = flag
    if buffer:
        segments.append(("".join(buffer), bool(current)))
    return segments
