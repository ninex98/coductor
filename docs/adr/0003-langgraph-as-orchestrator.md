# ADR 0003: LangGraph As Orchestrator

## Status

Accepted

## Context

Coductor 需要流程状态、条件路由、暂停恢复、重试和修复循环。这些职责不应塞进模型 Prompt。

## Decision

LangGraph 是 Workflow Runtime，节点保持薄，领域逻辑放在 Service。`run_id` 同时作为 LangGraph `thread_id`。

## Consequences

Phase 1 由 `RunService` 发起同等节点顺序，`WorkflowGraphRunner` 统一调度阶段副作用并写入固定 Artifact/checkpoint；后续把 runner 语义接入持久化 Checkpointer 时，不改变 Artifact 契约。
