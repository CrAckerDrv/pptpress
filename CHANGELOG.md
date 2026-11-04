# Changelog

遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Planned

见 [`docs/roadmap.md`](docs/roadmap.md)。

---

## [1.1.0] — 2026-11-05

以"实测缺口"驱动的一次修复版本：先写探针确认每条缺口真的存在，再修，再把每条转成回归用例。
测试从 10 条增至 **43 条**，四份示例在 `--strict` 下全部 0 错误 0 警告。

### Fixed — 会静默出错的两个 P0

* **`repeat(auto-fit, minmax(...))` 导致构建崩溃**（`AttributeError: 'NoneType'`）。
  `parse_track_list` 现在先把 `minmax(a,b)` 归约到上界，并用**最小值**计算 auto-fit 列数。
* **语义标签默认样式从未生效**：裸 `<h1>` 渲染成 12pt/400、`<b>` 不加粗、`<i>` 不斜体。
  根因是 `_DEFAULT_INHERITED` 里的可继承默认值让标签兜底分支变成死代码。
  改为注入一份**内置 UA 样式表**（`css.UA_STYLESHEET`），作者 CSS 仍在同特异性下胜出。

### Fixed — 样式表达力

* `grid-column: span N` 与显式 `grid-row` / `grid-column`：新增 `_place_grid_cells`，
  支持跨度、显式定位与行优先自动排布。
* `align-content`：网格行按 `start` / `center` / `end` / `space-between` 分布。
* `border-radius` 四角不同或椭圆（`50% / 20%`）：生成 `custGeom` 自定义几何；
  统一圆角仍走 `roundRect`（保持轻量）。
* `text-decoration: line-through` → `a:rPr@strike="sngStrike"`。
* `text-shadow` → run 级 `a:rPr/a:effectLst/a:outerShdw`，不再是形状阴影。
* `<ol>` → 原生 `a:buAutoNum`（支持 `start` 与罗马/字母方案），项目可自动重新编号。
* `aspect-ratio` 参与盒子高度推导。
* `height: N%` 改为按**包含块**解析（此前误用画布高度，定高卡片内算大一倍）。
* `transform: translateX(-50%)` 等百分比位移在布局后按自身宽高解析（居中定位可用）。
* `<sub>` / `<sup>` → `a:rPr@baseline` 原生基线偏移。
* SVG 标签与属性被 HTML 解析器小写化（`linearGradient` → `lineargradient`），
  导致渐变整图退化为 PNG：新增 `dom._restore_svg_case` 还原大小写。
* SVG `stroke-dasharray` → `a:prstDash` 预设虚线。
* `font-variant-numeric: tabular-nums` → `a:rPr@numFmt="tab"`。

### Fixed — 工具

* `tools/check_deck.py` 现在会把半透明图层（光斑、浅色底片）**合成**到下层再算对比度，
  并把渐变按色标平均后保留 alpha；此前把 14% 透明光斑当成白色背景，产生大量假警告。

### Changed

* 示例对比度调整：`aurora-launch` 与 `annual-review` 的页脚、引述署名提亮到 4.5:1 以上，
  装饰光斑降到 14%–20% alpha，使 `--strict` 全绿。

### Added

* `tests/test_gaps.py`：14 组、33 条回归用例，逐条对应上面每个修复。
* `docs/known-gaps.md`：改为"仍未解决"清单 + 已修复对照表。
* `README.en.md`：英文主页；`SECURITY.md`；`.github/ISSUE_TEMPLATE/`（bug / feature）；
  `MANIFEST.in`（sdist 带上文档、示例与截图）。

---

## [1.0.0] — 2026-11-03

首个公开版本。整条链路可用：HTML/CSS → 纯 Python 排版 → 原生可编辑 PPTX。

### Added

**引擎**

* `dom` / `css` / `values`：HTML 解析、样式表级联、长度/颜色/渐变/网格轨道解析。
* `metrics`：PIL/FreeType 真实字体度量；中文按全角度量断行。
* `layout`：块级流、Flexbox（方向/换行/间隙/伸缩/对齐）、CSS Grid（`repeat()`/`fr`/`auto` 混合轨道）、绝对定位与出血元素、内联行换行、原生表格（合并单元格、逐格边框）。
* `writer` / `xmlutil`：原生 DrawingML 写出——文本段落与运行、自选形状、渐变、阴影、分边边框、图片裁切、演讲者备注。
* `svgshape`：内联 SVG → 原生自定义几何形状；`<text>`/`<tspan>` 转原生文本框（`word_wrap=False`，不重折行）。
* `themes`：8 套预设（paper / noir / swiss / ocean / ember / mint / blueprint / risograph），同时写 CSS 变量与 PPTX 主题色。
* `preview` / `preview_html`：逐页 SVG 版面预览与单文件 HTML 预览页。

**工具**

* `tools/check_deck.py`：对比度、出血、整页位图、可编辑性检查，`--strict` 模式区分错误与提示。
* `tools/render_pptx.py`：逐页 PNG 渲染（复用单页 PPTX + LibreOffice，无需 PyMuPDF）。
* `tools/verify_editability.py`：核对 HTML 文本是否以段落形式全部进入 PPTX。
* `tools/bench.py`：批量构建示例并输出耗时与体积。

**示例**

* `aurora-launch`（6 页，深色发布会）
* `annual-review`（4 页，纸感经营复盘）
* `editorial-keynote`（4 页，出版感主题演讲）
* `ai-thinking-orchestration`（16 页课件，含 6 张内联 SVG 图表）

### Changed

* 文本框默认 `word_wrap = False`：PPTX 中不再二次折行，作者写的断点即交付的断点。
* 文本框宽度取自实测行宽 + 固定余量，避免 PIL/FreeType 与 Office 字形差异造成裁字。

### Fixed

* Grid 行高在跨行元素下塌陷为 0（改为两趟：先测行高，再以最终偏移重排）。
* SVG `<line>` 包围盒为零导致所有顶点塌到原点。
* SVG `<text>` 标签被丢弃。
* SVG 描边被重复缩放（`*0.75` 后又做 pt→EMU）。
* `shape.opacity` 未生效（现折算进填充/描边 alpha）。
* 圆角、`p:style` 主题泄漏、项目符号属性顺序、`#` 前缀破坏 DML 颜色等问题。

---

## 版本说明

* **主版本**：破坏性变更——HTML 支持范围收窄、输出结构变化、CLI 参数不兼容。
* **次版本**：新增 CSS 特性、新增写出对象类型、新增主题。
* **修订号**：bug 修复、文案与文档订正、性能优化。
