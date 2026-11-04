---
name: 功能请求 / Feature
about: 希望支持某个 CSS 特性、输出对象或工作流
title: ""
labels: enhancement
---

## 想做什么

一句话说清**你要做的版面**，而不是"支持 X 属性"：

> 例：想做三栏卡片，中间那张跨两列——现在跨列不生效。

## 现在会怎样

```
python -m pptpress build case.html -o case.pptx
```

```
（粘构建报告里的相关输出）
```

## 为什么这件事重要

- 这类版面在什么样的 deck 里出现？
- 现在有没有绕法？（多个 div 拼、绝对定位硬摆……）

## 是否能映射成可编辑对象

如果这是一个 CSS 特性，请说明它在 PowerPoint 里应该是什么：

| CSS | 期望的 PPTX 对象 |
|---|---|
| 例：`grid-column: span 2` | 形状宽度变成两列 |
| 例：`text-decoration: line-through` | 文本运行加删除线（`a:rPr@strike`） |

> 映射不到可编辑对象的特性通常不会实现——本项目的核心约束是"打开就能改"。

## 附加

- [ ] 我确认这不是 [`docs/known-gaps.md`](https://github.com/CrAckerDrv/pptpress/blob/main/docs/known-gaps.md) 里已列出的项
