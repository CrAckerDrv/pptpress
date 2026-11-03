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

**做法**：新增 `c:chart` 写出层（`deckpress/charts.py`）。

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

## 阶段二 · CSS 覆盖补齐（P0）

按"常见页面实际用得上"排序，不做长尾：

| 属性 | 现状 | 计划 |
|---|---|---|
| `row-gap` / `column-gap` | 只有合并的 `gap` | 分离支持 |
| `aspect-ratio` | 无 | 参与盒子高度推导 |
| `min-height` / `max-height` | 部分 | 完整参与 flex/grid 分配 |
| `align-content` | 无 | grid 多行对齐 |
| `background-size: cover` + 位置 | 部分 | 完整 `object-fit` 语义 |
| `border-style: dashed/dotted` | 无 | 映射到 `a:prstDash` |
| `text-decoration: line-through` | 无 | 原生删除线 |
| `font-variant-numeric` | 无 | 数字等宽（对表格很关键） |
| `writing-mode` | 无 | 竖排（海报/竖版场景） |

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

## 阶段五 · 视觉能力（P2）

| 事项 | 说明 |
|---|---|
| SVG 滤镜/遮罩的近似 | `feGaussianBlur` → 原生阴影；`clipPath` → 裁剪形状；减少 PNG 回退 |
| 渐变类型补齐 | `conic-gradient`、多色标角度分布 |
| 形状组合 | 支持 `groupShape`，让一组图标可以整体移动 |
| 一稿多色 | 同一份 HTML 用两套变量构建深/浅两版（已可行，补 CLI 与文档） |

---

## 阶段六 · 生态（P2）

* **主题市场**：主题是一份 JSON（CSS 变量 + 主题色），可单独分发与合成。
* **骨架库**：把 `pattern-library.md` 的 12 种骨架做成可 `import` 的 HTML 片段。
* **编辑器预览**：本地 `deckpress preview --serve`，改 HTML 浏览器自动刷新
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
| 1.0（当前） | HTML/CSS → 原生可编辑 PPTX，4 份示例，校验工具链 |
| 1.1 | 原生图表（阶段一）+ gap 分离与 aspect-ratio（阶段二前两项） |
| 1.2 | 并行构建 + XML 直写（阶段三） |
| 2.0 | PPTX 导入（阶段四）；到此具备"往返"能力 |
| 2.x | 视觉能力与生态（阶段五、六） |

每个版本发布前必须满足：

```bash
python -m pytest tests -q
python tools/bench.py                      # 不得出现 > 1.5s 的单份构建
python tools/check_deck.py examples/*.pptx --strict   # 无 !
```
