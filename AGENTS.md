# Coductor Agent Rules

- 中文用户文档优先，代码标识符和 YAML 字段使用英文。
- 所有阶段正式交接必须写入 YAML Artifact，不使用自由文本作为下游事实来源。
- 完成状态由质量门、审查和 Evidence Bundle 决定，Agent 声称不具备状态决定权。
- 默认 Solo First。只有依赖边界清晰且契约冻结时才考虑 pipeline 或 parallel。
- Builder 只能写当前仓库或隔离工作区；Planner、Inspector、Reviewer 默认只读。
- 网络、远程 Git 写入、生产环境、Secrets 和破坏性迁移必须人工批准。
- 修复循环必须有边界，默认最多 2 次。
