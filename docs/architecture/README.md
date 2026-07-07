# Coductor Architecture Diagrams

本目录保存 Coductor 架构图的可编辑源文件、生成脚本和 README 可直接引用的 PNG 导出图。

当前 canonical 图源为 HTML/CSS，不使用 Mermaid 默认图或 AI 生成位图作为最终成品。PNG 位于 [`exported/`](./exported/)，尺寸为 `3600 x 2200`，由同名 HTML 以 2x 设备像素比导出。

## 图 1：系统架构总览

展示 Coductor 的当前产品边界：CLI/Web 入口、RunService/LangGraph 控制面、执行后端、工具验证、目标满足评估、YAML Artifact、SQLite 和目标仓库。

![Coductor 系统架构总览](./exported/coductor-system-overview.png)

- 源文件：[coductor-system-overview.html](./coductor-system-overview.html)
- 导出文件：[exported/coductor-system-overview.png](./exported/coductor-system-overview.png)

## 图 2：端到端运行流程

展示从 Goal 到 Evidence 的主运行路径，并突出 `03_verification_plan.yaml`、`tool_runs/*`、`07_goal_satisfaction.yaml`、修复闭环、人工控制点和 Web Goal Loop 重跑动作。

![Coductor 端到端运行流程](./exported/coductor-runtime-flow.png)

- 源文件：[coductor-runtime-flow.html](./coductor-runtime-flow.html)
- 导出文件：[exported/coductor-runtime-flow.png](./exported/coductor-runtime-flow.png)

## 图 3：Artifact / State 流转

展示固定 YAML Artifact 链、`tool_runs/*` 外部证据、`repairs/R###` 修复证据链、RunStatus 状态边界、SQLite 持久化与 resume 防 stale 机制。

![Coductor Artifact / State 流转](./exported/coductor-artifact-state-flow.png)

- 源文件：[coductor-artifact-state-flow.html](./coductor-artifact-state-flow.html)
- 导出文件：[exported/coductor-artifact-state-flow.png](./exported/coductor-artifact-state-flow.png)

## 重新生成

```bash
.venv/bin/python docs/architecture/generate_diagrams.py --export-png
```

脚本会从三张 HTML/CSS 源图导出 PNG。当前导出使用 headless Chrome；在受限沙箱里可能需要允许启动本机 Chrome。

## 内容边界

- 已实现能力使用正常卡片样式。
- `codex_sdk` 等实验/占位能力使用低强调样式。
- 不把自动 PR、远程 push、自动 merge、生产 secrets 访问画成已实现能力。
- 不暗示 Codex CLI 直接输出 Coductor 结构化 YAML；结构化 Artifact 由 Coductor 本地写入。
