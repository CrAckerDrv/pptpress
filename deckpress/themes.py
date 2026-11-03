"""Theme support: CSS custom properties + PPTX theme colours in one file."""

from __future__ import annotations

import json
import os

BUILTIN = {
    "noir": {
        "colors": {
            "background": "#0B0C10", "surface": "#14161C", "text": "#F4F6FB",
            "text_muted": "#9AA3B5", "primary": "#6EE7B7", "secondary": "#60A5FA",
            "accent_3": "#F472B6", "accent_4": "#FBBF24", "accent_5": "#A78BFA",
            "accent_6": "#34D399", "line": "#23262F", "paper": "#0B0C10", "ink": "#F4F6FB",
        },
        "fonts": {"display": "'Inter', sans-serif", "body": "'Inter', sans-serif", "mono": "'JetBrains Mono', monospace"},
    },
    "paper": {
        "colors": {
            "background": "#FBFAF7", "surface": "#FFFFFF", "text": "#16181D",
            "text_muted": "#6B7280", "primary": "#E4572E", "secondary": "#1F6FEB",
            "accent_3": "#0F766E", "accent_4": "#B45309", "accent_5": "#7C3AED",
            "accent_6": "#DB2777", "line": "#E5E2DA", "paper": "#FBFAF7", "ink": "#16181D",
        },
        "fonts": {"display": "'Georgia', serif", "body": "'Inter', sans-serif", "mono": "'IBM Plex Mono', monospace"},
    },
    "swiss": {
        "colors": {
            "background": "#FFFFFF", "surface": "#F2F2F2", "text": "#0A0A0A",
            "text_muted": "#6E6E6E", "primary": "#FF3B30", "secondary": "#111111",
            "accent_3": "#2F6FED", "accent_4": "#FFC400", "accent_5": "#111111",
            "accent_6": "#7A7A7A", "line": "#DADADA", "paper": "#FFFFFF", "ink": "#0A0A0A",
        },
        "fonts": {"display": "'Helvetica Neue', Arial, sans-serif", "body": "'Helvetica Neue', Arial, sans-serif", "mono": "'Courier New', monospace"},
    },
    "ocean": {
        "colors": {
            "background": "#F5F9FC", "surface": "#FFFFFF", "text": "#0B2545",
            "text_muted": "#5B7189", "primary": "#0A6E8A", "secondary": "#22A6B3",
            "accent_3": "#F2B705", "accent_4": "#EF6C4D", "accent_5": "#7B61FF",
            "accent_6": "#2EC4B6", "line": "#D7E3ED", "paper": "#F5F9FC", "ink": "#0B2545",
        },
        "fonts": {"display": "'Inter', sans-serif", "body": "'Inter', sans-serif", "mono": "'IBM Plex Mono', monospace"},
    },
    "ember": {
        "colors": {
            "background": "#1A1210", "surface": "#261A16", "text": "#FDF1E7",
            "text_muted": "#C2A899", "primary": "#FF7A45", "secondary": "#FFC53D",
            "accent_3": "#F0A6CA", "accent_4": "#9AE6B4", "accent_5": "#B794F4",
            "accent_6": "#F6AD55", "line": "#3B2A23", "paper": "#1A1210", "ink": "#FDF1E7",
        },
        "fonts": {"display": "'Georgia', serif", "body": "'Inter', sans-serif", "mono": "'JetBrains Mono', monospace"},
    },
    "mint": {
        "colors": {
            "background": "#F3FBF6", "surface": "#FFFFFF", "text": "#0C2B20",
            "text_muted": "#527A69", "primary": "#0E9F6E", "secondary": "#0B7285",
            "accent_3": "#F59E0B", "accent_4": "#6366F1", "accent_5": "#EC4899",
            "accent_6": "#14B8A6", "line": "#D3E8DC", "paper": "#F3FBF6", "ink": "#0C2B20",
        },
        "fonts": {"display": "'Inter', sans-serif", "body": "'Inter', sans-serif", "mono": "'JetBrains Mono', monospace"},
    },
    "blueprint": {
        "colors": {
            "background": "#0E2A4A", "surface": "#123A63", "text": "#E8F1FB",
            "text_muted": "#9DBBD8", "primary": "#4CC9F0", "secondary": "#F72585",
            "accent_3": "#FFD166", "accent_4": "#06D6A0", "accent_5": "#B5179E",
            "accent_6": "#7209B7", "line": "#1D4E7C", "paper": "#0E2A4A", "ink": "#E8F1FB",
            "grid": "rgba(255,255,255,0.08)",
        },
        "fonts": {"display": "'IBM Plex Sans', 'Inter', sans-serif", "body": "'Inter', sans-serif", "mono": "'IBM Plex Mono', monospace"},
    },
    "risograph": {
        "colors": {
            "background": "#FDF6EC", "surface": "#FFFFFF", "text": "#141414",
            "text_muted": "#5A5A5A", "primary": "#FF5C8A", "secondary": "#2E5BFF",
            "accent_3": "#FFC93C", "accent_4": "#00B894", "accent_5": "#8E44AD",
            "accent_6": "#FF7A00", "line": "#E8DFD2", "paper": "#FDF6EC", "ink": "#141414",
        },
        "fonts": {"display": "'Archivo Black', 'Impact', sans-serif", "body": "'Inter', sans-serif", "mono": "'Space Mono', monospace"},
    },
}


class Theme:
    def __init__(self, name, data):
        self.name = name
        self.colors = dict(data.get("colors") or {})
        self.fonts = dict(data.get("fonts") or {})
        self.extra = {k: v for k, v in data.items() if k not in ("colors", "fonts")}

    def variables(self):
        variables = {}
        for key, value in self.colors.items():
            variables[f"color-{key}"] = value
            variables[key] = value
        for key, value in self.fonts.items():
            variables[f"font-{key}"] = value
            variables[f"font-family-{key}"] = value
        for key, value in self.extra.items():
            if isinstance(value, (str, int, float)):
                variables[key] = value
        return variables

    def to_css(self, selector=":root"):
        lines = [f"{selector} {{"]
        for key, value in self.variables().items():
            lines.append(f"  --{key}: {value};")
        lines.append("}")
        return "\n".join(lines)

    def __repr__(self):
        return f"<Theme {self.name} colors={len(self.colors)}>"


def load(theme="paper", themes_dir=None):
    """Load a theme by name from builtin presets or a ``themes/*.json`` folder."""
    if isinstance(theme, Theme):
        return theme
    if isinstance(theme, dict):
        return Theme(theme.get("name", "custom"), theme)
    name = theme or "paper"
    if name in BUILTIN:
        return Theme(name, BUILTIN[name])
    if themes_dir:
        for candidate in (os.path.join(themes_dir, f"{name}.json"), os.path.join(themes_dir, name)):
            if os.path.exists(candidate):
                with open(candidate, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return Theme(data.get("name", name), data)
    raise ValueError(f"unknown theme '{name}'; available: {', '.join(sorted(BUILTIN))}")


def names():
    return sorted(BUILTIN)
