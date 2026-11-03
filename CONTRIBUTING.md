# 贡献指南

Deckpress 是一个约 7.4k 行的纯 Python 引擎，目标只有一个：
**把 HTML/CSS 版面精确地变成可编辑的 PowerPoint 对象。**
改动请围绕这个目标，不要引入浏览器、不要引入位图回退。

---

## 1. 开发环境

```powershell
git clone https://github.com/<owner>/deckpress
cd deckpress
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest tests -q
```

要求 Python ≥ 3.9。日常自检三条命令：

```powershell
python -m pytest tests -q                          # 引擎自测（10 项）
python tools/bench.py                              # 全部示例构建 + 耗时
python -m deckpress build examples/aurora-launch.html -o build/aurora.pptx
python tools/check_deck.py build/aurora.pptx       # 交付校验
```

逐页 PNG 预览是可选的，需要本机装 LibreOffice：

```powershell
python tools/render_pptx.py build/aurora.pptx build/shots
```

---

## 2. 分层与责任

| 层 | 文件 | 只负责 |
|---|---|---|
| 解析 | `dom.py` `css.py` `values.py` | HTML → 节点树；样式表 → 计算样式；值 → 点 |
| 度量 | `metrics.py` | 用真实字体算字宽、行高、断行 |
| 排版 | `layout.py` `slides.py` | CSS 盒模型 → 带坐标的 Box 树 |
| 写出 | `writer.py` `xmlutil.py` `svgshape.py` | Box 树 → 原生 DrawingML |
| 外围 | `pipeline.py` `cli.py` `preview*.py` `themes.py` | 串联、命令行、预览、主题 |

**改哪一层，先看现象归属。** 例如"字被换行"是度量层，"卡片位置错"是排版层，
"形状没颜色"是写出层。跨层改要么是设计缺陷，要么是 bug 定位错了。

---

## 3. 三条不可回退的约束

1. **不允许整页位图。** 任何形式的"截图塞进 PPT"都会被
   `tools/check_deck.py` 判为错误，PR 不予合并。
2. **不允许引入浏览器/无头渲染。** 排版必须由本仓库的 Python 计算得出；
   浏览器渲染会让构建时间从百毫秒级跳到秒级，并引入不可控的字体差异。
3. **不允许写死模板。** 风格只能来自作者自己的 `<style>` 与 `:root` 变量；
   `themes.py` 是可选预设，不是母版。

---

## 4. 提交前检查

```powershell
python -m pytest tests -q
python tools/bench.py            # 确认没有明显变慢（阈值：单份 ≤ 1.5s）
python -m deckpress build examples/ai-thinking-orchestration.html -o build/deck.pptx
python tools/check_deck.py build/deck.pptx --strict
```

`--strict` 里的 `~` 是提示（例如有意设计的小字对比度），`!` 必须清零。

---

## 5. 加一个 CSS 特性

按顺序补四处，缺一处就会在别的页面上翻车：

1. `values.py` — 值解析与默认值；
2. `css.py` — 属性登记与继承规则（是否继承、初始值）；
3. `layout.py` — 几何影响；
4. `writer.py` / `xmlutil.py` — 写出为原生对象。

同时在 `tests/test_engine.py` 加一条最小用例，并在
`docs/authoring-guide.md` 的支持表里登记。

**不支持的特性请显式忽略并在 `css.py` 里注释原因**，不要静默降级成位图。

---

## 6. Bug 报告请附

* 最小复现 HTML（能用 5 行说清就不要贴整份 deck）
* `python -m deckpress build x.html -o x.pptx --json` 的输出
* 期望位置 vs 实际位置（点值，不是截图描述）
* 平台、Python 版本、`python -m pip list` 里四个依赖的版本

---

## 7. 提交信息

```
<层>: <一句话结论>

可选正文：现象 → 根因 → 修法（各一行）
```

示例：

```
layout: grid 行高在跨行元素下塌陷为 0

现象：三行卡片全部堆在 y=141.9
根因：measure 阶段用未定行高直接累加
修法：先测行高，再以最终偏移重排一次
```

---

## 8. 许可

提交即表示同意以 [MIT](LICENSE) 许可发布。
