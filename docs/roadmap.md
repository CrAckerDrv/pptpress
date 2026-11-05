# 技术路线图

目标不变：**保持"打开即可编辑、不写死模板、纯离线、百毫秒级"这四条性质，把能力面向上补。**

判断一个特性该不该做的三条准则：

1. 它能否映射成**可编辑的 PowerPoint 对象**？不能 → 不做，或只做到"提示"级别。
2. 它是否引入**浏览器 / 网络 / 大型资产**？是 → 不做。
3. 它是否让**常见页面更省事**？不是 → 排到后面。

---

## 阶段一 · 图表可编辑（P0）

**问题**：当前示例里的折线图是用 SVG 路径拼出来的——视觉上是矢量、可改色，
但数据不携带语义。改一个点要改 HTML。

**做法**：新增 `c:chart` 写出层（`pptpress/charts.py`）。

```html
<div class="chart" data-chart="line" data-series="推理搜索,思维链,直接回答">
  <script type="application/json">
    {"categories":[1,2,4,8,16,32,64],
     "series":[[64.7,72.9,80.2,87.7,92.4,92.4,92.4], ...]}
  </script>
</div>
```

* 输出原生 `graphicFrame`，PowerPoint 里右键"编辑数据"可改数。
* 首期支持 `line` / `bar` / `column` / `pie` / `scatter`。
* CSS 只控制尺寸与位置；配色从 `:root` 变量映射到 `c:chart` 的系列色。
* SVG 路径仍保留为"无数据语义的装饰图形"的写法。

**验收**：`examples/ai-thinking-orchestration` 的 6 张图全部换成原生图表，
`check_deck.py` 能识别"图表页含可编辑数据"。

---

## 阶段二 · CSS 覆盖补齐（P1）

按"常见页面实际用得上"排序，不做长尾。
逐项现状来自实测（见 [`known-gaps.md`](known-gaps.md)），已完成项不再列入。

| 属性 | 现状 | 计划 |
|---|---|---|
| `::before` / `::after` 内容 | 匹配得到但内容不生成 | 徽章、编号、引号装饰需要它 |
| `calc()` / `clamp()` | 未解析，静默回落 | 简单算术即可覆盖多数用法 |
| `writing-mode` | 无槽位 | 竖排（海报/竖版场景） |
| `conic-gradient` | 丢弃 | 饼图式底色 |
| `background-size: contain` + 位置 | 解析了但图片填充未使用 | 完整 `object-fit` 语义 |
| 多背景层 | 只取第一层 | 叠加纹理 |
| `filter` / `clip-path` | 无原生对应 | 列入"明确不做" |

**1.1.0 已完成**（回归用例见 `tests/test_gaps.py`）：
`repeat(auto-fit,minmax())` 崩溃、语义标签默认样式、`grid-column: span N`、
显式 `grid-row`、`align-content`、四角/椭圆 `border-radius`、
`text-decoration: line-through`、`text-shadow`（run 级）、`<ol>` 原生编号、
`aspect-ratio`、百分比高度基准、`transform: translateX(-50%)`、
SVG 标签大小写、SVG `stroke-dasharray`、`<sub>`/`<sup>` 基线。

更早已完成：`row-gap`/`column-gap` 分离、`border-style: dashed/dotted`
（→ `a:prstDash`）、`text-align: justify`、负 `letter-spacing`、逐边边框、
`box-shadow`、`linear-gradient`、`transform: rotate()`、逐格边框的表格、
`rem`/`em`/`%`/`vw`/`vh` 字号。

**验收**：`docs/authoring-guide.md` 的支持表与实现一一对应，无"文档写了但没做"的条目。

---

## 阶段三 · 大 deck 的构建性能（P1）

**现状**：16 页 545 ms，其中写盘 424 ms。100 页量级会到 3 s 上下。

**做法**：

1. **并行分页**：`layout` 与 `SlideWriter.write` 都已是纯函数式的（每页独立），
   按 CPU 核数并行，主进程只负责拼装 `Presentation`。
2. **XML 直写**：绕开 python-pptx 的对象包装，直接拼 `p:sld` 片段
   （已有 `xmlutil.py` 作为基础）。
3. **字体度量缓存跨进程复用**（当前是进程内）。

**验收**：100 页 deck ≤ 800 ms；单页 ≤ 6 ms。

---

## 阶段四 · 双向与改造（P1）

**PPTX → HTML 导入**（`import_pptx`）：把一份既有 PPTX 拆成等价 HTML + CSS，
用于"改造老模板"而不是"重做"。

* 首期目标：文本、图片、表格、纯色/渐变形状；
* 明确不做：动画、SmartArt、嵌入视频（这些无法保真往返）；
* 双向一致性用往返测试保证：`pptx → html → pptx` 的对象数与文本内容必须一致。

---

## 阶段五 · 视觉与动效（P2）

| 事项 | 说明 |
|---|---|
| SVG 滤镜/遮罩的近似 | `feGaussianBlur` → 原生阴影；`clipPath` → 裁剪形状；减少 PNG 回退 |
| 渐变类型补齐 | `conic-gradient`、多色标角度分布 |
| 形状组合 | 支持 `groupShape`，让一组图标可以整体移动 |
| 一稿多色 | 同一份 HTML 用两套变量构建深/浅两版（已可行，补 CLI 与文档） |
| 更多动效 | 路径动画、按数据点入场、切换式强调（`p:animClr`） |
| 动效预设 | `data-anim="cascade"` 之类的语义别名，内部展开成一组 stagger |

**已完成（1.2.0）**：原生转场（8 种）与元素动画（18 种效果）、
点击节奏（`click`/`with`/`after`）、`data-anim-stagger` 逐个出现、
校验器动效统计。文档见 [`motion.md`](motion.md)。

---

## 阶段六 · 生态（P2）

* **主题市场**：主题是一份 JSON（CSS 变量 + 主题色），可单独分发与合成。
* **骨架库**：把 `pattern-library.md` 的 12 种骨架做成可 `import` 的 HTML 片段。
* **编辑器预览**：本地 `pptpress preview --serve`，改 HTML 浏览器自动刷新
  （预览走本仓库的 SVG 生成器，不引入浏览器渲染）。
* **VS Code 插件**：`data-size` 提示、变量补全、构建命令面板。

---

## 明确不做

| 事项 | 原因 |
|---|---|
| 无头浏览器截图转 PPTX | 产物不可编辑、构建秒级、字体不可控——与本项目目标相反 |
| 内置模板库 / 母版文件 | 违背"不写死模板"；风格应来自作者自己的 CSS |
| 联网取图 / 生成配图 | 破坏"纯离线"这一最强属性 |
| 动画与转场 | PPTX 动画模型复杂且与"静态版面正确性"无关，收益/成本比低 |
| 长尾 CSS（`float`、`columns`、`@keyframes`） | 无法映射为可编辑对象 |

---

## 版本节奏

| 版本 | 内容 |
|---|---|
| 1.0 | HTML/CSS → 原生可编辑 PPTX，4 份示例，校验工具链 |
| 1.1 | 修复 2 个 P0（`auto-fit` 崩溃、语义标签默认样式）+ 14 项样式缺口，测试 10 → 43 |
| **1.2（当前）** | 原生转场 + 元素动画 + `data-anim-stagger`；动效统计进入校验器；示例全部带动效，测试 43 → 94 |
| 1.3 | `::before`/`::after`、`calc()`/`clamp()`、表格 `rowspan` |
| 1.4 | 原生图表对象（阶段一） |
| 1.5 | 并行构建 + XML 直写（阶段三） |
| 2.0 | PPTX 导入（阶段四）；到此具备"往返"能力 |
| 2.x | 视觉与生态（阶段五、六） |

每个版本发布前必须满足：

```bash
python -m pytest tests -q
python tools/bench.py                      # 不得出现 > 1.5s 的单份构建
python tools/check_deck.py examples/*.pptx --strict   # 无 !
```
