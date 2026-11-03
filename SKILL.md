---
name: pptpress
description: >
  HTML-first presentation workflow that authors decks as HTML/CSS and exports a
  fully editable PPTX — native text runs, shapes, tables, vector icons and
  theme colours, never a flattened screenshot and never a locked template.
  Use when the user asks to create, generate, redesign, restyle, beautify or
  convert a presentation, deck, slide, PPT, PPTX, keynote, pitch, report deck or
  courseware; wants a web-page-style deck delivered as PowerPoint; or mentions
  pptpress, HTML→PPTX, or "editable slides".
metadata:
  version: "1.0.0"
  license: "MIT"
  entrypoint: "python -m pptpress build <deck.html> -o <deck.pptx>"
---

# PPT Press · HTML 排版，可编辑交付

一句话：**用 HTML/CSS 做设计，用纯 Python 计算排版，输出原生可编辑 PPTX。**
没有浏览器、没有截图、没有写死的母版——风格来自一份 CSS，内容来自你的文案。

---

## 0. 三条硬规则

1. **先有页面任务，再有版式。** 每页先写一句"读者看完能做什么"，写不出来就不排版。
2. **不写死模板。** 风格 = `:root` 变量 + 少量骨架 CSS。换气质只换一段 `<style>`，
   不复制母版、不套用别人的 PPT 文件。
3. **不允许整页图片。** 文本必须是文本运行、图标必须是形状、表格必须是表格。
   构建器只会栅格化"带滤镜/遮罩/文字"的极少数 SVG。

---

## 1. 环境

```powershell
python -m pip install -r requirements.txt   # python-pptx / lxml / tinycss2 / Pillow
python -m pptpress themes                  # 列出内置主题
```

依赖极少、全程离线：不调用浏览器、不联网、不读注册表。

| 组件 | 作用 |
|---|---|
| `tinycss2` | 解析样式表 |
| `lxml` | HTML 解析 |
| `Pillow` | 读取真实字体度量（换行精度） |
| `python-pptx` | 写入 PPTX |

---

## 2. 工作流（6 步）

### Step 1 · 确认交付契约

从用户原话中提取，缺一项就问一个问题，不要一次问五个：

| 字段 | 说明 | 缺失时默认 |
|---|---|---|
| 主题 | 讲什么 | 必须问 |
| 受众 | 谁看（决定信息密度） | 内部同事 |
| 页数 | 几页 | 8–12 页 |
| 气质 | 深色发布会 / 纸感复盘 / 出版演讲 / 瑞士培训 / 正式汇报 | 按受众推断 |
| 语言 | 中文 / 英文 / 混排 | 跟随用户 |
| 场景 | 投屏、打印、自阅 | 投屏 |

> ⛔ **Gate 1**：只有"主题不清"或"气质完全相反"才停下来确认；其余用默认值直接推进。

### Step 2 · 选择气质配方

读 [`docs/pattern-library.md`](docs/pattern-library.md)，从 5 个配方中选一个，
或按用户品牌色改写 `:root` 的 6 个变量。**不要**在这里引入任何外部模板文件。

### Step 3 · 写大纲（每页一句）

输出一个 10 行以内的清单，每行格式：

```
P03 | 一句话结论 | 证据/数据 | 用哪个骨架
```

骨架从 §7 的 12 种里选（cover / statement / two-col / cards-3 / kpi-row /
table / timeline / bars / quote / defs / section / closing）。

> ⛔ **Gate 2**：大纲给用户过目。这是唯一必须停下来确认的设计节点。

### Step 4 · 写 HTML

新建一个文件 `deck.html`，骨架见 [`docs/authoring-guide.md`](docs/authoring-guide.md)：

```html
<!doctype html>
<html data-size="16:9">
<head><meta charset="utf-8"><style>
  :root{ --ink:#111827; --paper:#FBFAF7; --brand:#C2410C; }
  .slide{ font-family:'Inter','Segoe UI','Microsoft YaHei',sans-serif;
          background:var(--paper); color:var(--ink); padding:56px 64px; }
  h1{ font-size:52px; line-height:1.12; margin:0 0 12px; }
  .lead{ font-size:18px; line-height:1.7; color:#5B6474; }
</style></head>
<body>
  <section class="slide">
    <h1>结论先行</h1>
    <p class="lead">一句话说清这页要让读者做什么。</p>
  </section>
  <aside class="notes">演讲者备注写这里，会进入 PowerPoint 备注栏。</aside>
</body>
</html>
```

写作纪律：

* 一页一个观点；需要三栏说明这其实是三页。
* 标题用 `<br>` 主动断行——PPTX 不会重新折行，你看到的断点就是交付的断点。
* 字号阶梯：标题 40–88px，正文 13–20px，标注 10–12px；正文不小于 12px。
* 强调只用 `<b>` / `<i>` / 一个强调色，不要三种一起上。
* 每个 `font-family` 都写真实回退：`'Inter','Segoe UI','Microsoft YaHei',sans-serif`。

### Step 5 · 构建 + 校验

```powershell
python -m pptpress build deck.html -o deck.pptx
python tools/check_deck.py deck.pptx          # 对比度 / 出血 / 可编辑性
python tools/render_pptx.py deck.pptx shots   # 需要逐页看图时
```

构建报告会列出：页数、对象数、耗时，以及每条 **内容溢出** 警告（含页码）。
溢出必须回 Step 4 改文案或改 CSS，**不允许**靠缩小字号藏进去。

> ⛔ **Gate 3**：把 `check_deck.py` 的 `!`（错误）清零；`~`（提示）可保留，
> 但要在交付说明里写一句为什么（例如页脚对比度是设计选择）。

### Step 6 · 交付

交付物固定三件：

1. `deck.pptx` — 可编辑演示文稿
2. `deck.html` — 可再次构建的源文件（**这是资产，不是过程文件**）
3. 一页说明：用了哪个配方、改哪几个变量换风格、哪些是刻意设计（如出血光斑）

---

## 3. 质量闸（交付前逐条核对）

| # | 闸门 | 判定 |
|---|---|---|
| 1 | 每页有唯一结论 | 标题就是一个判断句，不是名词短语 |
| 2 | 无溢出 | `build` 报告里没有 `content overflow` |
| 3 | 无整页位图 | `check_deck.py` 无 `page looks rasterised` |
| 4 | 文本可编辑 | PowerPoint 中双击任意文字可直接改字 |
| 5 | 表格仍是表格 | 单元格可直接输入数字 |
| 6 | 图标仍是形状 | 可选中、可改色、可缩放不糊 |
| 7 | 主题可换 | 改 `:root` 变量重建，全局生效 |
| 8 | 字号下限 | 正文 ≥ 12px、标注 ≥ 10px（投影可读） |
| 9 | 对比度 | 正文对背景 ≥ 4.5:1；标题 ≥ 3:1；页脚允许更低但须是有意为之 |
| 10 | 备注 | `<aside>` 覆盖每页要点，供演讲者视图使用 |

---

## 4. 设计契约

这四条是本技能的定位，也是交付物的验收前提：

| 契约 | 落地方式 | 违反时的表现 |
|---|---|---|
| 风格由 CSS 决定 | 一个 `.pptx` 母版都不需要；风格 = `:root` 变量 + 骨架 CSS | 换风格要重做版式 |
| 版面自由 | Grid / Flex / 绝对定位任意组合，不受槽位约束 | 内容一变就撑破 |
| 输出原生可编辑 | 文本是运行、形状是形状、表格是表格、图标是矢量 | 出现整页位图 |
| 纯离线构建 | `python-pptx` + 三个解析/度量库，无浏览器、无网络 | 构建秒级、字体不可控 |

---

## 5. 失败处理（按层修复）

| 现象 | 归属层 | 处理 |
|---|---|---|
| `content overflow` | 文案 / CSS | 删字、拆页、加大容器；不要缩小字号 |
| `icon could not be rasterised` | 图标 | 换成 `path`/`rect`/`circle` 子集内的图标 |
| 文字位置偏 1–2pt | 字体 | 把实际安装的字体放进 `font-family` 首位 |
| 字体被替换 | 字体 | 同上；构建器已按"第一个已安装字体"落字 |
| 形状颜色不对 | 主题 | 检查是否被 `lineRef/fillRef` 继承，构建器已剥离 `p:style` |
| 表格行高不对 | 表格 | 减少单元格内文字，或给 `th/td` 显式 `padding` |
| 旋转元素错位 | 变换 | 只对形状使用 `transform: rotate()`，不要对文本运行使用 |

---

## 6. 命令速查

```powershell
python -m pptpress build   deck.html -o deck.pptx        # 构建
python -m pptpress build   deck.html -o deck.pptx --json # 机器可读报告
python -m pptpress preview deck.html -o preview/         # SVG/HTML 版面预览
python -m pptpress check   deck.html                     # 只校验，不留文件
python -m pptpress themes                              # 内置主题
python -m pytest tests -q                                # 引擎自测
python tools/check_deck.py deck.pptx                     # 交付校验
python tools/render_pptx.py deck.pptx shots              # 逐页 PNG（需 LibreOffice）
```
