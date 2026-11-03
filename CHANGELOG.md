# Changelog

遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Planned

见 [`docs/roadmap.md`](docs/roadmap.md)。

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
