# Glossary

- **Coductor**：面向 AI Coding Agent 的确定性研发工作流引擎。
- **Artifact**：阶段之间的 YAML 交接契约。
- **Evidence Bundle**：最终证据包，包含 Gate、Review、Patch 引用和回滚说明。
- **Gate**：由确定性命令产生的质量验证项。
- **Solo First**：默认用一个 Worker 完成紧密耦合任务。
- **Contract Before Parallelism**：并行前必须先冻结共享契约。
- **Worker**：被 Backend 调用的 Coding Agent 执行单元。
