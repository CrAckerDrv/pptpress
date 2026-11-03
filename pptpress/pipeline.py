"""The build pipeline: HTML -> DOM -> CSS -> layout -> PPTX (+ preview)."""

from __future__ import annotations

import os
import time

from . import css, dom, layout, metrics, slides, writer

__all__ = ["build", "preview", "layout_document", "BuildResult", "PreviewResult"]


class BuildResult:
    def __init__(self, output, slides, issues, timings):
        self.output = output
        self.slides = slides
        self.issues = issues
        self.timings = timings

    @property
    def ok(self):
        return bool(self.output) and os.path.exists(self.output)

    @property
    def objects(self):
        return sum(1 for slide in self.slides for _box in slide.walk())

    def summary(self):
        total = sum(self.timings.values())
        lines = [
            f"PPT Press build -> {self.output}",
            f"  slides : {len(self.slides)}",
            f"  objects: {self.objects}",
            f"  time   : {total * 1000:.0f} ms "
            + " ".join(f"{name}={value * 1000:.0f}ms" for name, value in self.timings.items()),
        ]
        if self.issues:
            lines.append(f"  issues : {len(self.issues)}")
            for issue in self.issues[:20]:
                lines.append(f"    - {issue}")
        return "\n".join(lines)

    def __repr__(self):
        return f"<BuildResult slides={len(self.slides)} ok={self.ok} issues={len(self.issues)}>"


class PreviewResult:
    def __init__(self, html_path, images, issues, timings):
        self.html_path = html_path
        self.images = images
        self.issues = issues
        self.timings = timings

    @property
    def ok(self):
        return bool(self.html_path) and os.path.exists(self.html_path)

    def __repr__(self):
        return f"<PreviewResult slides={len(self.images)} html={self.html_path}>"


def layout_document(html_path, theme=None):
    """Parse + style + lay out one HTML deck; returns (document, slides, engine)."""
    started = time.perf_counter()
    document = dom.Document(html_path)
    if theme:
        document.style_texts.insert(0, theme.to_css())
    parse_time = time.perf_counter() - started

    started = time.perf_counter()
    font_book = metrics.FontBook()
    sheet = css.parse_stylesheets(document)
    resolver = css.Resolver([sheet], fonts={"resolve": font_book.powerpoint_family})
    variables = {}
    for rule in sheet.rules:
        for _combinator, compound in rule.selector.parts:
            for name, _argument in compound.pseudos:
                if name != "root":
                    continue
                for declaration in rule.declarations:
                    if declaration.prop.startswith("--"):
                        variables[declaration.prop[2:]] = declaration.value
    resolver.variables.update(variables)
    css_time = time.perf_counter() - started

    started = time.perf_counter()
    width_pt, height_pt = slides.slide_size(document)
    base_dir = os.path.dirname(os.path.abspath(html_path))
    engine = layout.LayoutEngine(resolver, font_book, width_pt, height_pt, base_dir=base_dir)
    slide_boxes = engine.layout_document(document)
    layout_time = time.perf_counter() - started
    timings = {"parse": parse_time, "css": css_time, "layout": layout_time}
    return document, slide_boxes, engine, (width_pt, height_pt), timings


def build(html_path, out_pptx, theme=None, cache_dir=None):
    document, slide_boxes, engine, (width_pt, height_pt), timings = layout_document(html_path, theme)

    started = time.perf_counter()
    presentation = writer.build_presentation(
        width_pt,
        height_pt,
        font_family=_font_of(document, slide_boxes),
        theme_colors=theme.colors if theme else None,
    )
    cache = cache_dir or _default_cache_dir(out_pptx)
    base_dir = os.path.dirname(os.path.abspath(html_path))
    issues = list(engine.warnings)
    for slide_box in slide_boxes:
        slide_writer = writer.SlideWriter(presentation, slide_box, base_dir=base_dir, cache_dir=cache)
        slide_writer.write()
        issues.extend(f"slide {slide_box.index + 1}: {item}" for item in slide_writer.issues)
    directory = os.path.dirname(os.path.abspath(out_pptx))
    if directory:
        os.makedirs(directory, exist_ok=True)
    presentation.save(out_pptx)
    timings["pptx"] = time.perf_counter() - started
    return BuildResult(out_pptx, slide_boxes, issues, timings)


def preview(html_path, out_dir, theme=None):
    from . import preview as preview_module

    document, slide_boxes, engine, _size, timings = layout_document(html_path, theme)
    started = time.perf_counter()
    base_dir = os.path.dirname(os.path.abspath(html_path))
    images, html_out, issues = preview_module.write_previews(slide_boxes, out_dir, base_dir)
    timings["preview"] = time.perf_counter() - started
    flat = list(engine.warnings)
    for number, slide_issues in issues.items():
        flat.extend(f"slide {number}: {item}" for item in slide_issues)
    return PreviewResult(html_out, images, flat, timings)


def _default_cache_dir(out_pptx):
    return os.path.splitext(os.path.abspath(out_pptx))[0] + ".assets"


def _font_of(document, slide_boxes):
    for slide_box in slide_boxes:
        if slide_box.style is not None and slide_box.style.font_family:
            return slide_box.style.font_family
    return "Inter, sans-serif"

