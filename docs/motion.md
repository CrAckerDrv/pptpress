# 动效

PPT Press 的动效**不需要浏览器**：你在 HTML 上声明意图，引擎写出的是 PowerPoint
自己「动画窗格」里保存的那棵 `p:timing` 树。打开文件后可以直接在动画窗格里改时长、
换效果、删掉某一项——它是一份普通的 PPTX 动效，不是一段视频或一张 GIF。

---

## 一、两种动效

| 类型 | 属性位置 | 作用 | 写出的 XML |
|---|---|---|---|
| 页面转场 | `<section class="slide">` | 这一页怎么进 | `p:transition` |
| 元素动画 | 页面上任意元素 | 元素什么时候、以什么方式出现 | `p:timing` |

两者可以同时存在，也可以都不用——不加属性就是一份静态 deck。

---

## 二、页面转场

```html
<section class="slide" data-transition="push-left" data-transition-speed="med">
```

| 值 | 效果 | 方向 |
|---|---|---|
| `fade` | 淡入 | — |
| `push` / `push-left` | 推入 | 上 / 左 |
| `wipe` / `wipe-left` | 擦除 | 上 / 左 |
| `cover` | 覆盖 | 上 |
| `split` | 分割 | — |
| `cut` | 硬切 | — |

`data-transition-speed` 取 `slow` / `med` / `fast`，可省略。
写错的值会被**静默忽略**（不会生成非法 XML）。

**怎么选**：章节封面用 `push-left` 表示翻页，内容页用 `fade` 保持安静，
每页都用 `push` 会让人晕。编辑感强的 deck 用 `cut`，克制本身就是风格。

---

## 三、元素动画

```html
<div class="card" data-anim="fade-up" data-anim-delay="0.2">…</div>
```

| 属性 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `data-anim` | 见下表 | — | 效果名，必填 |
| `data-anim-delay` | 秒数或 `300ms` | `0` | 本效果开始前等待多久 |
| `data-anim-dur` | 秒数 | `0.5` | 效果持续时长 |
| `data-anim-trigger` | `click` / `with` / `after` | `click` | 与上一组的关系 |
| `data-anim-group` | 整数 | — | 同号的相邻效果合并为一次点击 |
| `data-anim-stagger` | 秒数 | `0.12` | 让子元素逐个出现（见第五节） |

### 效果名

| 进入 | 退出 | 强调 |
|---|---|---|
| `fade` | `fade-out` | `pulse` |
| `fade-up` / `fade-down` / `fade-left` / `fade-right` | `fly-out` | `spin` |
| `fly-left` / `fly-right` / `fly-up` / `fly-down` | `zoom-out` | |
| `zoom` / `wipe` / `wipe-left` / `wipe-up` | | |

---

## 四、点击节奏

三个 `trigger` 值决定演示者要按几次键：

```html
<div class="a" data-anim="fade-up"></div>                          <!-- 第 1 次点击 -->
<div class="b" data-anim="fade-up" data-anim-trigger="with"></div> <!-- 跟随上一组 -->
<div class="c" data-anim="fade-up" data-anim-trigger="after"
     data-anim-delay="0.3"></div>                                  <!-- 上一组结束后 0.3s -->
```

| 写法 | 演示者感受 |
|---|---|
| `click`（默认） | 每按一次，出一个 |
| `with` | 和上一组**同时**出现 |
| `after` | 上一组**播完之后**自动接着播 |

一个容器上的 `data-anim` 会动画**整个容器**（面板 + 里面的文字），
这是刻意的：卡片淡入而标签留在原地，看起来像故障。

---

## 五、逐个出现（`data-anim-stagger`）

最常用的动效写法，一行搞定一组卡片：

```html
<div class="grid2" data-anim="fade-up" data-anim-stagger="0.12">
  <div class="card">…</div>
  <div class="card">…</div>
  <div class="card">…</div>
</div>
```

结果：**演示者只按一次键**，三张卡片每隔 0.12 秒依次浮起。

* `data-anim-stagger="0.12"` —— 自定义间隔（秒）
* `data-anim-stagger`（不写值）—— 用默认 0.12s
* 只有 1 个子元素时不会拆分，退化为一次普通动画
* 不写 `data-anim-stagger` 时，整个容器作为一个整体出现

间隔的经验值：卡片 0.10–0.15s，列表项 0.06–0.10s。
超过 0.2s 会显得拖沓，整组都出来要等太久。

---

## 六、动画的粒度规则

引擎按**视觉单元**决定动画目标，不需要你自己标注：

| 你写的 | 被动画的对象 |
|---|---|
| `<div class="card">`（有背景、有文字） | 卡片面板 + 里面的所有文字 |
| `<li data-anim>` | 这一条列表项（含项目符号） |
| `<h1 data-anim>` | 标题文本框 |
| `<svg>` | 图形被拆成的全部矢量形状 |
| `<table data-anim>` | 整张表格 |

---

## 七、验证

```bash
python tools/check_deck.py deck.pptx
```

输出末尾会多一行：

```
  motion: 16 transitions, 15 animated slides, 249 effects, 13 clicks
```

* **effects** —— 被动画的形状数（一张卡片 = 面板 + 文字 = 2 个）
* **clicks** —— 演示者需要按的次数

改成 `--json` 可以看到每页的 `transition` / `effects` / `clicks`。

真实渲染验证（需要 LibreOffice）：

```bash
python tools/render_pptx.py deck.pptx shots   # 每页一张 PNG，确认定格画面正常
```

动效本身在 PNG 里看不出来，但可以确认**静态画面没有因为动效坏掉**，
并且文件能被正常打开、不触发 PowerPoint 的"修复"提示。

---

## 八、限制

* 不支持路径动画（`motion-path`）—— 没有编辑友好的对应物
* 不支持 `trigger="on-click-of"`（点某个对象触发）—— 只会增加误触
* 不写 `p:timing` 的幻灯片没有任何动效开销（字节数不变）

完整的属性清单见 [`authoring-guide.md`](authoring-guide.md)，
效果名在 `pptpress/animate.py` 的 `EFFECTS` 表里。
