# ADR 0001: YAML As Stage Contract

## Status

Accepted

## Context

Coductor 需要让不同阶段可审计、可恢复、可验证。自由文本对话不适合作为下游关键事实来源。

## Decision

所有阶段正式输入和输出都使用 Pydantic 模型校验后写入 YAML Artifact Envelope。大型内容只保存路径、大小和 SHA-256。

## Consequences

阶段之间可以通过 hash 和 revision 追溯 lineage。代价是模型输出必须经过结构化解析和严格校验。
