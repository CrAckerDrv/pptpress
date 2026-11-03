"""Preview renderer: a faithful SVG of the computed layout for each slide.

The preview is a *debug* aid — it shows exactly the geometry the PPTX writer
receives, so spacing problems are visible before PowerPoint opens.
"""

from __future__ import annotations

import html
import math
import os

from . import util

_FONT_STACK = "Inter, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', 'Source Han Sans SC', Arial, sans-serif"


class SvgWriter:
    def __init__(self, slide, base_dir="", fonts=None):
        self.slide = slide
        self.base_dir = base_dir or ""
        self.fonts = fonts or {}
        self.parts = []
        self.defs = []
        self.clip_id = 0
        self.issues = []

    def render(self):
        width, height = self.slide.width, self.slide.height
        self.parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width:.2f}pt" height="{height:.2f}pt" viewBox="0 0 {width:.2f} {height:.2f}">'
        )
        self.defs.append('<defs>')
        self.parts.append("<defs></defs>")
        background = self.slide.background
        if background is not None:
            self.parts.append(f'<rect x="0" y="0" width="{width:.2f}" height="{height:.2f}" {self._fill(background, width, height)}/>')
        for box in self.slide.children:
            self._emit(box, 0)
        self.parts.append("</svg>")
        body = "".join(self.parts).replace("<defs></defs>", "".join(self.defs) + "</defs>")
        return body

    # -- helpers ---------------------------------------------------------
    def _fill(self, background, width, height):
        if background is None:
            return 'fill="#FFFFFF"'
        if background.gradients:
            gradient = background.gradients[0]
            gradient.width = width
            gradient.height = height
            return f'fill="url(#{self._gradient_def(gradient)})"'
        if background.image:
            href = self._href(background.image)
            if href:
                return f'fill="url(#{self._image_pattern(href, width, height)})"'
        if background.color is not None:
            return f'fill="{util.to_css(background.color)}"'
        return 'fill="none"'

    def _gradient_def(self, gradient):
        ident = f"lg{len(self.defs)}"
        radians = (gradient.angle - 90.0) * math.pi / 180.0
        cx, cy = gradient.width / 2, gradient.height / 2
        length = (abs(gradient.width * math.cos(radians)) + abs(gradient.height * math.sin(radians))) / 2
        x1 = cx - length * math.cos(radians)
        y1 = cy - length * math.sin(radians)
        x2 = cx + length * math.cos(radians)
        y2 = cy + length * math.sin(radians)
        stops = "".join(
            f'<stop offset="{stop.position * 100:.2f}%" stop-color="{util.to_css(stop.color)}"/>'
            for stop in gradient.stops
        )
        self.defs.append(
            f'<linearGradient id="{ident}" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'gradientUnits="userSpaceOnUse">{stops}</linearGradient>'
        )
        return ident

    def _image_pattern(self, href, width, height):
        ident = f"img{len(self.defs)}"
        self.defs.append(
            f'<pattern id="{ident}" patternUnits="userSpaceOnUse" width="{width:.2f}" height="{height:.2f}">'
            f'<image href="{href}" xlink:href="{href}" width="{width:.2f}" height="{height:.2f}" '
            f'preserveAspectRatio="xMidYMid slice"/></pattern>'
        )
        return ident

    def _href(self, src):
        if not src or src.startswith(("http://", "https://")):
            return None
        path = src
        if not os.path.isabs(path):
            for candidate in (os.path.join(self.base_dir, src), os.path.join(self.base_dir, "assets", src)):
                if os.path.exists(candidate):
                    path = candidate
                    break
        if not os.path.exists(path):
            self.issues.append(f"missing image: {src}")
            return None
        return _as_data_uri(path)

    def _clip(self, x, y, width, height, radius=None):
        self.clip_id += 1
        ident = f"clip{self.clip_id}"
        if radius:
            rx, _ry = radius[0], radius[1]
            self.defs.append(
                f'<clipPath id="{ident}"><rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" '
                f'height="{height:.2f}" rx="{rx:.2f}"/></clipPath>'
            )
        else:
            self.defs.append(
                f'<clipPath id="{ident}"><rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" '
                f'height="{height:.2f}"/></clipPath>'
            )
        return ident

    def _radius_attr(self, style):
        if not style.radius:
            return ""
        raw = style.radius
        radius = min(max(raw[0], raw[1]), max(raw[0], raw[3]))
        return f' rx="{radius:.2f}"'

    def _emit(self, box, depth):
        if box.width <= 0 or box.height <= 0:
            return
        if box.kind == "text":
            self._emit_text(box)
        elif box.kind == "image":
            self._emit_image(box)
        elif box.kind == "svg":
            self._emit_svg_icon(box)
        elif box.kind == "table":
            self._emit_table(box)
        else:
            self._emit_block(box, depth)

    def _shape_attrs(self, box):
        style = box.style
        x, y, w, h = box.rect
        opacity = ""
        if style.opacity < 0.999:
            opacity = f' opacity="{style.opacity:.3f}"'
        return f'x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"{self._radius_attr(style)}{opacity}'

    def _emit_block(self, box, depth):
        style = box.style
        x, y, w, h = box.rect
        if style.background is not None:
            self.parts.append(f'<rect {self._shape_attrs(box)} {self._fill(style.background, w, h)}/>')
        if style.border:
            for side, (bx1, by1, bx2, by2) in _border_lines(box).items():
                border = style.border[side]
                if border and border.visible:
                    dash = ' stroke-dasharray="4 3"' if border.style == "dashed" else ""
                    self.parts.append(
                        f'<line x1="{bx1:.2f}" y1="{by1:.2f}" x2="{bx2:.2f}" y2="{by2:.2f}" '
                        f'stroke="{util.to_css(border.color or (200,200,200,1))}" '
                        f'stroke-width="{border.width:.2f}"{dash}/>'
                    )
        for child in box.children:
            self._emit(child, depth + 1)

    def _emit_text(self, box):
        style = box.style
        align = style.text_align
        x, y, w, h = box.rect
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(align, "start")
        tx = x if align == "left" else (x + w / 2 if align == "center" else x + w)
        cursor = y
        for line in box.lines or []:
            baseline = cursor + line.height * 0.8
            if not line.runs:
                cursor += line.height
                continue
            span_x = tx
            total = line.width
            if align == "center":
                span_x = x + max(0.0, (w - total) / 2.0)
            elif align == "right":
                span_x = x + max(0.0, w - total)
            offsets = []
            cursor_x = span_x
            for text, run_style, run_width in line.runs:
                offsets.append((text, run_style, run_width, cursor_x))
                cursor_x += run_width
            for text, run_style, run_width, cx in offsets:
                if not text.strip():
                    continue
                decoration = ""
                if "underline" in run_style.text_decoration:
                    decoration = f' text-decoration="underline"'
                weight = "700" if run_style.bold else "400"
                italic = ' font-style="italic"' if run_style.italic else ""
                self.parts.append(
                    f'<text x="{cx:.2f}" y="{baseline:.2f}" font-family="{_FONT_STACK}" '
                    f'font-size="{run_style.font_size:.2f}" font-weight="{weight}"{italic} '
                    f'fill="{util.to_css(run_style.color)}" xml:space="preserve"{decoration}>'
                    f"{html.escape(text)}</text>"
                )
            cursor += line.height
        if box.extra.get("overflow"):
            self.issues.append(f"text overflow at ({x:.0f},{y:.0f})")

    def _emit_image(self, box):
        x, y, w, h = box.rect
        href = self._href(box.image_src)
        if not href:
            self.parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#E5E7EB"/>'
            )
            return
        fit = box.extra.get("fit", "fill")
        preserve = "none" if fit == "fill" else "xMidYMid slice" if fit == "cover" else "xMidYMid meet"
        clip = self._clip(x, y, w, h, box.style.radius)
        self.parts.append(
            f'<image x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" href="{href}" '
            f'xlink:href="{href}" preserveAspectRatio="{preserve}" clip-path="url(#{clip})"/>'
        )

    def _emit_svg_icon(self, box):
        node = box.svg_node
        if node is None:
            return
        x, y, w, h = box.rect
        view = box.extra.get("viewbox") or [0, 0, 24, 24]
        inner = "".join(html.escape("") for _ in ())
        children = []
        for child in node.element_children():
            children.append(_serialize_svg_child(child.element))
        color = util.to_css(box.style.color)
        self.parts.append(
            f'<svg x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'viewBox="{view[0]} {view[1]} {view[2]} {view[3]}" fill="{color}" '
            f'stroke="{color}" preserveAspectRatio="xMidYMid meet">{"".join(children)}</svg>'
        )

    def _emit_table(self, box):
        table = box.table
        if not table:
            return
        x, y, w, h = box.rect
        widths = table["column_widths"]
        heights = table["row_heights"]
        cursor_y = y
        for row_index, row in enumerate(table["rows"]):
            cursor_x = x
            row_height = heights[row_index]
            col = 0
            for cell in row:
                span = 1
                try:
                    span = max(1, int(cell.attr("colspan") or 1))
                except ValueError:
                    span = 1
                cell_width = sum(widths[col:col + span]) if col + span <= len(widths) else widths[-1]
                cell_style = table["styles"][row_index][min(col, len(table["styles"][row_index]) - 1)]
                fill_attr = 'fill="#F3F4F6"' if cell.tag_name == "th" else 'fill="none"'
                if cell_style.background is not None:
                    fill_attr = self._fill(cell_style.background, cell_width, row_height)
                self.parts.append(
                    f'<rect x="{cursor_x:.2f}" y="{cursor_y:.2f}" width="{cell_width:.2f}" '
                    f'height="{row_height:.2f}" {fill_attr} stroke="#D1D5DB" stroke-width="0.5"/>'
                )
                runs = []
                # Lazy import to avoid a cycle at module load time.
                for text, run_style in _table_runs(cell, cell_style):
                    runs.append((text, run_style))
                line_height = max((s.font_size * s.line_height for _t, s in runs), default=cell_style.font_size * 1.2)
                text_y = cursor_y + (row_height - line_height * max(1, len(runs))) / 2 + line_height * 0.8
                merged = _merge_text_runs(runs)
                for text, run_style in merged:
                    if not text.strip():
                        continue
                    weight = "700" if run_style.bold else "400"
                    self.parts.append(
                        f'<text x="{cursor_x + 4:.2f}" y="{text_y:.2f}" font-family="{_FONT_STACK}" '
                        f'font-size="{run_style.font_size:.2f}" font-weight="{weight}" '
                        f'fill="{util.to_css(run_style.color)}" xml:space="preserve">{html.escape(text)}</text>'
                    )
                    break
                cursor_x += cell_width
                col += span
            cursor_y += row_height


def _merge_text_runs(runs):
    merged = []
    for text, style in runs:
        if merged and merged[-1][1] is style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


def _table_runs(cell, style):
    runs = []
    for child in cell.child_nodes:
        if child.tag_name:
            text = child.text()
        else:
            text = child.text
        if not text:
            continue
        runs.append((str(text), style))
    return runs


def _border_lines(box):
    x, y, w, h = box.rect
    style = box.style
    border = style.border
    top_w = border[0].width if border and border[0] and border[0].visible else 0.0
    right_w = border[1].width if border and border[1] and border[1].visible else 0.0
    bottom_w = border[2].width if border and border[2] and border[2].visible else 0.0
    left_w = border[3].width if border and border[3] and border[3].visible else 0.0
    return {
        0: (x, y + top_w / 2, x + w, y + top_w / 2),
        1: (x + w - right_w / 2, y, x + w - right_w / 2, y + h),
        2: (x, y + h - bottom_w / 2, x + w, y + h - bottom_w / 2),
        3: (x + left_w / 2, y, x + left_w / 2, y + h),
    }


def _serialize_svg_child(element):
    from lxml import etree

    raw = etree.tostring(element, encoding="unicode")
    raw = raw.replace('ns0:', "").replace(":ns0", "")
    return raw


def _as_data_uri(path):
    import base64

    try:
        with open(path, "rb") as handle:
            payload = base64.b64encode(handle.read()).decode("ascii")
    except OSError:
        return None
    extension = os.path.splitext(path)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(extension, "image/png")
    return f"data:{mime};base64,{payload}"


def render_slide(slide, base_dir=""):
    writer = SvgWriter(slide, base_dir)
    return writer.render(), writer.issues


def render_html(slides, base_dir="", title="Deckpress preview"):
    """A scrollable HTML page showing every slide as SVG."""
    from .preview_html import build_html_page

    return build_html_page(slides, base_dir, title)


def write_previews(slides, out_dir, base_dir="", title="Deckpress preview"):
    os.makedirs(out_dir, exist_ok=True)
    images = []
    issues = {}
    for slide in slides:
        svg, slide_issues = render_slide(slide, base_dir)
        path = os.path.join(out_dir, f"slide-{slide.index + 1:02d}.svg")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        images.append(path)
        if slide_issues:
            issues[slide.index + 1] = slide_issues
    html_path = os.path.join(out_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(render_html(slides, base_dir, title))
    return images, html_path, issues
