# Coductor Architecture Diagrams

本目录保存 Coductor 架构图的可编辑源文件和可交付 PNG 导出图。

PNG 导出文件位于 [`exported/`](./exported/)，当前为 2x 高清版本，适合 README、文档页面和技术分享材料直接引用。源文件仍保留为 SVG / HTML，便于后续继续编辑。

## 系统架构总览

展示 Coductor 的整体架构边界：用户入口、控制平面、LangGraph 编排、确定性服务、执行与质量闭环，以及 YAML Artifact / SQLite / Git 事实层。

![Coductor 系统架构总览](./exported/coductor-system-overview.png)

- 源文件：[coductor-system-overview.svg](./coductor-system-overview.svg)
- 导出文件：[exported/coductor-system-overview.png](./exported/coductor-system-overview.png)

## 端到端运行流程

展示从 Goal 到 Evidence 的主运行路径，并把修复闭环、人工控制点和交付状态作为独立区域呈现，避免主线拥挤。

![Coductor 端到端运行流程](./exported/coductor-runtime-flow.png)

- 源文件：[coductor-runtime-flow.svg](./coductor-runtime-flow.svg)
- 导出文件：[exported/coductor-runtime-flow.png](./exported/coductor-runtime-flow.png)

## Artifact / State 流转

展示固定 YAML Artifact 链、修复证据链、SQLite 持久化、确定性保障机制和真实 RunStatus 状态边界。

![Coductor Artifact / State 流转](./exported/coductor-artifact-state-flow.png)

- 源文件：[coductor-artifact-state-flow.svg](./coductor-artifact-state-flow.svg)
- 导出文件：[exported/coductor-artifact-state-flow.png](./exported/coductor-artifact-state-flow.png)

## 导出说明

本次导出未使用 Mermaid 默认图作为最终成品。当前环境未发现 `rsvg-convert`、`inkscape` 或 `cairosvg`，因此使用 headless Chromium 从源 SVG 按 2x 设备像素比导出 PNG。导出尺寸为 `3600 x 2200`。
