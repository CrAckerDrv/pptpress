# 已知缺口

本文件记录**实测确认**的缺失能力：每一条都附复现方式与代码位置。
未列出的项视为已验证可用（见 [实测数据](benchmarks.md)）。

测量方法：构造最小 deck → 构建 → 读回 `ppt/slides/slideN.xml` 或检查布局盒子几何。
判定标准只有一条：**PowerPoint 打开后是否真的呈现出来**。

---

## P0 · 静默出错（不报错，但结果不对）

### 1. 语义标签的默认字重/字号从未生效

`<b>`、`<strong>`、`<i>`、`<em>`、`<h1>`…`<h6>` 在 **没有显式 CSS** 时不会变粗、不会变大。

| 输入 | 期望 | 实测 |
|---|---|---|
| `<h1>标题</h1>` | 32pt / 700 | **12pt / 400** |
| `<b>粗体</b>` | 700 | **400** |
| `<i>斜体</i>` | italic | **normal** |

**根因**：`css._DEFAULT_INHERITED` 提供 `font-size:16px`、`font-weight:400`、
`font-style:normal`，它们是可继承属性，因此在 `layout.build_style()`（第 216–232 行）
里 `computed.get(...)` 永远拿得到值，指向标签的兜底分支
（`HEADING_SIZE` / `HEADING_WEIGHT` / `b,strong→700` / `i,em→italic`）**全部是死代码**。

**为什么示例看不出问题**：四份示例都显式写了字号与字重
（如 `aurora-launch` 的 `.stat b{font-weight:700}`、`h1{font-size:74px}`），
所以恰好绕过了这个 bug。裸写 HTML 的 deck 会全部退化成 12pt 正文。

**修复方案**：把标签默认值从"Python 兜底"改成 **UA 样式表**，
在 `parse_stylesheets()` 里先注入一份内置规则，再叠加作者 CSS
（作者规则 order 更大，同特异性下自然覆盖）：

```css
h1{font-size:32pt;font-weight:700} … h6{font-size:12pt;font-weight:600}
b,strong,th{font-weight:700}
i,em{font-style:italic}
small{font-size:.85em}
sub,sup{font-size:.75em;baseline:sub|super}
```

工作量：约 40 行 + 8 条回归用例。
**风险**：加粗后文本变宽，四份示例需要重新过一遍溢出与 `--strict` 校验。

### 2. `repeat(auto-fit, minmax(...))` 直接崩溃

```css
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
```

```
AttributeError: 'NoneType' object has no attribute 'resolve'
  values.py:571  parse_track_list
```

单用 `minmax(200px,1fr)` 或 `repeat(2,minmax(...))` 都正常，只有 `auto-fit` + `minmax`
进入未加保护的"固定长度"分支。这是**唯一会让构建中断**的 CSS 组合。

修复：在 `parse_track_list` 里先把 `minmax(a,b)` 归约为 `b`，再判断 `fr`。
工作量：约 10 行。

---

## P1 · 样式表达力（决定"能不能做出更丰富的版面"）

| # | 能力 | 现状 | 代码位置 | 工作量 |
|---|---|---|---|---|
| 3 | `grid-column: span 2` / 显式 `grid-row` | 忽略，按 DOM 顺序逐格填 | `layout._layout_grid` | 中 |
| 4 | `align-content` | 忽略，行永远贴顶 | 同上 | 小 |
| 5 | `border-radius` 四角不同 / `50% 20%` 椭圆 | 只取最大半径，画 `roundRect` | `writer._radius` | 中 |
| 6 | `text-decoration: line-through` | 解析了，写出时只判断 `underline` | `writer.py:300` | 小 |
| 7 | `text-shadow` | 解析了，但只写形状阴影，run 级 `effectLst` 从不写 | `writer._text` | 中 |
| 8 | `<ol>` 有序列表 | 输出 `buChar` 圆点，从不写 `buAutoNum` | `layout.py:1091` | 小 |
| 9 | `aspect-ratio` | 未解析 | `layout.build_style` | 小 |
| 10 | `object-position` | 无 `Style` 槽位 | `layout.Style.__slots__` | 小 |
| 11 | `writing-mode: vertical-rl` | 无槽位（竖排无法实现） | 同上 | 大 |
| 12 | `font-variant-numeric` | 无槽位（表格数字等宽做不了） | 同上 | 小 |
| 13 | `transform: translateX(-50%)` | 只支持 `rotate`，居中定位算不出来 | `values.parse_transform` | 中 |
| 14 | `height: 50%` 在定高父容器内 | **算错**：按画布高度 540pt 而非父容器 300px 解析（得 270pt，应为 112.5pt） | `layout._resolve_length` 的 percent base | 中 |
| 15 | `calc()` / `clamp()` | 未解析，回落到默认字号 | `values.parse_length` | 中 |
| 16 | `::before` / `::after` `content` | 选择器能匹配，但内容从不生成 | `layout` / `writer` | 中 |

> 说明：`vw` / `vh` **可用**（`2vw` → 19.2pt、`2vh` → 10.8pt）、
> `rem` / `em` / `%` 字号 **可用**，这三项不需要改。

---

## P2 · 结构化对象

| # | 能力 | 现状 | 代码位置 |
|---|---|---|---|
| 17 | 表格 `rowspan` | 忽略（`colspan` 正常） | `writer._table`（只处理 `_colspan`） |
| 18 | SVG `<linearGradient>` / `<radialGradient>` / `clipPath` | **失效**：HTML 解析器把标签名小写成 `lineargradient`，`svgshape` 只认驼峰，于是整图回退为 PNG | `dom.py` 用 `lxml.html` 解析 → `svgshape._gradients` |
| 19 | SVG `stroke-dasharray` | 丢弃（`SvgShape.__slots__` 没有 dash 槽位） | `svgshape.SvgShape` |
| 20 | 多背景层 | 只取第一层 | `values.parse_background` |
| 21 | `conic-gradient` / `repeating-*-gradient` | 丢弃 / 退化为普通渐变 | `values.parse_gradient` |
| 22 | `filter: blur()` / `clip-path` | 未映射（DrawingML 无对应表达） | — |

第 18 条值得单独说明：它让"带渐变图标的卡片"悄悄变成位图，
恰好破坏本项目"零整页位图"的核心承诺。修复方式是在 `dom` 解析后把已知 SVG 标签
重新大小写化（`lineargradient → linearGradient`、`viewbox → viewBox` 等），
或者对 `<svg>` 子树直接用 XML 解析器而不是 HTML 解析器。

---

## 建议的下一步顺序

1. **P0-2**（崩溃）：10 行，先把构建的健壮性补上。
2. **P0-1**（语义标签）：40 行，收益最大——它决定"裸写 HTML 能不能看"。
3. **P2-18**（SVG 大小写）：约 30 行，直接消除一类隐性位图。
4. **P1-3/4/5/6/8/9**：一批小改动，合起来就是"版面更丰富"。
5. **P1-14/13**（百分比基准、translate 居中）：影响常见居中版式，做完后
   `left:50%;transform:translateX(-50%)` 这类写法才敢用。
6. **P1-11/16**（竖排、伪元素）：单独排期，属于新特性而非修 bug。

每完成一条，在 `tests/test_engine.py` 里补最小用例，并从本文件删掉对应行。
