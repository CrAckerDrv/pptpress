"""Chart geometry for the courseware deck.

Each chart's viewBox aspect ratio is chosen to match its on-slide frame exactly,
so the exporter's uniform scale fills the card without letterboxing and keeps
label sizes identical to what the browser would show.
"""

from __future__ import annotations

import math

FONT = 11


def catmull(pts):
    if not pts:
        return ""
    parts = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for index in range(len(pts) - 1):
        p0 = pts[max(0, index - 1)]
        p1 = pts[index]
        p2 = pts[index + 1]
        p3 = pts[min(len(pts) - 1, index + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        parts.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(parts)


def head(vw, vh):
    return (f'<svg viewBox="0 0 {vw} {vh}" fill="none" '
            f'xmlns="http://www.w3.org/2000/svg">')


def txt(x, y, value, size=FONT, fill="#667085", anchor="start", weight=None):
    extra = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}"{extra}>{value}</text>')


# ---------------------------------------------------------------- chart A
def chart_a():
    """Accuracy vs test-time budget. Frame 700x470 -> viewBox 600x403."""
    X0, X1, Y0, Y1 = 58.0, 582.0, 28.0, 344.0
    VMIN, VMAX = 0.55, 0.95
    ay = lambda v: Y1 - (v - VMIN) / (VMAX - VMIN) * (Y1 - Y0)
    ax = lambda b: X0 + math.log2(b) / 6.0 * (X1 - X0)
    out = [head(600, 403)]
    for v in (0.65, 0.75, 0.85, 0.95):
        out.append(f'<line x1="{X0}" y1="{ay(v):.1f}" x2="{X1}" y2="{ay(v):.1f}" stroke="#EDF1F7" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    for v in (0.55, 0.65, 0.75, 0.85, 0.95):
        out.append(txt(X0 - 8, ay(v) + 4, f"{int(v * 100)}%", anchor="end"))
    for b in (1, 2, 4, 8, 16, 32, 64):
        out.append(txt(ax(b), Y1 + 18, f"{b}×", anchor="middle"))
    out.append(txt((X0 + X1) / 2, Y1 + 38, "测试时算力预算（相对倍数，对数刻度）",
                   fill="#5A6B80", anchor="middle"))

    low, high = ax(24), X1
    out.append(f'<rect x="{low:.1f}" y="{ay(0.90):.1f}" width="{high - low:.1f}" '
               f'height="{Y1 - ay(0.90):.1f}" fill="#1D4ED8" opacity="0.05"/>')
    out.append(txt(ax(32), ay(0.60), "高预算区 · 收益分化", fill="#5A6B80"))

    budgets = [1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64]
    direct = [(ax(b), ay(0.612)) for b in budgets]
    cot = [(ax(b), ay(0.612 + 0.190 * (1 - math.exp(-b / 3.4)))) for b in budgets]
    search = [(ax(b), ay(0.612 + 0.312 * (1 - math.exp(-b / 8.5)))) for b in budgets]
    out.append(f'<path d="{catmull(direct)}" stroke="#7C8898" stroke-width="2.4" stroke-dasharray="5 4"/>')
    out.append(f'<path d="{catmull(cot)}" stroke="#0C8479" stroke-width="2.8"/>')
    out.append(f'<path d="{catmull(search)}" stroke="#1D4ED8" stroke-width="2.8"/>')
    out.append(f'<circle cx="{search[-1][0]:.1f}" cy="{search[-1][1]:.1f}" r="4" fill="#1D4ED8"/>')
    out.append(f'<circle cx="{cot[-1][0]:.1f}" cy="{cot[-1][1]:.1f}" r="4" fill="#0C8479"/>')
    # Labels sit in the empty band between the curves, never on top of a stroke.
    out.append(txt(ax(4) + 4, ay(0.905), "推理搜索", fill="#1D4ED8", weight="bold"))
    out.append(txt(ax(4) + 4, ay(0.878), "多采样 + 验证器", fill="#1D4ED8"))
    out.append(txt(ax(4) + 4, ay(0.70), "思维链", fill="#0C8479", weight="bold"))
    out.append(txt(ax(4) + 4, ay(0.673), "单条链写更长", fill="#0C8479"))
    out.append(txt(ax(1) + 8, ay(0.612) + 18, "直接回答（水平线）", fill="#5F6E80"))
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- chart B
def chart_b():
    """Verifier vs plain voting. Frame 700x470 -> viewBox 600x403."""
    X0, X1, Y0, Y1 = 58.0, 582.0, 28.0, 344.0
    VMIN, VMAX = 0.55, 0.95
    by = lambda v: Y1 - (v - VMIN) / (VMAX - VMIN) * (Y1 - Y0)
    bx = lambda n: X0 + math.log2(n) / 5.0 * (X1 - X0)
    out = [head(600, 403)]
    for v in (0.65, 0.75, 0.85, 0.95):
        out.append(f'<line x1="{X0}" y1="{by(v):.1f}" x2="{X1}" y2="{by(v):.1f}" stroke="#EDF1F7" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    for v in (0.55, 0.65, 0.75, 0.85, 0.95):
        out.append(txt(X0 - 8, by(v) + 4, f"{int(v * 100)}%", anchor="end"))
    for n in (1, 2, 4, 8, 16, 32):
        out.append(txt(bx(n), Y1 + 18, f"{n}", anchor="middle"))
    out.append(txt((X0 + X1) / 2, Y1 + 38, "采样条数 n（自一致投票）", fill="#5A6B80", anchor="middle"))

    ns = [1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24, 32]
    plain = [(bx(n), by(0.612 + 0.030 * (1 - math.exp(-n / 4.5)) - 0.018 * (n / 32.0) ** 2)) for n in ns]
    verified = [(bx(n), by(0.612 + 0.318 * (1 - math.exp(-n / 5.2)))) for n in ns]
    out.append(f'<path d="{catmull(verified)}" stroke="#1D4ED8" stroke-width="2.8"/>')
    out.append(f'<path d="{catmull(plain)}" stroke="#7C8898" stroke-width="2.4" stroke-dasharray="5 4"/>')
    out.append(f'<circle cx="{verified[-1][0]:.1f}" cy="{verified[-1][1]:.1f}" r="4" fill="#1D4ED8"/>')
    out.append(f'<circle cx="{plain[-1][0]:.1f}" cy="{plain[-1][1]:.1f}" r="4" fill="#5F6E80"/>')

    gap_x = bx(8)
    out.append(f'<line x1="{gap_x:.1f}" y1="{by(0.93):.1f}" x2="{gap_x:.1f}" y2="{by(0.63):.1f}" '
               f'stroke="#C2410C" stroke-width="1.2" stroke-dasharray="4 4"/>')
    out.append(txt(gap_x + 8, (by(0.93) + by(0.63)) / 2, "差 25 个百分点", fill="#C2410C"))
    out.append(txt(bx(1) + 10, by(0.668) - 12, "有验证器", fill="#1D4ED8", weight="bold"))
    out.append(txt(bx(1) + 10, by(0.618) + 20, "无验证器（纯投票）", fill="#5F6E80"))
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- chart C
def chart_c():
    """Latency budget by stage. Frame 680x380 -> viewBox 600x335."""
    X0, X1 = 46.0, 566.0
    out = [head(600, 335)]
    rows = [("路由判定", 0.4, "#1D4ED8", "0.4s"), ("检索专家", 1.1, "#0C8479", "1.1s"),
            ("推理专家", 1.4, "#7C3AED", "1.4s"), ("验证与汇总", 0.7, "#C2410C", "0.7s")]
    total = sum(r[1] for r in rows)
    out.append(f'<line x1="{X0}" y1="40" x2="{X0}" y2="176" stroke="#94A3B5" stroke-width="1.4"/>')
    out.append(txt(X0 - 8, 44, "0s", anchor="end"))
    out.append(txt(X0 - 8, 180, "3.6s", anchor="end"))
    cursor = 0.0
    for name, value, color, label in rows:
        x = X0 + cursor / total * (X1 - X0)
        w = value / total * (X1 - X0)
        out.append(f'<rect x="{x:.1f}" y="62" width="{w:.1f}" height="52" rx="6" fill="{color}"/>')
        out.append(txt(x + w / 2, 94, name, fill="#FFFFFF", anchor="middle", weight="bold"))
        out.append(txt(x + w / 2, 142, f"{label} · {value / total * 100:.0f}%", fill="#5A6B80", anchor="middle"))
        cursor += value
    out.append(txt(X0, 208, "串行：路由 + 验证汇总（占 30%）", fill="#667085"))
    out.append(txt(X0, 230, "并行：两个专家同时开始，耗时不叠加（占 70%）", fill="#0C8479"))

    out.append(f'<rect x="{X0}" y="252" width="{X1 - X0}" height="14" rx="7" fill="#EDF1F7"/>')
    cursor = 0.0
    for _name, value, color, _label in rows:
        x = X0 + cursor / total * (X1 - X0)
        w = value / total * (X1 - X0)
        out.append(f'<rect x="{x:.1f}" y="252" width="{w:.1f}" height="14" fill="{color}" opacity="0.55"/>')
        cursor += value
    out.append(txt(X0, 292, "总延迟 ≈ 3.6s；专家从 1 个加到 3 个，耗时不变、成本 ×3", fill="#5A6B80"))
    out.append(txt(X0, 316, "延迟优化点在串行段，而不是再并联一个专家", fill="#C2410C"))
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- chart D
def chart_d():
    """Latency vs cost scatter. Frame 680x470 -> viewBox 600x415."""
    X0, X1, Y0, Y1 = 66.0, 566.0, 30.0, 350.0
    dx = lambda lat: X0 + (math.log2(lat) - math.log2(0.5)) / 5.0 * (X1 - X0)
    dy = lambda cost: Y1 - math.log2(cost) / 6.0 * (Y1 - Y0)
    out = [head(600, 415)]
    for cost in (2, 4, 8, 16, 32):
        out.append(f'<line x1="{X0}" y1="{dy(cost):.1f}" x2="{X1}" y2="{dy(cost):.1f}" stroke="#EDF1F7" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    for cost in (1, 2, 4, 8, 16, 32, 64):
        out.append(txt(X0 - 8, dy(cost) + 4, f"{cost}×", anchor="end"))
    for lat in (0.5, 1, 2, 4, 8, 16):
        out.append(txt(dx(lat), Y1 + 20, f"{lat}s", anchor="middle"))
    out.append(txt((X0 + X1) / 2, Y1 + 42, "单次请求延迟（对数刻度）", fill="#5A6B80", anchor="middle"))

    rx0, ry0 = dx(0.5), dy(4)
    out.append(f'<rect x="{rx0:.1f}" y="{ry0:.1f}" width="{dx(2.4) - rx0:.1f}" '
               f'height="{Y1 - ry0:.1f}" fill="#0C8479" opacity="0.07"/>')
    # Caption goes into the empty upper-left corner of the highlighted band; all
    # five callouts sit below or to the right of it.
    out.append(f'<rect x="{rx0 + 8:.1f}" y="{ry0 + 8:.1f}" width="10" height="10" fill="#0C8479" opacity="0.3"/>')
    out.append(txt(rx0 + 24, ry0 + 17, "浅绿区：低延迟 + 低成本", fill="#0C8479"))
    out.append(txt(rx0 + 24, ry0 + 32, "优先把流量落在这里", fill="#0C8479"))

    points = [
        ("规则路由", 0.6, 1.0, "#0C8479", "0.6s · 1×", 15, -26, "start"),
        ("模型路由", 1.1, 2.2, "#0C8479", "1.1s · 2.2× · 推荐主方案", 15, 18, "start"),
        ("学习式门控", 1.6, 3.0, "#7C3AED", "1.6s · 3×", 15, -16, "start"),
        ("广播投票", 7.5, 26.0, "#C2410C", "7.5s · 26× · 高风险分支", -16, -8, "end"),
        ("搜索 + 验证", 12.0, 46.0, "#1D4ED8", "12s · 46× · 须能验证", -16, -16, "end"),
    ]
    for name, lat, cost, color, detail, dx_off, dy_off, anchor in points:
        cx, cy = dx(lat), dy(cost)
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="{color}"/>')
        out.append(txt(cx + dx_off, cy + dy_off, name, fill="#0E1B2A", anchor=anchor, weight="bold"))
        out.append(txt(cx + dx_off, cy + dy_off + 14, detail, fill="#5A6B80", anchor=anchor))
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- chart E
def chart_e():
    """Error compounding along a chain. Frame 540x400 -> viewBox 460x341."""
    X0, X1, Y0, Y1 = 48.0, 436.0, 28.0, 288.0
    ey = lambda v: Y1 - (v - 0.70) / (0.96 - 0.70) * (Y1 - Y0)
    ex = lambda d: X0 + (d - 1) / 5.0 * (X1 - X0)
    out = [head(460, 341)]
    for v in (0.75, 0.80, 0.85, 0.90, 0.95):
        out.append(f'<line x1="{X0}" y1="{ey(v):.1f}" x2="{X1}" y2="{ey(v):.1f}" stroke="#EDF1F7" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    out.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#94A3B5" stroke-width="1.4"/>')
    for v in (0.70, 0.75, 0.80, 0.85, 0.90, 0.95):
        out.append(txt(X0 - 7, ey(v) + 4, f"{int(v * 100)}%", anchor="end"))
    for d in range(1, 7):
        out.append(txt(ex(d), Y1 + 20, f"{d}", anchor="middle"))
    out.append(txt((X0 + X1) / 2, Y1 + 40, "链路节点数（每步正确率 95%）", fill="#5A6B80", anchor="middle"))

    curve = [(ex(d), ey(0.95 ** d)) for d in range(1, 7)]
    out.append(f'<path d="{catmull(curve)}" stroke="#C2410C" stroke-width="2.8"/>')
    for index, (cx, cy) in enumerate(curve):
        radius = 5 if index == len(curve) - 1 else 3.2
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" fill="#C2410C"/>')
    out.append(txt(curve[0][0] + 7, curve[0][1] - 10, "95%", fill="#C2410C"))
    out.append(txt(curve[2][0] - 4, curve[2][1] - 10, "86%", fill="#C2410C", anchor="middle"))
    out.append(txt(curve[5][0] - 8, curve[5][1] - 16, "74%", fill="#C2410C", anchor="end", weight="bold"))
    out.append(txt(curve[5][0] - 8, curve[5][1] + 22, "六步串联", fill="#667085", anchor="end"))
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- chart F
def chart_f():
    """Gate weights. Frame 470x270 -> viewBox 420x241."""
    out = [head(420, 241)]
    rows = [("E1", 0.42, True), ("E2", 0.31, True), ("E3", 0.15, False), ("E4", 0.12, False)]
    out.append(txt(0, 18, "一次前向的门控权重（k = 2）", fill="#5A6B80"))
    for index, (name, weight, selected) in enumerate(rows):
        y = 48 + index * 42
        bar_color = "#1D4ED8" if selected else "#94A3B5"
        name_color = "#0E1B2A" if selected else "#667085"
        out.append(txt(0, y + 15, name, fill=name_color, weight="bold" if selected else None))
        out.append(f'<rect x="34" y="{y}" width="300" height="16" rx="8" fill="#EDF1F7"/>')
        out.append(f'<rect x="34" y="{y}" width="{weight * 300:.1f}" height="16" rx="8" fill="{bar_color}"/>')
        out.append(txt(346, y + 15, f"{weight:.2f}", fill="#1D4ED8" if selected else "#5F6E80"))
    out.append(f'<line x1="0" y1="212" x2="400" y2="212" stroke="#DDE3EC" stroke-width="1.2"/>')
    out.append(txt(0, 232, "灰条 = 被门控跳过，不产生计算量", fill="#C2410C"))
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    for label, builder in (
        ("CHART_A_P05", chart_a), ("CHART_B_P07", chart_b), ("CHART_C_P11", chart_c),
        ("CHART_D_P12", chart_d), ("CHART_E_P13", chart_e), ("CHART_F_P10", chart_f),
    ):
        print(f"<!-- {label} -->")
        print(builder())
        print()
