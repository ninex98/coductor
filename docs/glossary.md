# Glossary

- **Coductor**：面向 AI Coding Agent 的确定性研发工作流引擎。
- **Artifact**：阶段之间的 YAML 交接契约。
- **Evidence Bundle**：最终证据包，包含 Gate、Review、Patch 引用和回滚说明。
- **Evidence Validation**：交付完整性检查，要求必需 Gate 通过、无阻塞审查且存在 patch evidence。
- **Gate**：由确定性命令产生的质量验证项。
- **Solo First**：默认用一个 Worker 完成紧密耦合任务。
- **Contract Before Parallelism**：并行前必须先冻结共享契约。
- **Human Required**：流程保留证据但需要人工介入，常见原因包括 gate 失败、stale artifact、路径冲突、blocking review 或 evidence 不完整。
- **Worker**：被 Backend 调用的 Coding Agent 执行单元。
