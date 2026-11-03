"""Benchmark: build the three example decks and report timing + size.

    python tools/bench.py
    python tools/bench.py --json
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptpress import pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


def run():
    if not os.path.isdir(EXAMPLES):
        return {"error": "no examples directory"}
    files = sorted(name for name in os.listdir(EXAMPLES) if name.endswith(".html"))
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in files:
            target = os.path.join(tmp, name.replace(".html", ".pptx"))
            started = time.perf_counter()
            result = pipeline.build(os.path.join(EXAMPLES, name), target)
            elapsed = time.perf_counter() - started
            results.append({
                "deck": name,
                "slides": len(result.slides),
                "objects": result.objects,
                "issues": result.issues,
                "seconds": round(elapsed, 3),
                "bytes": os.path.getsize(target) if result.ok else 0,
                "stages": {key: round(value * 1000, 1) for key, value in result.timings.items()},
            })
    return {"decks": results}


def main(argv=None):
    payload = run()
    if "--json" in (argv or sys.argv[1:]):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"{'deck':<26}{'slides':>7}{'objects':>9}{'ms':>9}{'KB':>8}  issues")
    for item in payload.get("decks", []):
        print(
            f"{item['deck']:<26}{item['slides']:>7}{item['objects']:>9}"
            f"{item['seconds'] * 1000:>9.0f}{item['bytes'] / 1024:>8.0f}"
            f"  {len(item['issues'])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
