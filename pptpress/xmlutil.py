"""Low-level DrawingML helpers: fills, lines, shadows, gradients, fonts.

Everything here writes *native* PowerPoint XML so the exported deck stays fully
editable — nothing is rasterised.
"""

from __future__ import annotations

import copy

from lxml import etree
from pptx.oxml.ns import qn

from . import util

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _el(tag, **attrs):
    element = etree.SubElement(etree.Element("dummy"), qn(tag))
    for key, value in attrs.items():
        element.set(key, str(value))
    parent = element.getparent()
    parent.remove(element)
    return element


def make(tag, **attrs):
    element = etree.Element(qn(tag), nsmap=None)
    for key, value in attrs.items():
        name = key.replace("_", "-") if key.startswith("no") is False else key
        element.set(name, str(value))
    return element


def sub(parent, tag, **attrs):
    element = etree.SubElement(parent, qn(tag))
    for key, value in attrs.items():
        if value is None:
            continue
        element.set(key.replace("_", "-"), str(value))
    return element


# --------------------------------------------------------------------------
# colours and fills
# --------------------------------------------------------------------------
def color_element(color):
    """solidFill child for a colour tuple."""
    fill = etree.Element(qn("a:solidFill"))
    rgb = util.to_dml(color)
    alpha = util.alpha_of(color)
    clr = etree.SubElement(fill, qn("a:srgbClr"), val=rgb)
    if alpha < 0.999:
        etree.SubElement(clr, qn("a:alpha"), val=str(int(round(alpha * 100000))))
    return fill


def gradient_element(gradient, angle_deg=None):
    """Build ``<a:gradFill>`` approximating a CSS gradient (linear or radial)."""
    grad = etree.Element(qn("a:gradFill"), rotWithShape="1")
    stops = etree.SubElement(grad, qn("a:gsLst"))
    for stop in gradient.stops:
        gs = etree.SubElement(stops, qn("a:gs"), pos=str(int(round(util.clamp(stop.position, 0, 1) * 100000))))
        rgb = util.to_dml(stop.color)
        clr = etree.SubElement(gs, qn("a:srgbClr"), val=rgb)
        alpha = util.alpha_of(stop.color)
        if alpha < 0.999:
            etree.SubElement(clr, qn("a:alpha"), val=str(int(round(alpha * 100000))))
    if (gradient.kind or "linear") == "radial":
        # CSS radial gradients map onto a circular DrawingML path; the rectangle
        # is treated as the outer edge of the ellipse.
        path = etree.SubElement(grad, qn("a:path"), path="circle")
        etree.SubElement(path, qn("a:fillToRect"), l="50000", t="50000", r="50000", b="50000")
        return grad
    lin = etree.SubElement(grad, qn("a:lin"))
    angle = gradient.angle if angle_deg is None else angle_deg
    # CSS 0deg = to top, PowerPoint 0 = to right; both increase clockwise.
    lin.set("ang", str(int(round(((angle - 90.0) % 360.0) * 60000))))
    lin.set("scaled", "0")
    return grad


def background_fill(background, shape_width, shape_height):
    """Return a fill element for a Background, or None."""
    if background is None:
        return None
    if background.gradients:
        gradient = background.gradients[0]
        gradient.width = shape_width
        gradient.height = shape_height
        if len(background.gradients) > 1 and background.color is None:
            # Approximate overlapping gradients by their average midpoint.
            pass
        return gradient_element(gradient)
    if background.color is not None and util.alpha_of(background.color) > 0.001:
        return color_element(background.color)
    return None


def set_fill(shape, background, width, height):
    sp_pr = shape._element.spPr
    for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill"):
        for element in sp_pr.findall(qn(tag)):
            sp_pr.remove(element)
    fill = background_fill(background, width, height)
    if fill is not None:
        # A shape's fill must appear in the schema-defined position.
        ordered_insert(sp_pr, fill)
    else:
        ordered_insert(sp_pr, etree.Element(qn("a:noFill")))


def ordered_insert(sp_pr, element):
    """Insert a child of ``spPr`` keeping the CT_ShapeProperties order."""
    order = [
        "a:xfrm", "a:custGeom", "a:prstGeom", "a:noFill", "a:solidFill",
        "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill", "a:ln",
        "a:effectLst", "a:effectDag", "a:scene3d", "a:sp3d", "a:extLst",
    ]
    tag = etree.QName(element).localname
    target = f"a:{tag}"
    _FILL_TAGS = ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")
    if tag in _FILL_TAGS:
        for fill_tag in _FILL_TAGS:
            for existing in sp_pr.findall(qn(f"a:{fill_tag}")):
                sp_pr.remove(existing)
    try:
        index = order.index(target)
    except ValueError:
        sp_pr.append(element)
        return element
    for existing in sp_pr.findall(qn(target)):
        sp_pr.remove(existing)
    insert_at = len(sp_pr)
    for position, child in enumerate(sp_pr):
        child_name = etree.QName(child).localname
        child_tag = f"a:{child_name}"
        if child_tag in order and order.index(child_tag) > index:
            insert_at = position
            break
    sp_pr.insert(insert_at, element)
    return element


def set_line(shape, width_pt, color, dash=None, opacity=1.0):
    line = shape.line
    line.width = util.pt2emu(max(0.1, width_pt))
    if color is None:
        line.fill.background()
        return
    color = util.with_alpha(color, util.alpha_of(color) * opacity)
    line.fill.solid()
    line.fill.fore_color.rgb = _rgb(color)
    if dash:
        ln = shape._element.spPr.find(qn("a:ln"))
        if ln is not None:
            prst = ln.find(qn("a:prstDash"))
            if prst is None:
                prst = etree.SubElement(ln, qn("a:prstDash"))
            prst.set("val", dash)


def no_line(shape):
    sp_pr = shape._element.spPr
    ln = sp_pr.find(qn("a:ln"))
    if ln is None:
        ln = ordered_insert(sp_pr, etree.Element(qn("a:ln")))
        ln.set("w", "0")
        etree.SubElement(ln, qn("a:noFill"))
        return
    for child in list(ln):
        ln.remove(child)
    etree.SubElement(ln, qn("a:noFill"))


class _RGB:
    __slots__ = ("red", "green", "blue")

    def __init__(self, red, green, blue):
        self.red, self.green, self.blue = red, green, blue

    def __iter__(self):
        return iter((self.red, self.green, self.blue))

    def __str__(self):
        return f"{int(self.red):02X}{int(self.green):02X}{int(self.blue):02X}"


def _rgb(color):
    from pptx.dml.color import RGBColor

    return RGBColor(int(color[0]), int(color[1]), int(color[2]))


# --------------------------------------------------------------------------
# effects
# --------------------------------------------------------------------------
def set_shadow(shape, shadows):
    """Apply the first drop shadow (PowerPoint supports one outer shadow)."""
    sp_pr = shape._element.spPr
    for effect in sp_pr.findall(qn("a:effectLst")):
        sp_pr.remove(effect)
    effect_lst = ordered_insert(sp_pr, etree.Element(qn("a:effectLst")))
    outer = None
    for shadow in shadows:
        if shadow.get("inset"):
            continue
        distance = util.pt2emu((shadow["x"] ** 2 + shadow["y"] ** 2) ** 0.5)
        angle = 0.0
        if distance:
            import math

            angle = math.degrees(math.atan2(-shadow["y"], shadow["x"])) % 360.0
        if outer is None or shadow["blur"] > outer["blur"]:
            outer = {
                "blur": shadow["blur"],
                "distance": distance,
                "angle": angle,
                "color": shadow["color"],
                "spread": shadow.get("spread", 0.0),
            }
    if outer is None:
        for shadow in shadows:
            if not shadow.get("inset"):
                continue
            inner = etree.SubElement(effect_lst, qn("a:innerShdw"))
            inner.set("blurRad", str(util.pt2emu(shadow["blur"])))
            inner.set("dist", str(util.pt2emu((shadow["x"] ** 2 + shadow["y"] ** 2) ** 0.5)))
            inner.set("dir", str(int(round(5400000 + (shadow["x"] >= 0) * 0))))
            inner.append(color_element(shadow["color"]))
            return
        shape.shadow.inherit = False
        return
    shdw = etree.SubElement(effect_lst, qn("a:outerShdw"))
    shdw.set("blurRad", str(util.pt2emu(outer["blur"])))
    shdw.set("dist", str(util.pt2emu(outer["distance"])))
    shdw.set("dir", str(int(round(outer["angle"] * 60000))))
    shdw.set("algn", "ctr")
    shdw.set("rotWithShape", "0")
    shdw.append(color_element(outer["color"]))


def clear_effects(shape):
    sp_pr = shape._element.spPr
    for effect in sp_pr.findall(qn("a:effectLst")):
        sp_pr.remove(effect)
    shape.shadow.inherit = False


def set_run_shadow(run, shadow):
    """Attach an outer shadow to a single text run (``a:rPr/a:effectLst``).

    DrawingML allows an effect list on run properties, which is the only way a
    text shadow stays a *text* property instead of becoming a shape shadow.
    """
    import math

    r_pr = run._r.get_or_add_rPr()
    for effect in r_pr.findall(qn("a:effectLst")):
        r_pr.remove(effect)
    effect_lst = etree.SubElement(r_pr, qn("a:effectLst"))
    shdw = etree.SubElement(effect_lst, qn("a:outerShdw"))
    distance = (shadow.get("x", 0.0) ** 2 + shadow.get("y", 0.0) ** 2) ** 0.5
    angle = 0.0
    if distance:
        angle = math.degrees(math.atan2(-shadow.get("y", 0.0), shadow.get("x", 0.0))) % 360.0
    shdw.set("blurRad", str(util.pt2emu(shadow.get("blur", 0.0))))
    shdw.set("dist", str(util.pt2emu(distance)))
    shdw.set("dir", str(int(round(angle * 60000))))
    shdw.set("algn", "ctr")
    shdw.set("rotWithShape", "0")
    shdw.append(color_element(shadow.get("color", (0, 0, 0, 0.5))))


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------
def set_run_font(run, family, size_pt, bold=False, italic=False, color=None,
                 letter_spacing=0.0, underline=False, baseline=None, strike=False,
                 only_bold_italic=False):
    run.font.size = util.pt2emu(size_pt)
    run.font.bold = bool(bold)
    run.font.italic = bool(italic)
    if underline:
        run.font.underline = True
    if strike:
        # ``a:rPr@strike`` is a plain attribute, not a child element.
        run._r.get_or_add_rPr().set("strike", "sngStrike")
    if color is not None:
        run.font.color.rgb = _rgb(color)
        alpha = util.alpha_of(color)
        if alpha < 0.999:
            _set_run_alpha(run, alpha)
    family = first_family(family) or "Inter"
    run.font.name = family
    r_pr = run._r.get_or_add_rPr()
    latin = r_pr.find(qn("a:latin"))
    if latin is None:
        latin = etree.SubElement(r_pr, qn("a:latin"))
    latin.set("typeface", family)
    for tag in ("a:ea", "a:cs"):
        element = r_pr.find(qn(tag))
        if element is None:
            element = etree.SubElement(r_pr, qn(tag))
        element.set("typeface", _east_asian_family(family))
    if letter_spacing:
        r_pr.set("spc", str(int(round(letter_spacing * 100))))
    if baseline:
        r_pr.set("baseline", str(int(baseline * 1000)))


def first_family(stack):
    """``"'Inter', 'Segoe UI', sans-serif"`` -> ``"Inter"``."""
    if not stack:
        return ""
    for part in stack.split(","):
        name = part.strip().strip("'\"").strip()
        if not name:
            continue
        if name.lower() in ("sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy"):
            continue
        return name
    return stack.split(",")[0].strip().strip("'\"")


def _set_run_alpha(run, alpha):
    r_pr = run._r.get_or_add_rPr()
    fill = r_pr.find(qn("a:solidFill"))
    if fill is None:
        return
    clr = fill.find(qn("a:srgbClr"))
    if clr is None:
        return
    existing = clr.find(qn("a:alpha"))
    if existing is not None:
        existing.set("val", str(int(round(alpha * 100000))))
    else:
        etree.SubElement(clr, qn("a:alpha"), val=str(int(round(alpha * 100000))))


_EA_FALLBACKS = [
    ("inter", "Microsoft YaHei"),
    ("segoe", "Microsoft YaHei"),
    ("arial", "Microsoft YaHei"),
    ("helvetica", "Microsoft YaHei"),
    ("roboto", "Microsoft YaHei"),
    ("georgia", "SimSun"),
    ("times", "SimSun"),
    ("garamond", "SimSun"),
    ("calibri", "Microsoft YaHei"),
    ("cambria", "SimSun"),
    ("consolas", "Consolas"),
    ("source han", "Source Han Sans SC"),
]


def _east_asian_family(family):
    lower = (family or "").lower()
    if any(
        keyword in lower
        for keyword in ("yahei", "雅黑", "simhei", "黑体", "simsun", "宋体", "kaiti", "楷体", "dengxian", "等线", "song", "ming", "kai", "hei")
    ):
        return family
    for keyword, fallback in _EA_FALLBACKS:
        if keyword in lower:
            return fallback
    return "Microsoft YaHei"


def set_paragraph(paragraph, line_height_pt=None, space_before=0.0, space_after=0.0,
                  align="left", indent_pt=0.0, hanging_pt=None, level=0):
    paragraph.line_spacing = util.pt2emu(line_height_pt) if line_height_pt else None
    paragraph.space_before = util.pt2emu(space_before)
    paragraph.space_after = util.pt2emu(space_after)
    paragraph.level = level
    p_pr = paragraph._p.get_or_add_pPr()
    if align == "center":
        paragraph.alignment = 2  # PP_ALIGN.CENTER
    elif align == "right":
        paragraph.alignment = 3
    elif align == "justify":
        paragraph.alignment = 4
    else:
        paragraph.alignment = 1
    if hanging_pt:
        p_pr.set("marL", str(util.pt2emu(indent_pt)))
        p_pr.set("indent", str(-util.pt2emu(hanging_pt)))
    elif indent_pt:
        p_pr.set("marL", str(util.pt2emu(indent_pt)))
        p_pr.set("indent", "0")
    # Remove autofit surprises
    for tag in ("a:buNone",):
        if p_pr.find(qn(tag)) is None:
            etree.SubElement(p_pr, qn(tag))


def set_text_frame(frame, anchor="top", wrap=True, margins=(0.0, 0.0, 0.0, 0.0)):
    frame.word_wrap = wrap
    frame.vertical_anchor = {"top": 1, "middle": 2, "bottom": 3}.get(anchor, 1)
    left, top, right, bottom = margins
    frame.margin_left = util.pt2emu(left)
    frame.margin_top = util.pt2emu(top)
    frame.margin_right = util.pt2emu(right)
    frame.margin_bottom = util.pt2emu(bottom)
    body_pr = frame._txBody.find(qn("a:bodyPr"))
    if body_pr is not None:
        for child in list(body_pr):
            if child.tag in (qn("a:normAutofit"), qn("a:spAutoFit"), qn("a:noAutofit")):
                body_pr.remove(child)
        etree.SubElement(body_pr, qn("a:noAutofit"))
        body_pr.set("wrap", "square" if wrap else "none")


def add_soft_break(paragraph):
    br = etree.SubElement(paragraph._p, qn("a:br"))
    return br
