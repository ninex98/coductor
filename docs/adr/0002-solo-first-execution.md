# ADR 0002: Solo First Execution

## Status

Accepted

## Context

多 Agent 并行会带来上下文同步、契约漂移和集成成本。大多数紧密耦合代码修改更适合一个连续上下文完成。

## Decision

`auto` 模式默认生成 `solo` 策略。只有依赖边界清晰、写入范围互不冲突且并行收益明确时才选择 `parallel`。

## Consequences

MVP 更稳、更容易验证。后续并行能力必须先满足契约冻结和路径冲突检查。
