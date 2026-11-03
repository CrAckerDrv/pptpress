"""Startup plumbing for Deckpress.

Console output is forced to UTF-8 so CJK deck names and warning text survive a
Windows code page, and optional dependencies are checked once with a message
that says exactly what to install.
"""

from __future__ import annotations

import sys

REQUIRED = {
    "pptx": "python-pptx",
    "lxml": "lxml",
    "tinycss2": "tinycss2",
    "PIL": "Pillow",
}


def enable_utf8():
    """Make stdout/stderr UTF-8 where the platform allows it."""
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", "") or ""
        if encoding.lower().replace("-", "") in ("utf8", "utf8mb4"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable
            pass


def ensure_dependencies():
    """Return a list of missing distributions (empty when everything is present)."""
    missing = []
    for module, distribution in REQUIRED.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(distribution)
    return missing
