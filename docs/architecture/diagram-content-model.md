# Coductor Diagram Content Model

本文档基于当前代码和 `docs/architecture/architecture_inventory.md`，对 Coductor 架构图、流程图和状态图做内容降噪。目标是先确定“图里该表达什么、图下该解释什么、哪些不要画”，再进入 SVG / HTML 视觉生成阶段。

## 1. 图表总原则

### 必须进入图中的内容

- Coductor 的一句话定位：本地运行的确定性 AI Coding 工作流引擎。
- 主线流程：`Goal -> Inspect -> Spec -> Plan -> Execute -> Verify -> Repair -> Review -> Deliver`。
- 关键分层：用户入口、控制平面、LangGraph 编排、执行后端、质量闭环、Artifact 层、SQLite 存储。
- 事实来源边界：YAML Artifact 是阶段交接事实来源，SQLite 只保存索引、事件、checkpoint 和锁。
- 质量闭环：quality gate、bounded repair、independent review、Evidence validation。
- 人工交互点：approval、human_required、resume、verify/review rerun。
- Planned 能力必须低强调展示，不能和已实现能力处于同等视觉权重。

### 放到图下说明的内容

- CLI 命令完整清单。
- SQLite 表字段细节。
- 每个 YAML Artifact 的完整字段。
- `RunService`、`TaskExecutionService`、`ReviewDeliveryService` 等类的内部方法。
- `GateRunner` 的具体命令执行细节，例如 `shlex.split()`、stdout/stderr 文件路径。
- resume 的详细复用规则和 artifact reuse 细节。
- release manifest 中的人工 Git 命令内容。

### 不适合展示的内容

- 所有 Python 文件或类之间的细粒度依赖图。
- 所有 CLI 子命令连到所有服务的全连接图。
- 所有 Artifact schema 字段。
- 测试文件矩阵。
- Roadmap 中当前代码未发现明确实现的功能，除非以 `Planned` 小标签出现。
- 外部 Codex CLI 输出结构化 YAML 的暗示。当前结构化 YAML 由 Coductor 本地写入。

### 当前已实现能力

- CLI：`init`、`run`、`resume`、`status`、`show`、`artifacts`、`logs`、`explain`、`approve`、`pause`、`stop`、`verify`、`review`、`report`、`release`、`serve`、`doctor`。
- 本地 Web Console：读取 artifact/log/report/doctor，执行 approve/pause/stop/resume/verify/review/release 控制。
- LangGraph `StateGraph` 主编排。
- Pydantic v2 Artifact Envelope。
- YAML Artifact 原子写入、hash、revision、history、inputs lineage、stale 校验。
- SQLite `runs`、`events`、`workflow_checkpoints`、`run_locks`。
- deterministic repository inspection、spec builder、planner、plan validator。
- solo、pipeline、parallel 执行策略；parallel 使用 worktree 和 patch 回放。
- `fake` backend 与 `codex_exec` backend。
- quality gates、failure fingerprint、bounded repair、independent review、Evidence Bundle、delivery report。
- release manifest 生成，且只给出本地/人工命令。

### Planned / 部分实现 / 不应画成已实现的能力

- `codex_sdk`：有 provider 边界，但当前为占位或 fallback 边界。
- 自动 PR 创建、远程 push、自动 merge：当前代码未发现明确实现。
- 自动 git commit：当前 release manifest 只列人工命令。
- 通知审批：当前代码未发现明确实现。
- SQLAlchemy storage：依赖声明存在，但当前 storage 实现使用标准库 `sqlite3`。
- release manifest schema：Pydantic 模型存在，但 schema map 未覆盖 `release_manifest`。
- model-assisted rich spec/plan：当前 spec/plan 主要是 deterministic 规则，未发现明确 LLM spec/plan 生成路径。
- Web Console SSE / 实时推送：当前代码是普通 HTTP + 前端轮询。
- 严格统一状态枚举：当前 DB 可能写入控制状态字符串，不完全等同 `RunStatus` enum。

## 2. 图 1：Coductor 总体架构概览

### 图中只展示的核心区域

| 区域 | 最多 3 个关键词 | 展示状态 |
| --- | --- | --- |
| 用户入口 | CLI、Web Console、Operator | 已实现 |
| 控制平面 | RunService、ReportService、run locks | 已实现 |
| LangGraph 编排 | StateGraph、WorkflowState、checkpoint | 已实现 |
| 核心主线 | Goal、Plan、Evidence | 已实现 |
| 执行层 | CodexExec、FakeBackend、target repo | 已实现 |
| 质量闭环 | Gate、Repair、Review | 已实现 |
| Artifact 层 | YAML、revision、lineage | 已实现 |
| 持久化层 | SQLite、events、locks | 已实现 |

`CodexSdkBackend` 只可作为执行层旁边的低强调 `Planned placeholder` 标签，不进入主路径。

### 主要流向

1. 用户通过 CLI 或 Web Console 进入控制平面。
2. 控制平面创建或恢复 run，并调用 LangGraph。
3. LangGraph 驱动主线阶段：`Goal -> Inspect -> Spec -> Plan -> Execute -> Verify -> Review -> Deliver`。
4. Execute 调用后端并作用于目标 Git 仓库。
5. Verify / Repair / Review 形成质量闭环。
6. 每个阶段写入 YAML Artifact；Artifact 进入 run directory。
7. SQLite 记录 run 状态、事件、checkpoint、锁。
8. Evidence validation 决定 `ready_for_human_review` 或 `human_required`。

### 不应该出现的细节

- 完整 CLI 命令列表。
- 每个 service 的方法名。
- 每个 Artifact 的完整字段。
- 每张 SQLite 表的字段。
- `workflow.nodes.*` 的全部文件名。
- `GateRunner` 的具体 subprocess 参数。
- release manifest 的具体 Git 命令。

### 右侧或底部辅助说明

- `YAML Artifact = 阶段事实来源`。
- `SQLite = 运行索引 / 事件 / checkpoint / lock`。
- `CodexExecBackend 返回普通文本摘要，结构化结果由 Coductor 写入 YAML`。
- `Release 不自动 push / PR，仅生成本地人工命令`。
- `Planned 使用虚线或灰色卡片`。

## 3. 图 2：Coductor 端到端运行流程

### 主流程阶段

| 阶段 | 图中短标签 | 主要 Artifact |
| --- | --- | --- |
| collect_goal | Goal | `00_goal.yaml` |
| inspect_repository | Inspect | `01_repository_snapshot.yaml` |
| draft_spec | Spec | `02_spec.yaml` |
| create_execution_plan | Plan | `03_execution_plan.yaml` |
| materialize_tasks / dispatch_tasks | Execute | `task.yaml`、`worker_request.yaml`、`worker_result.yaml`、`patch.diff` |
| integrate_changes | Integrate | `04_integration.yaml` |
| run_quality_gates | Verify | `05_gate_report.yaml` |
| repair_failure | Repair | `repair_request.yaml`、`repair_result.yaml`、`repair_result.patch` |
| run_independent_review | Review | `06_review.yaml` |
| prepare_evidence | Deliver | `07_evidence.yaml`、`delivery-report.md` |
| release command | Release | `08_release_manifest.yaml` |

主视觉中建议把 `materialize_tasks` 和 `dispatch_tasks` 合并成 `Execute`，避免流程过密。详细节点名可放图下注释。

### 关键分支

- Spec 需要审批：`Spec -> human_required -> approve -> resume -> Plan`。
- Plan 无效或 parallel 需要审批：`Plan -> human_required -> approve -> resume -> Execute`。
- Worker 失败或路径越界：`Execute -> human_required`。
- Gate 失败且未达到修复上限：`Verify -> Repair -> Verify`。
- Gate 失败且达到修复上限：继续进入 Evidence，但 Evidence 可能降级为 `human_required`。
- Blocking review 且 `repair_after_blocking_review=true`：`Review -> Repair -> Verify`。
- Evidence invalid：`Deliver -> human_required`。
- Evidence valid：`Deliver -> ready_for_human_review`。

### 修复循环

图中只展示一个闭环：

```text
Verify failed -> RepairService -> Verify again
```

小标签展示：

- `max_repair_attempts=2`
- `repairs/R###/*`
- `failure_fingerprint`

放到图下说明：

- repair prompt 的上下文组成。
- backend 是否支持 resume thread 的细节。
- repair result 与 patch 捕获的字段细节。

### 人工交互点

图中展示：

- `human_required`
- `approve`
- `resume`
- `verify / review rerun`

放到图下说明：

- `pause`、`stop` 只允许 running。
- `verify`、`review` 允许 `human_required` 或 `ready_for_human_review`。
- `resume` 对 paused/stopped 不继续执行，只返回当前状态。

### 不应该塞入的技术模块

- Backend Factory 细节。
- SQLite 表结构。
- Artifact Envelope 字段。
- Web Console API 路由。
- Pydantic model 列表。
- repository inspector 的扫描细节。

## 4. 图 3：Artifact / State 流转

### 固定 Artifact 链

建议主线只展示：

```text
00_goal
  -> 01_repository_snapshot
  -> 02_spec
  -> 03_execution_plan
  -> tasks/T###/*
  -> 04_integration
  -> 05_gate_report
  -> 06_review
  -> 07_evidence
  -> 08_release_manifest
```

其中 `08_release_manifest.yaml` 是 release 命令产物，不应暗示为自动远程发布。

`tasks/T###/*` 建议折叠成一个卡片，卡片内列：

- `task.yaml`
- `worker_request.yaml`
- `worker_result.yaml`

`patch.diff` 是非 YAML 证据文件，作为小标签挂在 `worker_result.yaml` 或 `07_evidence.yaml` 旁边。

### 修复 Artifact

修复区建议作为侧边闭环展示：

```text
05_gate_report failed
  -> repairs/R###/repair_request.yaml
  -> repairs/R###/repair_result.yaml
  -> repair_result.patch
  -> 05_gate_report rerun
```

图中小标签：

- `R###`
- `failure_fingerprint`
- `max 2`

图下说明：

- `repair_result.yaml` 复用 `WorkerResultData` 模型。
- repair patch 是 Evidence 的补充证据，但不是 Envelope YAML。

### 状态机

图中状态只展示：

```text
created
running
human_required
ready_for_human_review
paused
stopped
failed
```

控制状态字符串以小标签展示：

- `approved`
- `verification_requested`
- `review_requested`

说明中明确：

- 这些控制状态来自控制面写入，不是 `RunStatus` enum 成员。
- 后续如要严格状态机，可单独建 control action 表或统一 enum。

### SQLite 记录内容

图中展示 4 个表名即可：

- `runs`
- `events`
- `workflow_checkpoints`
- `run_locks`

图下说明：

- SQLite 不保存阶段业务事实。
- `runs.run_dir` 读取时需要路径边界校验。
- `events` 是 timeline。
- `workflow_checkpoints` 保存 `WorkflowState` JSON。
- `run_locks` 用于 resume/control 互斥。

### 确定性保障机制

图中适合用小标签展示：

- `content_sha256`
- `revision`
- `history`
- `inputs[]`
- `contract sha256`
- `stale_artifacts`
- `Evidence validation`

放到说明文字：

- hash 读取时重算。
- `inputs[]` 保存 path、revision、sha256。
- contract hash mismatch 会让恢复进入 `human_required`。
- Evidence final_status 由 gate、review、patch evidence 决定。

### 小标签 vs 说明文字

适合小标签：

- `YAML source of truth`
- `SQLite index only`
- `max repair: 2`
- `read-only review`
- `local release commands`
- `Planned`

放说明文字：

- 完整字段结构。
- 质量门日志路径。
- release manifest 的安全判断字段。
- resume 对前后半段 Artifact 的复用细节。
- parallel worktree 的 patch 回放算法。

## 5. 后续生成图表时的内容预算

为了避免视觉拥挤，建议使用以下预算：

| 图 | 主节点上限 | 主连线上限 | 侧边说明上限 |
| --- | ---: | ---: | ---: |
| 图 1 总体架构概览 | 8 个区域 + 1 条主线 | 10 条 | 5 条 |
| 图 2 端到端流程 | 10 个阶段 + 6 个分支 | 18 条 | 6 条 |
| 图 3 Artifact / State | 12 个 Artifact 节点 + 7 个状态 | 20 条 | 8 条 |

超过预算时，必须拆图或把细节移到说明文字。
