# 架构

一份 deck 从 HTML 到 PPTX 只经过一次数据流：

```
deck.html  →  节点树  →  计算样式  →  Box 树  →  DrawingML
            dom/css/values          layout     writer/xmlutil/svgshape
```

没有中间图形层、没有浏览器、没有临时图片（图标回退除外）。
每个阶段的结构都是显式的 Python 对象，因此可以被测试断言。

---

## 1. 坐标系统

| 阶段 | 单位 | 换算 |
|---|---|---|
| 作者写 CSS | px | 1280×720 px 画布 |
| 引擎内部 | **pt** | 1 px = 0.75 pt |
| 输出 | EMU | 1 pt = 12,700 EMU |

归一发生在 `values.py`：所有长度解析出来就是点。百分比不在此处解析——
它依赖包含块宽度，由 `layout.py` 在几何计算时惰性求值
（`Percent` 是 `float` 的子类，用来区分"100% 高度"与"1px 高度"）。

画布由 `data-size` 决定，`slides.slide_size()` 把它映射为 `(width_pt, height_pt)`：

| `data-size` | 画布 |
|---|---|
| `16:9` | 960×540 pt |
| `4:3` | 720×540 pt |
| `1:1` | 540×540 pt |
| `9:16` | 540×960 pt |
| `A4` | 595×842 pt |
| `1280x720` | 直接取值 ÷ 0.75 |

---

## 2. 数据结构

### 2.1 节点树（`dom.py`）

`Node` 包装一个 lxml 元素，补三样东西：`class_set`、`pseudo_element`、
`text_nodes`。文本节点被提升为 `TextNode`，带 `_order` 与 `child_nodes`，
让"文本 + `inline-block` 混排"能和普通盒子走同一套流式排版。

### 2.2 计算样式（`css.py` + `values.py`）

`css.Resolver` 做级联：特异性排序 → `!important` → 内联样式 → 继承属性。
结果是一个扁平的 `Style` 对象，字段全是最终值（已解析成点/颜色/枚举）。

自定义属性在 `:root` 上收集后放进 `resolver.variables`，`var(--x)` 在此时替换。
主题就是往 `variables` 里注入一组值——这也是"主题不是母版"的实现原因：
它只是变量，不是版式。

### 2.3 Box 树（`layout.py`）

```
Box
├─ rect: (x, y, w, h)          pt
├─ style: Style
├─ lines: [Line]               文本行（已断行，带 run 列表）
├─ children: [Box]
└─ extra: {bullet, nowrap, …}  写出阶段需要但样式里没有的信息
```

`Line` 里每个 `run` 是 `(text, Style, width_pt)`。**断行在排版阶段一次算完**，
写出阶段不再测量——这是"PPTX 不重折行"的前提。

`Box.walk()` 是唯一遍历入口，构建报告的对象数、校验器的溢出检查都用它。

### 2.4 写出（`writer.py` / `xmlutil.py` / `svgshape.py`）

`SlideWriter` 按 `Box` 的绘制顺序输出，每类盒子一个方法：

| Box 类型 | 写出函数 | 产物 |
|---|---|---|
| 有背景/边框 | `_shape` | `p:sp` 自选形状 |
| 有文本行 | `_text` | `p:sp` 文本框（一行一段落） |
| 表格 | `_table` | 原生 `a:tbl` |
| 图片 | `_picture` | `p:pic` |
| SVG | `svgshape.emit` | 自定义几何 + 文本框 |

`xmlutil.py` 只做"底层属性能否落地"：填充、描边、阴影、渐变、字体、项目符号。
属性顺序在 DrawingML 里是有语义的（例如项目符号必须 `buClr → buSzPct → buFont → buChar`），
所以这里的写入顺序不是风格问题，是正确性问题。

---

## 3. 排版算法要点

### 3.1 断行（`metrics.py` + `layout.py`）

1. 字体栈里**第一个已安装**的族被选中，同一个族名同时写进 PPTX。
2. 有字体文件时用 PIL/FreeType 取真实 advance width；缺字体时退回保守宽度表。
3. CJK 逐字测量（全角），Latin 用字体度量；行首禁则字符做简单 `_glue_punctuation`。
4. 行高取 `max(line-height × font-size, 自然行高)`，避免大字号被压扁。

### 3.2 Grid（两趟）

早期版本把行高在 measure 阶段直接累加，跨行元素会让后续行塌到 `y=0`。
现在固定两趟：

```
pass 1: 用最小行高测量每个格子的自然高度 → 求每行最大高度
pass 2: 以最终行偏移重新排版每个格子（此时百分比高度才是对的）
```

代价是每个格子排版两次，收益是行高正确且百分比可解析。

### 3.3 Flex

`_flex_row` 先按 `flex-grow` 分配主轴宽度，再逐个测量，最后按 `align-items`
做交叉轴定位。`flex:1` 与固定宽度可以混排；`stretch` 时子项高度取容器高度。

### 3.4 绝对定位与出血

`position:absolute` 相对最近定位祖先。`left+right` 或 `top+bottom` 成对出现时
拉伸盒子；只给一侧时收缩到内容宽度。超出画布的形状**不裁剪**——这是出血的实现方式，
校验器把它归类为"提示"而非"错误"。

---

## 4. 内联 SVG（`svgshape.py`）

SVG 是最容易退化成图片的地方，所以单独成层。

```
<svg viewBox> → 图元列表 → 每个图元 → p:sp（custGeom）
                      └── <text> → 独立文本框（word_wrap=False）
```

三个必须处理的边界：

* **包围盒**：`<line>` 天然零宽零高，必须显式算 bbox，否则所有顶点塌到原点。
* **归一化**：`custGeom` 的路径坐标是 `0..w`/`0..h` 的相对值，需要 epsilon 保护除零。
* **缩放**：`viewBox` → 目标框是统一缩放，描边宽度乘一次 `scale` 即可；
  再乘 0.75 会变成双倍粗（这是修过的 bug）。

`<text>` 的标签框宽度按 `_visual_len` 估算（CJK 1.0em、Latin 0.55em）× 1.9 + 6，
并关闭自动换行，否则 `85%` 会被折成两行。

仅当 SVG 使用滤镜、遮罩或 `clip-path` 时才回退到 PNG（`svgicon.py`，6× 超采样），
构建报告会逐条列出回退项。

---

## 5. 扩展点

| 想加什么 | 改哪里 | 别忘了 |
|---|---|---|
| 新 CSS 属性 | `values.py` → `css.py` → `layout.py` → `writer.py` | `tests/` 加最小用例 + `authoring-guide.md` 登记 |
| 新输出对象 | `writer.py` 加方法 + `xmlutil.py` 加原语 | `check_deck.py` 补可编辑性判据 |
| 新主题 | `themes.py` 加一份 JSON | 同时给 CSS 变量与 `clrScheme` |
| 新页面骨架 | `docs/pattern-library.md` | 附一段可直接粘贴的 HTML/CSS |
| 新校验规则 | `tools/check_deck.py` | 区分 `!`（错误）与 `~`（提示） |

**判断改动归哪一层**：如果现象是"字换行位置不对"，问题在 `metrics.py`；
"盒子位置不对"在 `layout.py`；"颜色/边框不对"在 `writer.py`/`xmlutil.py`。
跨层改通常意味着 bug 定位错了。

---

## 6. 性能

单份构建的耗时分布（16 页 / 812 对象 / 545 ms）：

| 阶段 | 耗时 | 说明 |
|---|---|---|
| parse | 4 ms | lxml 解析 |
| css | 3 ms | 级联 |
| layout | 114 ms | 断行 + 几何（主要成本是字体度量） |
| pptx | 424 ms | python-pptx 写盘（zip + XML 序列化） |

结论：**写盘比排版贵**。优化顺序是 XML 生成 → 字体度量缓存 → 并行分页。

字体度量已有进程内缓存（`FontBook`），所以多页 deck 的边际成本远低于首份。
