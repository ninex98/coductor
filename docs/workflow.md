# Workflow

Coductor 的阶段术语固定如下：

| Stage ID | 英文环节 | 中文环节 | 中文角色 |
|---|---|---|---|
| `intake` | Goal Intake | 目标受理 | 目标分析师 |
| `inspect` | Repository Inspection | 仓库勘察 | 仓库勘察员 |
| `specify` | Specification | 规格定案 | 规格分析师 |
| `plan` | Execution Planning | 执行规划 | 任务规划师 |
| `orchestrate` | Workflow Orchestration | 流程编排 | 流程编排器 |
| `execute` | Task Execution | 编码实施 | 实现工程师 |
| `integrate` | Change Integration | 变更集成 | 集成管理员 |
| `verify` | Quality Verification | 质量验证 | 验证工程师 |
| `repair` | Failure Repair | 问题修复 | 修复工程师 |
| `review` | Independent Review | 独立审查 | 独立审查员 |
| `deliver` | Evidence Delivery | 证据交付 | 交付管理员 |

当前实现支持 solo 单任务链路，以及由 `auto` 检测明确先后依赖后生成的顺序 pipeline。Pipeline 会按任务依赖拓扑顺序执行，例如先 dispatch `T001`，再 dispatch 依赖它的 `T002`。显式 `parallel` 会先验证 allowed paths 不重叠、contract 不在同批次交接，验证失败进入 `human_required`，验证通过后记录 merged tasks 与 conflicts。失败 Gate 会进入有限修复循环；同一失败指纹重复或达到最大修复次数后进入 `human_required`。

`resume` 当前通过 SQLite workflow checkpoint 恢复原 `run_id`、目标、执行模式、阶段状态和修复次数。恢复前会扫描 run 目录中的 Artifact 链路；若上游 hash、revision 或下游记录的 contract hash 不一致，流程进入 `human_required`，并在 checkpoint 中记录 `stale_artifacts`。链路有效时再继续可重放流程。

`workflow/graph.py` 已能构建最小 LangGraph `StateGraph`；后续会把各阶段副作用继续迁入薄节点，并接入 LangGraph 原生 SQLite saver。

Evidence delivery 是最终状态来源。即使独立 review 有 blocking finding，系统也会写入 `06_review.yaml`、`07_evidence.yaml` 和 `delivery-report.md`；此时 evidence 的 `final_status` 与 Artifact envelope status 都必须是 `human_required`。
