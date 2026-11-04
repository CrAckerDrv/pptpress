"""Native PPTX writer.

Every HTML element becomes an editable PowerPoint object:

* text -> a text box with real paragraphs and runs (still editable as a block)
* painted boxes -> autoshapes with solid/gradient/picture fills, borders, shadows
* images -> pictures with crop-based ``object-fit``
* icons -> small PNGs rasterised from inline SVG (the only rasterised element)
* tables -> native PowerPoint tables with merged cells and per-cell borders
* lists -> native bulleted paragraphs (``buChar``), still editable in PowerPoint
"""

from __future__ import annotations

import os

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu

from . import svgicon, svgshape, util, values, xmlutil

DASH_MAP = {"dashed": "dash", "dotted": "sysDot", "dashdot": "dashDot"}
BULLET_CHARS = {"disc": "•", "circle": "◦", "square": "▪", "none": ""}

ALIGN_MAP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}


class SlideWriter:
    def __init__(self, presentation, slide_box, base_dir="", cache_dir=None):
        self.prs = presentation
        self.box = slide_box
        self.base_dir = base_dir or ""
        self.cache_dir = cache_dir
        self.slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self.issues = []
        self.count = 0

    # -- entry -----------------------------------------------------------
    def write(self):
        self._background()
        for box in self.box.children:
            self._emit(box)
        if self.box.speaker_notes:
            self.slide.notes_slide.notes_text_frame.text = self.box.speaker_notes
        return self.slide

    def _background(self):
        background = self.box.background
        if background is None:
            return
        width, height = self.box.width, self.box.height
        needs_shape = (
            background.gradients
            or background.image
            or (background.color is not None and util.alpha_of(background.color) < 0.999)
        )
        if not needs_shape and background.color is not None:
            fill = self.slide.background.fill
            fill.solid()
            fill.fore_color.rgb = _rgb(background.color)
            return
        shape = self._rect(0.0, 0.0, width, height, "background")
        self._fill(shape, background, width, height)
        shape.line.fill.background()
        shape.name = "background"

    # -- dispatch --------------------------------------------------------
    def _emit(self, box):
        if box.width <= 0.2 or box.height <= 0.2:
            return
        if box.kind == "text":
            self._text(box)
        elif box.kind == "image":
            self._picture(box)
        elif box.kind == "svg":
            self._icon(box)
        elif box.kind == "table":
            self._table(box)
        else:
            self._container(box)

    # -- shapes ----------------------------------------------------------
    def _rect(self, x, y, width, height, name, shape=MSO_SHAPE.RECTANGLE):
        element = self.slide.shapes.add_shape(
            shape,
            Emu(util.pt2emu(x)),
            Emu(util.pt2emu(y)),
            Emu(max(1, util.pt2emu(width))),
            Emu(max(1, util.pt2emu(height))),
        )
        _detach_theme_style(element)
        element.shadow.inherit = False
        element.name = name
        self.count += 1
        return element

    def _rounded_shape(self, x, y, width, height, corners, name):
        """Build a rect with four independent elliptical corners.

        ``custGeom`` is the only DrawingML construct that can describe "24px on
        the top-left, square elsewhere" or "50% / 20%"; a roundRect's single
        adjustment can express neither.
        """
        shape = self._rect(x, y, width, height, name, MSO_SHAPE.RECTANGLE)
        sp_pr = shape._element.spPr
        for geometry in list(sp_pr):
            if geometry.tag in (qn("a:prstGeom"), qn("a:custGeom")):
                sp_pr.remove(geometry)
        custom = etree.Element(qn("a:custGeom"))
        path_list = etree.SubElement(custom, qn("a:pathLst"))
        path = etree.SubElement(path_list, qn("a:path"))
        path.set("w", str(int(round(util.pt2emu(max(0.01, width))))))
        path.set("h", str(int(round(util.pt2emu(max(0.01, height))))))
        box_w = max(0.01, width)
        box_h = max(0.01, height)

        def emit(command, point=None, **attributes):
            element = etree.SubElement(path, qn(f"a:{command}"))
            if point is not None:
                x_emu = etree.SubElement(element, qn("a:pt"))
                x_emu.set("x", str(int(round(point[0]))))
                x_emu.set("y", str(int(round(point[1]))))
            for key, value in attributes.items():
                if isinstance(value, (int, float)):
                    element.set(key, str(int(round(value))))
                else:
                    element.set(key, str(value))

        limit = min(box_w, box_h) / 2.0
        tl_x, tl_y = min(corners[0][0], limit), min(corners[0][1], limit)
        tr_x, tr_y = min(corners[1][0], limit), min(corners[1][1], limit)
        br_x, br_y = min(corners[2][0], limit), min(corners[2][1], limit)
        bl_x, bl_y = min(corners[3][0], limit), min(corners[3][1], limit)

        def to_emu(value):
            return util.pt2emu(value)

        emit("moveTo", point=(to_emu(tl_x), 0))
        emit("lnTo", point=(to_emu(box_w - tr_x), 0))
        if tr_x or tr_y:
            emit("arcTo", wR=to_emu(tr_x), hR=to_emu(tr_y), stAng=16200000, swAng=5400000)
        emit("lnTo", point=(to_emu(box_w), to_emu(box_h - br_y)))
        if br_x or br_y:
            emit("arcTo", wR=to_emu(br_x), hR=to_emu(br_y), stAng=0, swAng=5400000)
        emit("lnTo", point=(to_emu(bl_x), to_emu(box_h)))
        if bl_x or bl_y:
            emit("arcTo", wR=to_emu(bl_x), hR=to_emu(bl_y), stAng=5400000, swAng=5400000)
        emit("lnTo", point=(0, to_emu(tl_y)))
        if tl_x or tl_y:
            emit("arcTo", wR=to_emu(tl_x), hR=to_emu(tl_y), stAng=10800000, swAng=5400000)
        emit("close")
        xmlutil.ordered_insert(sp_pr, custom)
        return shape

    def _container(self, box):
        style = box.style
        if style.paint:
            x, y, width, height = box.rect
            corners = values.resolve_radius(style.radius, width, height)
            uneven = _corners_differ(corners)
            if uneven:
                # Per-corner or elliptical radii cannot be expressed by
                # roundRect's single adjustment, so the shape is built from an
                # explicit custom geometry instead of being silently squared off.
                shape = self._rounded_shape(x, y, width, height, corners, _name(box))
                self._fill(shape, style.background, width, height)
                if style.background is not None and style.background.image:
                    self._picture_fill(shape, style.background, width, height)
                self._outline(shape, box)
                if style.shadows:
                    try:
                        xmlutil.set_shadow(shape, style.shadows)
                    except Exception:
                        pass
                self._apply_rotation(shape, style)
                _strip_text(shape)
                for child in box.children:
                    self._emit(child)
                return
            shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if corners else MSO_SHAPE.RECTANGLE
            shape = self._rect(x, y, width, height, _name(box), shape_type)
            self._fill(shape, style.background, width, height)
            if style.background is not None and style.background.image:
                self._picture_fill(shape, style.background, width, height)
            self._outline(shape, box)
            if style.shadows:
                try:
                    xmlutil.set_shadow(shape, style.shadows)
                except Exception:
                    pass
            if corners and shape_type == MSO_SHAPE.ROUNDED_RECTANGLE:
                try:
                    shape.adjustments[0] = min(0.5, corners[0][0] / max(1.0, min(width, height)))
                except (IndexError, ValueError, TypeError):
                    pass
            self._apply_rotation(shape, style)
            _strip_text(shape)
        for child in box.children:
            self._emit(child)

    def _apply_rotation(self, shape, style):
        angle = style.transform.get("rotate") or 0.0
        if abs(angle) < 0.01:
            return
        shape.rotation = (-angle) % 360.0

    def _fill(self, shape, background, width, height):
        if background is None:
            shape.fill.background()
            return
        if background.gradients:
            gradient = background.gradients[0]
            gradient.width = width
            gradient.height = height
            sp_pr = shape._element.spPr
            for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill"):
                for existing in sp_pr.findall(qn(tag)):
                    sp_pr.remove(existing)
            xmlutil.ordered_insert(sp_pr, xmlutil.gradient_element(gradient))
            return
        if background.color is not None:
            shape.fill.solid()
            shape.fill.fore_color.rgb = _rgb(background.color)
            alpha = util.alpha_of(background.color)
            if alpha < 0.999:
                _set_fill_alpha(shape, alpha)
            return
        if not background.image:
            shape.fill.background()

    def _picture_fill(self, shape, background, width, height):
        path = self._asset(background.image)
        if not path:
            self.issues.append(f"missing background image: {background.image}")
            return
        try:
            self._blip_fill(shape, path, width, height)
        except Exception as error:  # pragma: no cover - defensive
            self.issues.append(f"background image failed: {error}")

    def _blip_fill(self, shape, path, width, height):
        from pptx.oxml.ns import nsdecls

        _image_part, rel_id = self.slide.part.get_or_add_image_part(path)
        crop = {"l": 0, "t": 0, "r": 0, "b": 0}
        intrinsic = _image_size(path)
        if intrinsic and intrinsic[0] and intrinsic[1] and width and height:
            source_ratio = intrinsic[0] / intrinsic[1]
            target_ratio = width / height
            if source_ratio > target_ratio:
                excess = 1.0 - target_ratio / source_ratio
                crop["l"] = crop["r"] = int(excess * 50000)
            elif source_ratio < target_ratio:
                excess = 1.0 - source_ratio / target_ratio
                crop["t"] = crop["b"] = int(excess * 50000)
        xml = (
            f'<a:blipFill {nsdecls("a", "r")} rotWithShape="1">'
            f'<a:blip r:embed="{rel_id}"/>'
            f'<a:srcRect l="{crop["l"]}" t="{crop["t"]}" r="{crop["r"]}" b="{crop["b"]}"/>'
            f"<a:stretch><a:fillRect/></a:stretch></a:blipFill>"
        )
        sp_pr = shape._element.spPr
        for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill"):
            for existing in sp_pr.findall(qn(tag)):
                sp_pr.remove(existing)
        xmlutil.ordered_insert(sp_pr, etree.fromstring(xml))

    def _outline(self, shape, box):
        border = box.style.border
        if not border:
            xmlutil.no_line(shape)
            return
        visible = [(index, side) for index, side in enumerate(border) if side and side.visible]
        if not visible:
            xmlutil.no_line(shape)
            return
        widths = {round(side.width, 2) for _index, side in visible}
        colors = {util.to_dml(side.color or (0, 0, 0, 1)) for _index, side in visible}
        styles = {side.style for _index, side in visible}
        if len(visible) == 4 and len(widths) == 1 and len(colors) == 1:
            side = visible[0][1]
            xmlutil.set_line(shape, side.width, side.color, DASH_MAP.get(side.style, "solid"))
            return
        xmlutil.no_line(shape)
        x, y, width, height = box.rect
        for index, side in visible:
            if index == 0:
                bar = (x, y, width, side.width)
            elif index == 1:
                bar = (x + width - side.width, y, side.width, height)
            elif index == 2:
                bar = (x, y + height - side.width, width, side.width)
            else:
                bar = (x, y, side.width, height)
            if bar[2] <= 0 or bar[3] <= 0:
                continue
            line = self._rect(*bar, name=_name(box) + f"-border{index}")
            xmlutil.no_line(line)
            line.fill.solid()
            line.fill.fore_color.rgb = _rgb(side.color or (200, 200, 200, 1))
            alpha = util.alpha_of(side.color or (200, 200, 200, 1))
            if alpha < 0.999:
                _set_fill_alpha(line, alpha)
            _strip_text(line)

    # -- text ------------------------------------------------------------
    def _text(self, box):
        if not box.lines:
            return
        style = box.style
        x, y, width, height = box.rect
        # Every laid-out line is written as its own paragraph, so PowerPoint must
        # not re-wrap it: a metric difference between PIL/FreeType and the office
        # shaper would insert an extra line and push the block out of its box.
        # ``word_wrap = False`` keeps the authored line breaks exactly.
        widest = self._widest_line(box)
        if widest > 0:
            width = max(width, widest + 8.0)
        tracking = abs(style.letter_spacing or 0.0) * 2.0
        slack = max(3.0, width * 0.02) + tracking
        align = style.text_align
        if align == "center":
            x -= slack / 2.0
        elif align == "right":
            x -= slack
        width += slack
        textbox = self.slide.shapes.add_textbox(
            Emu(util.pt2emu(x)),
            Emu(util.pt2emu(y)),
            Emu(max(1, util.pt2emu(width))),
            Emu(max(1, util.pt2emu(height * 1.18 + 4.0))),
        )
        textbox.name = _name(box)
        self.count += 1
        frame = textbox.text_frame
        # Wrapping off: the line breaks below are the ones the layout engine
        # computed, and they are what the author designed.
        frame.word_wrap = False
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_left = 0
        frame.margin_right = 0
        frame.margin_top = 0
        frame.margin_bottom = 0
        frame.auto_size = MSO_AUTO_SIZE.NONE
        _no_autofit(frame)
        bullet = box.extra.get("bullet") or ""
        autonum = box.extra.get("autonum") or ""
        for index, line in enumerate(box.lines):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.alignment = ALIGN_MAP.get(style.text_align, PP_ALIGN.LEFT)
            paragraph.line_spacing = Emu(util.pt2emu(line.height or style.font_size * style.line_height))
            paragraph.space_before = Emu(0)
            paragraph.space_after = Emu(0)
            _clear_bullet(paragraph)
            if index == 0:
                if autonum:
                    _autonum(paragraph, autonum, style, box.extra.get("bullet_start") or 1)
                elif bullet:
                    _bullet(paragraph, bullet, style)
            if not line.runs:
                continue
            for text, run_style, _run_width in line.runs:
                run = paragraph.add_run()
                run.text = text
                xmlutil.set_run_font(
                    run,
                    run_style.font_family,
                    run_style.font_size,
                    bold=run_style.bold,
                    italic=run_style.italic,
                    color=util.with_alpha(run_style.color, util.alpha_of(run_style.color) * run_style.opacity),
                    letter_spacing=run_style.letter_spacing,
                    underline="underline" in (run_style.text_decoration or ""),
                    strike="line-through" in (run_style.text_decoration or ""),
                    baseline=run_style.baseline_shift,
                )
                if run_style.text_shadow is not None:
                    xmlutil.set_run_shadow(run, run_style.text_shadow)
                if run_style.font_variant_numeric in ("tabular-nums", "lining-nums", "slashed-zero"):
                    run._r.get_or_add_rPr().set("numFmt", "tab")
        self._rotate_textbox(textbox, style)

    def _rotate_textbox(self, textbox, style):
        angle = style.transform.get("rotate") or 0.0
        if abs(angle) < 0.01:
            return
        textbox.rotation = (-angle) % 360.0

    @staticmethod
    def _widest_line(box):
        """Widest measured line plus the bullet indent, in points."""
        widest = max((line.width for line in (box.lines or [])), default=0.0)
        if box.extra.get("bullet"):
            widest += max(6.0, box.style.font_size * 0.85)
        return widest

    # -- pictures ---------------------------------------------------------
    def _picture(self, box):
        path = self._asset(box.image_src)
        if not path:
            self.issues.append(f"missing image: {box.image_src}")
            return
        x, y, width, height = box.rect
        try:
            picture = self.slide.shapes.add_picture(
                path,
                Emu(util.pt2emu(x)),
                Emu(util.pt2emu(y)),
                Emu(max(1, util.pt2emu(width))),
                Emu(max(1, util.pt2emu(height))),
            )
        except Exception as error:
            self.issues.append(f"image failed ({box.image_src}): {error}")
            return
        picture.name = _name(box)
        self.count += 1
        self._crop(picture, box, path)
        radius = _radius(box.style)
        alpha = box.style.opacity
        if radius and radius > 0.5:
            _round_picture(picture, radius, width, height)
        if alpha < 0.999:
            _alpha_picture(picture, alpha)
        if box.style.shadows:
            try:
                xmlutil.set_shadow(picture, box.style.shadows)
            except Exception:
                pass
        self._apply_rotation(picture, box.style)

    def _crop(self, picture, box, path):
        fit = (box.extra.get("fit") or "cover").lower()
        intrinsic = box.extra.get("intrinsic") or _image_size(path)
        if not intrinsic or fit == "fill" or not all(intrinsic):
            return
        image_ratio = intrinsic[0] / intrinsic[1]
        width, height = box.rect[2], box.rect[3]
        if not width or not height:
            return
        box_ratio = width / height
        if fit == "cover":
            if image_ratio > box_ratio:
                excess = 1.0 - box_ratio / image_ratio
                picture.crop_left = excess / 2.0
                picture.crop_right = excess / 2.0
            else:
                excess = 1.0 - image_ratio / box_ratio
                picture.crop_top = excess / 2.0
                picture.crop_bottom = excess / 2.0
        elif fit == "contain":
            if image_ratio > box_ratio:
                new_height = width / image_ratio
                picture.top = Emu(util.pt2emu(box.rect[1] + (height - new_height) / 2.0))
                picture.height = Emu(util.pt2emu(new_height))
            else:
                new_width = height * image_ratio
                picture.left = Emu(util.pt2emu(box.rect[0] + (width - new_width) / 2.0))
                picture.width = Emu(util.pt2emu(new_width))

    def _icon(self, box):
        """Vector icons become native shapes; anything else falls back to PNG."""
        if box.node is not None:
            try:
                raw = etree.tostring(box.node.element, encoding="unicode", with_tail=False)
                document = svgshape.parse(raw)
                created = svgshape.emit(self.slide, document, box, shape_name=_name(box) or "icon")
                if created:
                    self.count += created
                    self._apply_rotation_group(box, created)
                    return
            except (svgshape.Unsupported, etree.XMLSyntaxError, ValueError):
                pass
            except Exception as error:  # pragma: no cover - defensive
                self.issues.append(f"svg geometry failed: {error}")
        path = self._icon_png(box)
        if not path:
            self.issues.append("icon could not be rasterised")
            return
        x, y, width, height = box.rect
        try:
            picture = self.slide.shapes.add_picture(
                path,
                Emu(util.pt2emu(x)),
                Emu(util.pt2emu(y)),
                Emu(max(1, util.pt2emu(width))),
                Emu(max(1, util.pt2emu(height))),
            )
        except Exception as error:
            self.issues.append(f"icon failed: {error}")
            return
        picture.name = _name(box) or "icon"
        self.count += 1
        self._apply_rotation(picture, box.style)

    def _apply_rotation_group(self, box, count):
        angle = box.style.transform.get("rotate") or 0.0
        if abs(angle) < 0.01:
            return
        for shape in self.slide.shapes[-count:]:
            shape.rotation = (-angle) % 360.0

    def _icon_png(self, box):
        if not self.cache_dir or box.node is None:
            return None
        os.makedirs(self.cache_dir, exist_ok=True)
        raw = etree.tostring(box.node.element, encoding="unicode", with_tail=False)
        import hashlib

        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        output = os.path.join(self.cache_dir, f"icon-{digest}.png")
        return svgicon.svg_to_png(raw, output, color=box.style.color, scale=6)

    # -- tables -----------------------------------------------------------
    def _table(self, box):
        data = box.table
        if not data:
            return
        widths = data["column_widths"]
        heights = data["row_heights"]
        rows = len(data["rows"])
        columns = len(widths)
        if not rows or not columns:
            return
        x, y = box.rect[0], box.rect[1]
        shape = self.slide.shapes.add_table(
            rows,
            columns,
            Emu(util.pt2emu(x)),
            Emu(util.pt2emu(y)),
            Emu(util.pt2emu(sum(widths))),
            Emu(util.pt2emu(sum(heights))),
        )
        shape.name = _name(box) or "table"
        self.count += 1
        table = shape.table
        _plain_table_style(table)
        for index, width in enumerate(widths):
            table.columns[index].width = Emu(util.pt2emu(width))
        for index, height in enumerate(heights):
            table.rows[index].height = Emu(util.pt2emu(height))
        for row_index, cells in enumerate(data["rows"]):
            column = 0
            for cell_index, cell in enumerate(cells):
                span = data["spans"][row_index][cell_index]
                if column >= columns:
                    break
                target = table.cell(row_index, column)
                style = data["styles"][row_index][cell_index]
                if span > 1 and column + span <= columns:
                    try:
                        target.merge(table.cell(row_index, column + span - 1))
                    except Exception:
                        pass
                self._cell(target, cell, style)
                column += span

    def _cell(self, target, cell, style):
        frame = target.text_frame
        frame.word_wrap = True
        frame.margin_left = Emu(util.pt2emu(style.padding[3] + 3))
        frame.margin_right = Emu(util.pt2emu(style.padding[1] + 3))
        frame.margin_top = Emu(util.pt2emu(style.padding[0] + 2))
        frame.margin_bottom = Emu(util.pt2emu(style.padding[2] + 2))
        frame.vertical_anchor = {"middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}.get(
            style.vertical_align, MSO_ANCHOR.MIDDLE
        )
        if style.background is not None and style.background.color is not None:
            target.fill.solid()
            target.fill.fore_color.rgb = _rgb(style.background.color)
        else:
            target.fill.background()
        for side_index, side_name in enumerate(("left", "top", "right", "bottom")):
            border = None
            if style.border:
                border = style.border[[3, 0, 1, 2][side_index]]
            if border and border.visible:
                _cell_border(target, side_name, border.width, border.color or (209, 213, 219, 1))
        paragraph = frame.paragraphs[0]
        paragraph.alignment = ALIGN_MAP.get(style.text_align, PP_ALIGN.LEFT)
        paragraph.space_before = Emu(0)
        paragraph.space_after = Emu(0)
        runs = cell.child_nodes
        if not runs:
            return
        for part in runs:
            if part.tag_name:
                text = part.text()
                run_style = style
            else:
                text = (part.text or "").strip()
                run_style = style
            if not text:
                continue
            run = paragraph.add_run()
            run.text = text
            xmlutil.set_run_font(
                run, run_style.font_family, run_style.font_size,
                bold=run_style.bold, italic=run_style.italic, color=run_style.color,
            )

    # -- helpers ----------------------------------------------------------
    def _asset(self, src):
        if not src or src.startswith(("http://", "https://", "data:")):
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


# --------------------------------------------------------------------------
def _rgb(color):
    return RGBColor(int(color[0]), int(color[1]), int(color[2]))


def _detach_theme_style(shape):
    """Remove ``<p:style>`` so the theme's accent fill/shadow cannot leak in.

    ``add_shape`` writes a style reference (lnRef/fillRef/effectRef). Left in
    place, PowerPoint and LibreOffice may draw theme accents and preset shadows
    over the colours the deck actually specified.
    """
    element = shape._element
    for style in element.findall(qn("p:style")):
        element.remove(style)


def _corners_differ(corners):
    """True when the radius cannot be expressed by one roundRect adjustment."""
    if not corners or not any(rx or ry for rx, ry in corners):
        return False
    first = corners[0]
    if any(abs(rx - first[0]) > 0.01 or abs(ry - first[1]) > 0.01 for rx, ry in corners[1:]):
        return True
    # Elliptical (rx != ry) corners need a custom path as well.
    return abs(first[0] - first[1]) > 0.01


def _radius(style):
    if not style.radius:
        return 0.0
    return max([max(rx, ry) for rx, ry in style.radius if rx or ry] or [0.0])


def _name(box):
    node = box.node
    if node is None:
        return box.kind
    tag = node.tag_name or box.kind
    suffix = ""
    if node.class_set:
        suffix = "-" + "-".join(sorted(node.class_set)[:2])
    label = ""
    if box.kind == "text":
        label = (box.text or "")[:18].strip()
    return f"{tag}{suffix}{(': ' + label) if label else ''}"


def _strip_text(shape):
    frame = shape.text_frame
    body = frame._txBody
    paragraphs = body.findall(qn("a:p"))
    for paragraph in paragraphs[1:]:
        body.remove(paragraph)
    if paragraphs:
        for run in paragraphs[0].findall(qn("a:r")):
            paragraphs[0].remove(run)


def _no_autofit(frame):
    body_pr = frame._txBody.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    for child in list(body_pr):
        if child.tag in (qn("a:normAutofit"), qn("a:spAutoFit"), qn("a:noAutofit")):
            body_pr.remove(child)
    etree.SubElement(body_pr, qn("a:noAutofit"))


def _clear_bullet(paragraph):
    p_pr = paragraph._p.get_or_add_pPr()
    for tag in ("a:buChar", "a:buAutoNum", "a:buNone", "a:buBlip", "a:buClr", "a:buSzPct", "a:buFont"):
        for element in p_pr.findall(qn(tag)):
            p_pr.remove(element)
    etree.SubElement(p_pr, qn("a:buNone"))


def _bullet(paragraph, char, style):
    """Write bullet properties in the schema-mandated order.

    ``CT_TextParagraphProperties`` requires buClr -> buSzPct -> buFont -> buChar;
    writing buChar first makes PowerPoint and LibreOffice render stray fills.
    """
    p_pr = paragraph._p.get_or_add_pPr()
    for element in p_pr.findall(qn("a:buNone")):
        p_pr.remove(element)
    indent = max(6.0, style.font_size * 0.85)
    p_pr.set("marL", str(util.pt2emu(indent)))
    p_pr.set("indent", str(-util.pt2emu(indent)))
    color = etree.SubElement(p_pr, qn("a:buClr"))
    etree.SubElement(color, qn("a:srgbClr"), val=util.to_dml(style.color))
    size = etree.SubElement(p_pr, qn("a:buSzPct"))
    size.set("val", "100000")
    font = etree.SubElement(p_pr, qn("a:buFont"))
    font.set("typeface", "Arial")
    bullet = etree.SubElement(p_pr, qn("a:buChar"))
    bullet.set("char", char)


def _autonum(paragraph, scheme, style, start=1):
    """Native ordered numbering (``a:buAutoNum``), so items renumber themselves."""
    p_pr = paragraph._p.get_or_add_pPr()
    for element in p_pr.findall(qn("a:buNone")):
        p_pr.remove(element)
    indent = max(6.0, style.font_size * 0.85)
    p_pr.set("marL", str(util.pt2emu(indent)))
    p_pr.set("indent", str(-util.pt2emu(indent)))
    color = etree.SubElement(p_pr, qn("a:buClr"))
    etree.SubElement(color, qn("a:srgbClr"), val=util.to_dml(style.color))
    size = etree.SubElement(p_pr, qn("a:buSzPct"))
    size.set("val", "100000")
    font = etree.SubElement(p_pr, qn("a:buFont"))
    font.set("typeface", "Arial")
    auto = etree.SubElement(p_pr, qn("a:buAutoNum"))
    auto.set("type", scheme)
    if start and start > 1:
        auto.set("startAt", str(int(start)))


def _set_fill_alpha(shape, alpha):
    sp_pr = shape._element.spPr
    if not sp_pr.findall(qn("a:solidFill")):
        return
    for fill in sp_pr.findall(qn("a:solidFill")):
        for srgb in fill.findall(qn("a:srgbClr")):
            existing = srgb.find(qn("a:alpha"))
            value = str(int(round(alpha * 100000)))
            if existing is None:
                etree.SubElement(srgb, qn("a:alpha"), val=value)
            else:
                existing.set("val", value)


def _alpha_picture(picture, opacity):
    blip = picture._element.blipFill.find(qn("a:blip"))
    if blip is None:
        return
    for element in blip.findall(qn("a:alphaModFix")):
        blip.remove(element)
    etree.SubElement(blip, qn("a:alphaModFix"), amt=str(int(round(opacity * 100000))))


def _round_picture(picture, radius, width, height):
    prst = picture._element.spPr.find(qn("a:prstGeom"))
    if prst is None:
        return
    prst.set("prst", "roundRect")
    av = prst.find(qn("a:avLst"))
    if av is None:
        av = etree.SubElement(prst, qn("a:avLst"))
    for child in list(av):
        av.remove(child)
    ratio = min(0.5, radius / max(1.0, min(width, height)))
    etree.SubElement(av, qn("a:gd"), name="adj", fmla=f"val {int(ratio * 100000)}")


def _plain_table_style(table):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("a:tblPr"))
    if tbl_pr is None:
        return
    for attribute in ("firstRow", "bandRow", "firstCol", "lastRow", "lastCol", "bandCol"):
        tbl_pr.set(attribute, "0")
    for style_id in tbl_pr.findall(qn("a:tableStyleId")):
        tbl_pr.remove(style_id)


def _cell_border(cell, side, width_pt, color):
    tc = cell._tc
    tc_pr = tc.find(qn("a:tcPr"))
    if tc_pr is None:
        tc_pr = etree.SubElement(tc, qn("a:tcPr"))
    tag = qn(f"a:ln{side.capitalize()}")
    for existing in tc_pr.findall(tag):
        tc_pr.remove(existing)
    line = etree.Element(tag, w=str(max(1, util.pt2emu(width_pt))), cap="flat", cmpd="sng", algn="ctr")
    fill = etree.SubElement(line, qn("a:solidFill"))
    clr = etree.SubElement(fill, qn("a:srgbClr"), val=util.to_dml(color))
    alpha = util.alpha_of(color)
    if alpha < 0.999:
        etree.SubElement(clr, qn("a:alpha"), val=str(int(round(alpha * 100000))))
    etree.SubElement(line, qn("a:prstDash"), val="solid")
    tc_pr.insert(0, line)


def _image_size(path):
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


# --------------------------------------------------------------------------
def build_presentation(width_pt, height_pt, font_family="Inter", theme_colors=None):
    presentation = Presentation()
    presentation.slide_width = Emu(util.pt2emu(width_pt))
    presentation.slide_height = Emu(util.pt2emu(height_pt))
    _theme(presentation, font_family, theme_colors)
    return presentation


def _theme(presentation, font_family, theme_colors=None):
    try:
        master = presentation.slide_masters[0]
    except IndexError:  # pragma: no cover
        return
    theme_part = None
    for rel in master.part.rels.values():
        if "theme" in rel.reltype:
            theme_part = rel.target_part
            break
    if theme_part is None:
        return
    try:
        root = etree.fromstring(theme_part.blob)
    except etree.XMLSyntaxError:  # pragma: no cover
        return
    latin = (font_family or "Inter").split(",")[0].strip().strip("'\"")
    east_asian = xmlutil._east_asian_family(latin)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    for scheme in ("majorFont", "minorFont"):
        element = root.find(f".//a:{scheme}", ns)
        if element is None:
            continue
        for tag, value in (("latin", latin), ("ea", east_asian), ("cs", latin)):
            child = element.find(f"a:{tag}", ns)
            if child is None:
                child = etree.SubElement(element, qn(f"a:{tag}"))
            child.set("typeface", value)
    if theme_colors:
        scheme = root.find(".//a:clrScheme", ns)
        if scheme is not None:
            _colors(scheme, theme_colors, ns)
    try:
        theme_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    except AttributeError:  # pragma: no cover - older python-pptx
        pass


def _colors(scheme, palette, ns):
    mapping = {
        "dk1": palette.get("text") or palette.get("ink"),
        "lt1": palette.get("background") or palette.get("paper"),
        "dk2": palette.get("text_muted") or palette.get("muted"),
        "lt2": palette.get("surface") or palette.get("background_alt"),
        "accent1": palette.get("primary"),
        "accent2": palette.get("secondary"),
        "accent3": palette.get("accent_3"),
        "accent4": palette.get("accent_4"),
        "accent5": palette.get("accent_5"),
        "accent6": palette.get("accent_6"),
        "hlink": palette.get("accent_6") or palette.get("secondary"),
        "folHlink": palette.get("accent_5") or palette.get("primary"),
    }
    for slot, value in mapping.items():
        if not value:
            continue
        element = scheme.find(f"a:{slot}", ns)
        if element is None:
            continue
        for child in list(element):
            element.remove(child)
        parsed = util.parse_color(value) or (0, 0, 0, 1)
        etree.SubElement(element, qn("a:srgbClr"), val=util.to_dml(parsed))
