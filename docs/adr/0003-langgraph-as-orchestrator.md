# ADR 0003: LangGraph As Orchestrator

## Status

Accepted

## Context

Coductor 需要流程状态、条件路由、暂停恢复、重试和修复循环。这些职责不应塞进模型 Prompt。

## Decision

LangGraph 是 Workflow Runtime，节点保持薄，领域逻辑放在 Service。`run_id` 同时作为 LangGraph `thread_id`。

## Consequences

Phase 1 由 `RunService` 构建 contextual LangGraph 作为主运行时。节点保持薄，只做 Artifact 输入读取、服务调用、状态补丁和 checkpoint 保存；固定 YAML Artifact 仍是下游事实来源。`compile_workflow_graph` 已支持传入 checkpointer，`langgraph-checkpoint-sqlite` 已作为目标依赖声明；直接访问 LangGraph graph 的路径使用 context manager 关闭 SQLite checkpoint 连接。前半段节点恢复时会复用已有 Artifact 并推进 checkpoint；后续扩展后半段幂等恢复时，也不改变 Artifact 契约。
