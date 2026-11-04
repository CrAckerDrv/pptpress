---
name: 渲染问题 / Bug
about: 某段 HTML/CSS 没有按预期变成 PPTX
title: ""
labels: bug
---

## 最小复现

贴上能复现的最小 HTML（10 行以内最好，不要整份 deck）：

```html
<!doctype html><html data-size="16:9">
<head><style>
  .slide { width:1280px; height:720px; padding:40px; background:#fff; }
</style></head>
<body><section class="slide">
  <!-- 出问题的那一段 -->
</section></body></html>
```

## 构建报告

```
python -m pptpress build case.html -o case.pptx --json
```

```json
// 把输出粘在这里
```

## 期望 vs 实际

| | 值 |
|---|---|
| 期望位置/尺寸 | `x=…, y=…, w=…, h=…`（点） |
| 实际位置/尺寸 | `x=…, y=…, w=…, h=…`（点） |
| 截图 | 可选，PNG 直接拖进来 |

## 环境

```
Python:      (python --version)
PPT Press:   (python -m pptpress --version 或 pip show pptpress)
系统:        (Windows 11 / macOS 14 / Ubuntu 24.04)
```

```
python -m pip list | Select-String "python-pptx|lxml|tinycss2|pillow"
python-pptx 1.x.x
lxml 6.x.x
tinycss2 1.x.x
pillow 12.x.x
```

## 交付前自检过吗

- [ ] `python tools/check_deck.py case.pptx` 输出里没有 `!`
- [ ] 已阅读 [`docs/known-gaps.md`](https://github.com/CrAckerDrv/pptpress/blob/main/docs/known-gaps.md)，
      确认这条不在已知缺口里
