# 已知缺口

本文件记录**实测确认仍未解决**的缺失能力：每一条都附复现方式与代码位置。
已修复的项列在文末的 [已修复](#已修复-110)，并已转成 `tests/test_gaps.py` 的回归用例。

测量方法：构造最小 deck → 构建 → 读回 `ppt/slides/slideN.xml` 或检查布局盒子几何。
判定标准只有一条：**PowerPoint 打开后是否真的呈现出来**。

> 最近一次核对：1.2.0（2026-11-05）。共 46 项检查，其中 30 项通过、16 项仍为缺口
> （其中 3 项属于动效：路径动画、指定对象触发、按数据点入场）。

---

## P0 · 静默出错（不报错，但结果不对）

暂无。1.1.0 修掉了两个 P0 项，见文末。

---

## P1 · 样式表达力

| # | 能力 | 现状 | 代码位置 | 工作量 |
|---|---|---|---|---|
| 1 | `writing-mode: vertical-rl` | 无 `Style` 槽位，竖排无法实现 | `layout.Style.__slots__` | 大 |
| 2 | `::before` / `::after` `content` | 选择器匹配得到，内容从不生成 | `layout` / `writer` | 中 |
| 3 | `calc()` / `clamp()` | 未解析，回落到默认值 | `values.parse_length` | 中 |
| 4 | `float` / `columns` | 未实现（有意不做，见 roadmap） | — | — |
| 5 | `filter: blur()` / `clip-path` | DrawingML 无原生对应表达 | — | 大 |
| 6 | `conic-gradient` / `repeating-*-gradient` | 前者丢弃，后者退化为普通渐变 | `values.parse_gradient` | 中 |
| 7 | 多背景层 | 只取第一层 | `values.parse_background` | 小 |
| 8 | `background-size: contain` + `object-position` | 解析了但图片填充未使用该值 | `writer._picture_fill` | 小 |

## P2 · 结构化对象与动效

| # | 能力 | 现状 | 代码位置 |
|---|---|---|---|
| 9 | 表格 `rowspan` | 忽略（`colspan` 正常） | `writer._table`（只处理 `_colspan`） |
| 10 | 原生图表对象 `c:chart` | 图表目前是 SVG 路径（矢量可改色，但不携带数据） | 未实现，见 roadmap 阶段一 |
| 11 | 一稿多主题构建（同内容深/浅两版） | 手动改 `:root` 后重建，无 CLI 支持 | `cli.py` |
| 12 | 路径动画 `motion-path` | 只支持进入/退出/强调，无沿路径移动 | `animate.py` |
| 13 | 点击指定对象触发动画 | 只有 `click` / `with` / `after` | `animate.EFFECTS` 之外 |
| 14 | 动画图表（按数据点逐条入场） | 整个图表作为一个单元 | `writer._icon` |

---

## 建议的下一步顺序

1. **`::before` / `::after`**（P1-2）：徽章、编号、引号装饰都依赖它，收益最高。
2. **`calc()` / `clamp()`**（P1-3）：响应式字号写法现在会静默失效。
3. **表格 `rowspan`**（P2-9）：与已实现的 `colspan` 同源，补齐成本低。
4. **原生图表**（P2-10）：路线图阶段一，工作量最大但价值最高。
5. **`writing-mode`**（P1-1）：单独立项，属于新特性而非修 bug。

动效三项目前不做：路径动画和"点击指定对象"在真实放映里都是误触来源，
按数据点逐条入场需要拆开 SVG 图表的数据结构，收益与成本不成比例。

每完成一条，在 `tests/test_gaps.py` 里补最小用例，并从本文件删掉对应行。

---

## 已修复（1.1.0）

| 原缺口 | 修复方式 | 回归用例 |
|---|---|---|
| `repeat(auto-fit, minmax())` 构建崩溃 | `values._minmax_track` 归约上下界；`auto-fit` 用最小值算列数 | `test_grid_minmax_never_crashes`、`test_auto_fit_column_count_uses_the_minimum` |
| 语义标签默认样式失效（裸 `<h1>` = 12pt） | 内置 UA 样式表注入级联，作者 CSS 仍然覆盖 | `test_heading_scale`、`test_inline_semantics` |
| `grid-column: span N` / 显式 `grid-row` 被忽略 | `layout._place_grid_cells` 做显式定位 + 行优先自动排布 | `test_grid_column_span`、`test_grid_explicit_placement` |
| `align-content` 被忽略 | 网格行按 `start/center/end/space-between` 分布 | `test_grid_align_content_centers_rows` |
| `border-radius` 四角不同 / 椭圆 | 生成 `custGeom` 自定义几何（含 `arcTo`） | `test_per_corner_radius_uses_custom_geometry`、`test_elliptical_radius_uses_custom_geometry` |
| `text-decoration: line-through` 丢失 | `a:rPr@strike="sngStrike"` | `test_line_through_is_native` |
| `text-shadow` 只落在形状上 | run 级 `a:rPr/a:effectLst/a:outerShdw` | `test_text_shadow_lands_on_the_run` |
| `<ol>` 输出圆点 | 原生 `a:buAutoNum`（含 `startAt`、罗马/字母方案） | `test_ordered_list_uses_native_numbering` |
| `aspect-ratio` 未解析 | 参与盒子高度推导 | `test_aspect_ratio_sizes_the_box` |
| `height: N%` 按画布而非父容器 | 百分比基准改为包含块 | `test_percentage_height_uses_the_parent_not_the_canvas` |
| `transform: translateX(-50%)` 失效 | `Percent` 保留在 transform 中，布局后按自身宽高解析 | `test_translate_percent_centers_the_box` |
| SVG `<linearGradient>` 等标签被 HTML 解析器小写化 → 整图退化为 PNG | `dom._restore_svg_case` 还原标签与属性大小写 | `test_svg_gradient_survives_the_html_parser` |
| SVG `stroke-dasharray` 被丢弃 | `SvgShape.dash` → `a:prstDash` 预设 | `test_svg_dasharray_becomes_a_preset_dash` |
| `<sub>` / `<sup>` 无基线偏移 | `a:rPr@baseline` | `test_sub_sup_use_baseline_shift` |
