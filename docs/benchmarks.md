# 实测数据

本文件只记录**本项目自身的可复现测量**：体积、构建耗时、产物尺寸与校验结果。
所有数字都可在本机用文末命令重新跑出来（Windows 11 / Python 3.12 / 单机）。

---

## 1. 体积

| 指标 | 数值 |
|---|---|
| 源码文件 | 51 |
| 源码体积 | 0.52 MB |
| 引擎模块 | 19 个 / 8,181 行 |
| 全部 Python 代码 | 27 个文件 / 9,492 行 |
| 文档 | 14 篇 / 2,267 行 |
| 随包第三方素材 | 0 |

"源码"指除 `examples/*.pptx` 与 `examples/shots/*.png` 之外的全部文件。
本项目不含图标库、音效库、字体度量 JSON 或形状定义 XML：
图标来自页面里的内联 SVG，字体度量来自系统已装字体，主题来自代码里的 8 组变量。

## 2. 构建耗时

```
deck                            slides  objects       ms      KB  issues
ai-thinking-orchestration.html      16      812      680     119  0
aurora-launch.html                   6      195      120      44  0
annual-review.html                   4      119       96      37  0
editorial-keynote.html               4       86       66      34  0
```

计时包含解析、样式计算、排版与写出 PPTX；不含 PNG 预览（预览是独立的可选步骤）。

单份 16 页课件的耗时拆分：

| 阶段 | 耗时 | 说明 |
|---|---|---|
| parse | 4 ms | lxml 解析 HTML |
| css | 3 ms | 级联与计算样式 |
| layout | 120 ms | 断行 + 几何（主要成本是字体度量） |
| pptx | 520 ms | python-pptx 写盘（zip + XML 序列化），含动效树 |

**结论**：写盘比排版贵。优化顺序是 XML 生成 → 字体度量缓存 → 并行分页，
所以路线图把"XML 直写 + 并行分页"排在性能项而不是排版项。

## 3. 产物

| 项目 | 数值 |
|---|---|
| 单份体积 | 34–103 KB |
| 16 页课件对象数 | 812 |
| ├─ 文本框 | 404 |
| ├─ 自选形状（卡片、色块、坐标轴） | 203 |
| ├─ 自由曲线形状（图表曲线） | 35 |
| ├─ 原生表格 | 4 |
| └─ 图片 | 0 |
| 可编辑字符 | 6,069 |
| 整页位图 | 0 |

## 4. 校验结果

```bash
python -m pytest tests -q                                  # 94 passed
python tools/check_deck.py examples/*.pptx --strict         # 0 错误 0 警告
python tools/verify_editability.py examples/ai-thinking-orchestration.pptx \
       --source examples/ai-thinking-orchestration.html     # 全部段落可编辑
```

`check_deck.py` 的判据：

| 检查 | 判据 | 结果 |
|---|---|---|
| 整页位图 | 单张图片面积 ≥ 页面 50% | `!` 错误 |
| 可编辑文本 | 每页至少一个非空文本框 | `!` 错误 |
| 文字对比度 | 正文 ≥ 4.5:1，标题 ≥ 3:1（半透明图层已合成） | `~` 提示 |
| 出血 | 形状越过页面边界 | `~` 提示（有意设计） |

四份示例在 `--strict` 下均为 0 错误 0 警告。

**动效覆盖**（`check_deck.py --json` 的 `motion` 字段）：

| 示例 | 转场 | 有动效的页 | 动效形状 | 点击次数 |
|---|---|---|---|---|
| ai-thinking-orchestration | 16 | 15 | 249 | 13 |
| aurora-launch | 6 | 4 | 57 | 4 |
| annual-review | 4 | 2 | 18 | 6 |
| editorial-keynote | 4 | 1 | 1 | 0 |

---

## 复现命令

```powershell
# 体积（排除示例产物与截图）
Get-ChildItem -Recurse -File . |
  Where-Object { $_.Extension -notin '.png', '.pptx' } |
  Measure-Object -Sum Length

# 速度
python tools/bench.py
python tools/bench.py --json

# 质量
python -m pytest tests -q
python tools/check_deck.py examples/aurora-launch.pptx --strict
python tools/verify_editability.py examples/aurora-launch.pptx --source examples/aurora-launch.html
```
