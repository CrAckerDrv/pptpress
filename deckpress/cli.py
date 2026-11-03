"""Command line interface.

    python -m deckpress build deck.html -o deck.pptx
    python -m deckpress preview deck.html -o preview/
    python -m deckpress check deck.html
    python -m deckpress themes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import env, themes, util
from .pipeline import build, preview


def _theme(value):
    if not value:
        return None
    return themes.load(value)


def cmd_build(args):
    started = time.perf_counter()
    result = build(args.html, args.output, theme=_theme(args.theme), cache_dir=args.cache_dir)
    elapsed = time.perf_counter() - started
    if args.json:
        print(json.dumps({
            "output": result.output,
            "slides": len(result.slides),
            "objects": result.objects,
            "issues": result.issues,
            "timings": result.timings,
            "seconds": round(elapsed, 3),
            "bytes": os.path.getsize(result.output) if result.ok else 0,
        }, ensure_ascii=False, indent=2))
    else:
        print(result.summary())
    return 0 if result.ok else 1


def cmd_preview(args):
    result = preview(args.html, args.output, theme=_theme(args.theme))
    if args.json:
        print(json.dumps({
            "html": result.html_path,
            "images": result.images,
            "issues": result.issues,
            "timings": result.timings,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"preview written to {result.html_path}")
        for issue in result.issues:
            print(f"  ! {issue}")
    return 0 if result.ok else 1


def cmd_check(args):
    """Build into a temp file and report structural problems only."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        target = os.path.join(temp_dir, "check.pptx")
        result = build(args.html, target, theme=_theme(args.theme), cache_dir=temp_dir)
    report = {
        "slides": len(result.slides),
        "objects": result.objects,
        "timings": {key: round(value, 4) for key, value in result.timings.items()},
        "issues": result.issues,
        "ok": not result.issues,
    }
    pages = []
    for slide in result.slides:
        pages.append({
            "slide": slide.index + 1,
            "title": slide.title,
            "boxes": sum(1 for _box in slide.walk()),
            "past_bottom": _overflow(slide),
        })
    report["page_metrics"] = pages
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not result.issues else 2


def _overflow(slide):
    out = []
    for box in slide.walk():
        if box.bottom > slide.height + 1.5:
            out.append(round(box.bottom, 1))
    return sorted(set(out))[:8]


def cmd_themes(args):
    for name in themes.names():
        theme = themes.load(name)
        print(f"{name:12s} background={theme.colors.get('background')} primary={theme.colors.get('primary')}")
    return 0


def main(argv=None):
    env.enable_utf8()
    missing = env.ensure_dependencies()
    if missing:
        print(f"missing dependencies: {', '.join(missing)}", file=sys.stderr)
        print(f"install with: python -m pip install {' '.join(missing)}", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(prog="deckpress", description="HTML -> editable PPTX")
    sub = parser.add_subparsers(dest="command")

    build_parser = sub.add_parser("build", help="build a .pptx from an HTML deck")
    build_parser.add_argument("html")
    build_parser.add_argument("-o", "--output", default=None)
    build_parser.add_argument("-t", "--theme", default=None)
    build_parser.add_argument("--cache-dir", default=None)
    build_parser.add_argument("--json", action="store_true")
    build_parser.set_defaults(func=cmd_build)

    preview_parser = sub.add_parser("preview", help="render SVG/HTML previews of every slide")
    preview_parser.add_argument("html")
    preview_parser.add_argument("-o", "--output", default=None)
    preview_parser.add_argument("-t", "--theme", default=None)
    preview_parser.add_argument("--json", action="store_true")
    preview_parser.set_defaults(func=cmd_preview)

    check_parser = sub.add_parser("check", help="static checks without keeping the file")
    check_parser.add_argument("html")
    check_parser.add_argument("-t", "--theme", default=None)
    check_parser.set_defaults(func=cmd_check)

    theme_parser = sub.add_parser("themes", help="list builtin themes")
    theme_parser.set_defaults(func=cmd_themes)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    if getattr(args, "command", "") == "build" and not args.output:
        base = os.path.splitext(args.html)[0]
        args.output = base + ".pptx"
    if getattr(args, "command", "") == "preview" and not args.output:
        base = os.path.splitext(args.html)[0]
        args.output = base + "-preview"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
