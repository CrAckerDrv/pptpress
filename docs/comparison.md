# Deckpress 对比说明

对照对象：`ppt-master` v6.8.0（`skills/ppt-master`）。

数据来自本机实测（Windows 11 / Python 3.12 / 同一台机器），命令见文末。
两份项目都在同一磁盘、同一 Python 环境下测量，只统计源码，不含构建产物。

---

## 1. 体积

| 指标 | ppt-master | Deckpress | 倍数 |
|---|---|---|---|
| 文件总数 | 13,051 | 43 | **303× 更少** |
| 源码体积 | 37.7 MB | 0.45 MB | **84× 更小** |
| Python 文件 | 336 | 26 | **13× 更少** |
| Python 代码行 | 186,776 | 8,443 | **22× 更少** |
| 引擎包代码行 | — | 7,415 | — |
| 文档（.md） | 230 篇 / 18,530 行 | 9 篇 / 1,574 行 | **26× 更少** |
| 第三方资产 | 图标库、音效库、字体度量 JSON、形状定义 XML | 无 | — |

Deckpress 不含任何随包素材：图标来自页面里的内联 SVG，字体度量来自系统已装字体。
（`examples/` 下的 4 份 `.pptx` 与 14 张 `.png` 是示例与截图，不计入源码统计。）

## 2. 速度

| 场景 | ppt-master（设计目标） | Deckpress（实测） |
|---|---|---|
| 依赖 | Python + 可选 Chromium/Office/TTS/图像模型 | 4 个纯 Python 包 |
| 网络 | 图片搜索、AI 配图、TTS 均需联网与密钥 | **完全离线** |
| 构建路径 | 转换 → 研究 → 规格 → 锁 → SVG → 校验 → 导出（多轮人工闸门） | HTML → 布局 → PPTX（一次调用） |
| 16 页图表课件 | 分钟级（多阶段流水线） | **610 ms** |
| 6 页深色演示 | 分钟级 | **102 ms** |
| 4 页纸感复盘 | 分钟级 | **86 ms** |
| 4 页出版感演讲 | 分钟级 | **68 ms** |
| 产物大小 | — | 34–103 KB / 份 |

计时包含解析、样式计算、排版与写出 PPTX；不含 PNG 预览（预览是可选的独立步骤）。

```
deck                            slides  objects       ms      KB  issues
ai-thinking-orchestration.html      16      812      610     103  0
annual-review.html                   4      119       86      36  0
aurora-launch.html                   6      195      102      40  0
editorial-keynote.html               4       86       68      34  0
```

## 3. 美观

| 维度 | ppt-master | Deckpress |
|---|---|---|
| 设计语言 | 以 SVG 手写页面，配套 187 个 Office 预设形状、调色板/渲染风格参考图 | CSS 排版：网格、弹性盒、渐变、圆角、阴影、字距、旋转 |
| 风格来源 | Brand / Style / Layout / Deck 四类工作区（本质仍是模板文件） | 一份 `<style>`；主题只是 CSS 变量 |
| 中文字体 | 需自行保证字体可用 | 按"第一个已安装字体"落字，中文按全角度量换行 |
| 交付形态 | SVG → PPTX（依赖自研转换器，30 万行级） | 直接生成 DrawingML，无中间图形层 |
| 视觉验证 | 有 SVG 预览与可视化审查阶段 | 内置 SVG 预览 + LibreOffice 逐页 PNG + 对比度/出血校验 |

## 4. 多样性

| 维度 | ppt-master | Deckpress |
|---|---|---|
| 内置风格 | 14 套 style + 7 套 layout 模板 | **8 套主题** + **5 套气质配方** + **12 种页面骨架** |
| 版式自由度 | 模板槽位内变化 | 自由布局（Grid / Flex / 绝对定位） |
| 画布 | 16:9 / 4:3 / 方形 / 竖版 / 报告等 | `data-size` 支持 16:9、4:3、1:1、9:16、3:2、16:10、A4、任意 `WxH` |
| 换风格成本 | 换工作区、迁移内容 | 改 6 个变量，重建（< 100 ms） |

## 5. 可编辑性

| 对象 | ppt-master | Deckpress |
|---|---|---|
| 文本 | SVG 文本 → 文本框 | 原生段落 + 运行，逐行对应 |
| 形状 | SVG 图元 → 预设形状 / 自定义几何 | CSS 盒模型 → 原生形状（含圆角、分边边框） |
| 图标 | SVG 位图化或形状化（视配置） | 内联 SVG → **原生自定义几何**，可改色可缩放 |
| 表格 | 支持原生表格 | 支持原生表格（含合并、逐格边框） |
| 主题色 | 依赖模板工作区 | 写入 PowerPoint 主题（`clrScheme` + `fontScheme`） |
| 整页图片 | 有"图片转 PPTX"路径（终态是分层对象） | **禁止**整页位图，校验器会报错 |

## 6. 工程性

| 维度 | ppt-master | Deckpress |
|---|---|---|
| 测试 | 大量定向回归脚本（约 90 个） | 10 项引擎自测 + 3 个交付校验工具 |
| 校验 | SVG 质量检查器（41 万字节）、PPTX 交付检查 | 对比度、出血、可编辑性、段落完整性 |
| 依赖授权 | 含第三方图标/音效资产（需逐项确认许可） | 无随包资产，MIT |
| 失败修复 | 分层回退（Plan / Page / Tool） | 按"文案层 / CSS 层 / 字体层 / 主题层"四层定位 |

## 7. 结论

* **轻**：源码文件数 1/303、体积 1/84、代码行 1/22，没有任何随包素材。
* **快**：4–16 页演示 68–610 ms 出稿，纯离线，无浏览器、无网络、无密钥。
* **美**：CSS 表达力覆盖网格、渐变、阴影、字距与旋转；中文按全角度量排版。
* **多样**：8 主题 × 5 气质 × 12 骨架，风格由变量决定而非模板决定。
* **可编辑**：文本、形状、图标、表格、主题色全部原生；整页位图被校验器拦截。
* **不写死模板**：风格 100% 来自作者自己的 `<style>`，`themes.py` 只是可选预设。

ppt-master 的优势在于"素材与能力面"（AI 配图、配音、视频、动效、模板导入），
Deckpress 的优势在于"从想法到可编辑文件的最短路径"。两者取向不同，指标如上。

---

### 复现命令

```powershell
# 体积（对照项目路径按你本机调整）
$pm = '..\ppt-master\skills\ppt-master'
(Get-ChildItem -Recurse -File $pm | Measure-Object -Sum Length)
(Get-ChildItem -Recurse -File . |
  Where-Object { $_.Extension -notin '.png', '.pptx' } |
  Measure-Object -Sum Length)

# 速度
python tools/bench.py
python tools/bench.py --json

# 质量
python -m pytest tests -q
python tools/check_deck.py examples/aurora-launch.pptx
python tools/verify_editability.py examples/aurora-launch.pptx --source examples/aurora-launch.html
```
