"""Regenerate the six chart SVG blocks inside the courseware deck.

Charts are generated from real numbers (see ``build_charts.py``) and injected
between marker comments, so the deck HTML stays readable while the curves stay
mathematically honest.

Run from the repository root:

    python examples/charts/apply_charts.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = os.path.join(os.path.dirname(HERE), "ai-thinking-orchestration.html")

# On-slide frame width (px) for each chart, keyed by marker. The chart's viewBox
# aspect ratio is chosen to match, so the uniform scale fills the card exactly.
FRAMES = {
    "CHART_A_P05": 700,
    "CHART_B_P07": 700,
    "CHART_F_P10": 430,
    "CHART_C_P11": 680,
    "CHART_D_P12": 680,
    "CHART_E_P13": 540,
}


def chart_markup():
    # Force UTF-8 on the child's stdout: the generator prints CJK labels, and the
    # Windows console code page would otherwise corrupt them mid-line.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "build_charts.py")],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(result.stderr or "build_charts.py produced no output")
    blocks = re.split(r"<!-- (CHART_\w+) -->", result.stdout)
    return {blocks[i]: blocks[i + 1].strip() for i in range(1, len(blocks), 2)}


def main():
    grid = chart_markup()
    html = open(DECK, encoding="utf-8").read()

    for key, markup in grid.items():
        wrapped = f"<!-- {key} -->\n{markup}\n<!-- /{key} -->"
        html = re.sub(rf"<!-- {key} -->.*?<!-- /{key} -->", lambda m: wrapped, html, flags=re.S)

    # Pin each chart column's width so the frame aspect matches the viewBox.
    for key, width in FRAMES.items():
        pattern = re.compile(
            rf'<div style="(width:\d+px|flex:1)">\s*<div class="chart">\s*<!-- {key} -->',
            re.S,
        )
        html = pattern.sub(
            lambda m: f'<div style="width:{width}px"><div class="chart"><!-- {key} -->',
            html,
        )
    open(DECK, "w", encoding="utf-8").write(html)
    print(f"injected {len(grid)} charts into {os.path.relpath(DECK)}")


if __name__ == "__main__":
    main()
