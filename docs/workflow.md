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

当前实现支持 solo 单任务链路，以及由 `auto` 检测明确先后依赖后生成的顺序 pipeline。Pipeline 会按任务依赖拓扑顺序执行，例如先 dispatch `T001`，再 dispatch 依赖它的 `T002`。显式 `parallel` 会先验证 allowed paths 不重叠、contract 不在同批次交接，并检查依赖图、验收覆盖、上游 Artifact 和策略理由；验证失败进入 `human_required`。验证通过后默认仍要求计划审批，`03_execution_plan.yaml` 会记录 `approval.required: true`，CLI `approve` 会写入 `approved_by: cli`，随后 `resume` 从 `validate_execution_plan` 继续。执行时每批 ready tasks 会按 `workflow.max_parallel_workers` 在隔离 git worktree 并发运行，批次完成后再串行回放 patch 并写入 `04_integration.yaml` 的 merged tasks 与 conflicts。失败 Gate 会进入有限修复循环；同一失败指纹重复或达到最大修复次数后进入 `human_required`。

`resume` 当前通过 SQLite workflow checkpoint 恢复原 `run_id`、目标、执行模式、阶段状态和修复次数。恢复前会扫描 run 目录中的 Artifact 链路；若上游 hash、revision 或下游记录的 contract hash 不一致，流程进入 `human_required`，并在 checkpoint 中记录 `stale_artifacts`。链路有效且 checkpoint 中记录的 Artifact 都存在时，contextual LangGraph 会从 checkpoint stage 继续；若 checkpoint 缺少必要 Artifact，则从 `collect_goal` 重放，以保持固定 YAML 事实链完整。

CLI 可观测性分三层：`coductor status [RUN_ID]` 查看运行总览，`coductor status RUN_ID --json` 输出包含 run 表记录和 checkpoint 摘要的机器可读 JSON；`coductor logs RUN_ID --stage dispatch_tasks --tail 20 --json` 可按阶段过滤、截取最近事件并输出机器可读日志；`coductor explain RUN_ID` 读取 SQLite checkpoint 并显示 `current_stage`、`completed_task_ids`、`last_error` 和 `stale_artifacts`；`coductor artifacts RUN_ID` 在列出 YAML Artifact 前也会显示同一份 checkpoint 摘要，方便把固定文件产物和当前运行状态对齐。

控制命令不是任意状态覆盖：`pause` 和 `stop` 只接受 `running`；`approve` 只接受 `human_required`；`verify` 和 `review` 只接受 `ready_for_human_review` 或 `human_required`。对需要审批的 parallel plan，`approve` 会修改计划 Artifact 并把 checkpoint 推进到 `validate_execution_plan`；普通人工确认仍只记录控制事件。`verify` 会真实重跑质量门并更新 `05_gate_report.yaml`，`review` 会真实重跑独立审查和 evidence 交付。非法状态会返回可恢复错误，并保持原 run 状态不变。`resume` 遇到 `paused` 或 `stopped` run 时只返回当前状态，不会继续执行 LangGraph。

`RunService` 构建 contextual LangGraph 作为当前主编排器。阶段节点仍保持薄，具体领域逻辑继续放在 artifact writer、task execution、verification、repair、review delivery 等服务中；节点负责读取上游 Artifact、调用服务、记录固定 Artifact 路径和 checkpoint。`compile_workflow_graph` 支持传入 checkpointer，`langgraph-checkpoint-sqlite` 已作为目标依赖声明；后续重点是清理 Graph checkpoint 连接生命周期和更细粒度的节点级幂等恢复。

Evidence delivery 是最终状态来源。即使独立 review 有 blocking finding，系统也会写入 `06_review.yaml`、`07_evidence.yaml` 和 `delivery-report.md`；此时 evidence 的 `final_status` 与 Artifact envelope status 都必须是 `human_required`。Worker、Repairer 和 Reviewer 的 backend 调用会在对应 Artifact 的 `usage` 字段记录 duration/token 信息；没有真实 token usage 时使用本地估算并标记 `estimated: true`，最终由 `07_evidence.yaml` 的 `usage_summary` 和 delivery report 的 Run Metrics 汇总。
