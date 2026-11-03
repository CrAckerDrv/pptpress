# PPT Press · 版式与风格库

> 这里是“可换的气质”，不是“写死的模板”。
> 每个配方都由纯 CSS 构成，可以整体替换、局部混用，或直接改变量。

## 0. 选择方式

| 场景 | 气质 | 配方 | 示例 |
|---|---|---|---|
| 产品发布、融资、大会主舞台 | 深色、发光、克制的大字 | `noir stage` | `examples/aurora-launch.html` |
| 经营复盘、董事会、内部汇报 | 浅纸色、衬线标题、数据优先 | `editorial report` | `examples/annual-review.html` |
| 主题演讲、观点输出、长文改编 | 纯排版、极宽留白、出版感 | `editorial keynote` | `examples/editorial-keynote.html` |
| 培训、工作坊、教程 | 卡片节奏、编号明显 | `swiss workshop` | 见 §4 |
| 政府/国企正式汇报 | 红蓝稳重、表格密集 | `civic` | 见 §5 |

一份 CSS 决定整份演示的性格；换模板 = 换一段 `<style>`，而不是换一个母版。

---

## 1. `noir stage` · 发布会

```css
:root{
  --ink:#F2F5FF; --muted:#9AA6C4; --night:#080B14;
  --cyan:#4DE3D0; --violet:#8B7CFF; --line:rgba(255,255,255,.14);
}
.slide{
  font-family:'Inter','Segoe UI','Microsoft YaHei',sans-serif;
  background:linear-gradient(160deg,#080B14 0%,#101A33 55%,#0B1224 100%);
  color:var(--ink); padding:64px 72px;
}
h1{font-size:74px;line-height:1.05;letter-spacing:-1px;margin:20px 0 0}
h2{font-size:40px;line-height:1.15;letter-spacing:-.5px;margin:14px 0 10px}
.kicker{font-size:12px;letter-spacing:4px;text-transform:uppercase;color:var(--cyan)}
.lead{font-size:20px;line-height:1.7;color:var(--muted);margin:18px 0 0}
.card{background:rgba(255,255,255,.045);border:1px solid var(--line);
      border-radius:18px;padding:26px 24px}
```

要点：亮度只给强调色；卡片用 4.5% 白，而不是实心灰；背景用一条 160° 渐变，
再叠 1–2 个 radial 光斑（见 §6 光斑配方）。

## 2. `editorial report` · 经营复盘

```css
:root{
  --ink:#111827; --muted:#5B6474; --paper:#FBFAF7;
  --brand:#B4471F; --brand-soft:#F3E3D8; --navy:#1F3A5F; --line:#E5E0D6;
}
.slide{font-family:'Inter','Segoe UI','Microsoft YaHei',sans-serif;
       background:var(--paper); color:var(--ink); padding:56px 64px;
       font-variant-numeric:tabular-nums}
h1,h2{font-family:'Georgia','Songti SC',serif;letter-spacing:-.4px}
h1{font-size:56px;line-height:1.12}
.kpi .value{font-family:'Georgia','Songti SC',serif;font-size:34px}
th{background:var(--brand-soft);color:var(--brand);
   font-size:11.5px;letter-spacing:1.2px;text-transform:uppercase}
```

要点：衬线只用于标题与数字，正文保持无衬线；强调色只出现在小面积（表头、
KPI 变化值、时间轴），避免整页发红。

## 3. `editorial keynote` · 主题演讲

```css
.slide{font-family:'Georgia','Songti SC','SimSun',serif;background:#F6F4EF;color:#141414}
.display{font-size:88px;line-height:1.02;letter-spacing:-2px;margin:0}
.display em{font-style:italic;color:#C2410C}
.pull{font-size:44px;line-height:1.35;letter-spacing:-.6px}
.attrib{font-family:'Inter',Arial,sans-serif;font-size:11px;
        letter-spacing:2.4px;text-transform:uppercase;color:#6F6A62}
.rule{position:absolute;left:76px;right:76px;top:0;height:1px;background:#D9D3C7}
```

要点：一页一句话；标题允许 3–4 行；用 1px 细线和 folio（页码）制造出版感。

## 4. `swiss workshop` · 培训

```css
:root{--ink:#0A0A0A;--paper:#FFFFFF;--accent:#FF3B30;--muted:#6E6E6E;--line:#DADADA}
.slide{background:var(--paper);color:var(--ink);padding:52px 60px;
       font-family:'Helvetica Neue',Arial,'Microsoft YaHei',sans-serif}
h2{font-size:42px;line-height:1.1;letter-spacing:-1px}
.step{display:flex;gap:18px;padding:18px 0;border-top:1px solid var(--line)}
.step .n{width:46px;font-size:13px;letter-spacing:1.5px;color:var(--accent)}
```

要点：无圆角、无阴影、无渐变；只用黑、白、一个红；靠对齐与留白建立秩序。

## 5. `civic` · 正式汇报

```css
:root{--ink:#1B1B1B;--paper:#FFFFFF;--brand:#8C1D18;--navy:#1B3A6B;
      --line:#D8D8D8;--soft:#F2F5FA}
.slide{background:var(--paper);color:var(--ink);padding:50px 58px;
       font-family:'Microsoft YaHei','SimHei',sans-serif}
h2{font-size:30px;color:var(--brand);border-bottom:2px solid var(--brand);
   padding-bottom:10px;margin:0 0 18px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:var(--soft);border:1px solid var(--line)}
td{border:1px solid var(--line);padding:8px 10px}
```

要点：标题带下划色条、表格全框线、字号偏小但行距充足；正文避免斜体与英文缩写。

---

## 6. 可复用零件

**光斑（深色页增加层次）**
```css
.orb{position:absolute;right:-150px;top:-170px;width:520px;height:520px;
     border-radius:50%;
     background:radial-gradient(circle,rgba(139,124,255,.34) 0%,rgba(139,124,255,0) 68%)}
```
允许出血到画布外；这是少数值得使用绝对定位的地方。

**横向进度条（等价于图表）**
```css
.bar-row{display:flex;align-items:center;gap:14px;margin-bottom:14px}
.bar-label{width:132px;font-size:13px;color:var(--muted)}
.bar-track{flex:1;height:10px;border-radius:6px;background:rgba(255,255,255,.09)}
.bar-fill{height:10px;border-radius:6px;
          background:linear-gradient(90deg,var(--violet),var(--cyan))}
```

**时间轴**
```css
.steps{display:flex;gap:14px}
.step{flex:1;border-top:2px solid var(--violet);padding-top:14px}
```

**引用块**
```css
.callout{background:var(--navy);color:#F7F9FC;border-radius:6px;padding:26px 28px}
.callout .q{font-family:'Georgia','Songti SC',serif;font-size:22px;line-height:1.6;margin:0}
```

**封面右上角 chip**
```css
.chip{position:absolute;right:72px;top:64px;padding:9px 18px;border-radius:999px;
      background:rgba(77,227,208,.14);color:#4DE3D0;font-size:12px;letter-spacing:2px}
```

**多栏定义表**
```css
.defs{border-top:1px solid var(--line)}
.def{display:flex;gap:28px;padding:18px 0;border-bottom:1px solid var(--line)}
.def dt{width:170px;font-weight:700;margin:0}
.def dd{flex:1;color:var(--muted);margin:0}
```

---

## 7. 页面骨架清单（12 种）

| 骨架 | 用途 | 关键 CSS |
|---|---|---|
| `cover` | 封面：kicker + 大标题 + 一句 lead | `.kicker` `h1` `.lead` |
| `statement` | 单句观点页 | `.pull` + `.attrib` |
| `two-col` | 论点 / 证据 | `.two{grid-template-columns:1.05fr .95fr}` |
| `cards-3` | 三张并列卡片 | `.cards{grid-template-columns:repeat(3,1fr)}` |
| `kpi-row` | 4 个关键指标 | `.kpis{grid-template-columns:repeat(4,1fr)}` |
| `table` | 明细表 | `table.matrix` |
| `timeline` | 季度/阶段 | `.steps{display:flex}` |
| `bars` | 横向条形 | `.bar-row` |
| `quote` | 引用 + 出处 | `.callout .q` |
| `defs` | 术语/概念表 | `.def{display:flex}` |
| `section` | 章节分隔 | `justify-content:center;height:100%` |
| `closing` | 收尾与联系方式 | 大留白 + `.attrib` |

任何一页都不需要“模板文件”：选骨架、贴文案、调两个变量即可。
