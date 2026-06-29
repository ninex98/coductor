# Coductor Architecture Inventory

本文件是为后续绘制 Coductor 架构图和业务流转图准备的代码审计清单。结论只基于当前仓库内实际代码、配置、文档和测试；不能从代码确认的内容会明确标注为“待确认”或“当前代码未发现明确实现”。

## 一句话定位

Coductor 是一个本地运行的确定性 AI Coding 工作流引擎：CLI 接收自然语言研发目标，程序化编排 Goal -> Inspect -> Spec -> Plan -> Execute -> Verify -> Repair -> Review -> Evidence，并把阶段交接事实写入固定 YAML Artifact，SQLite 只保存运行索引、事件、checkpoint 和锁。

确定性依据：

- `pyproject.toml` 的项目描述是 `Deterministic AI Coding Workflow Engine`。
- `README.md`、`docs/architecture.md`、`docs/workflow.md` 均把固定 YAML Artifact 和 Evidence Bundle 定义为完成状态来源。
- 当前主运行路径由 `src/coductor/cli.py` 调用 `src/coductor/services/run_service.py`，再构建 `src/coductor/workflow/graph.py` 中的 contextual LangGraph。

## 技术栈

| 类别 | 当前实现 |
| --- | --- |
| 语言 | Python 3.12+ |
| 包布局 | `src/coductor` src-layout package |
| CLI | Typer 优先，缺少 Typer 时 fallback 到 argparse |
| 控制台输出 | Rich 可用时使用 Rich，否则普通 stdout |
| 工作流编排 | LangGraph `StateGraph` |
| checkpoint | 自有 SQLite checkpoint 表 + 可选 `langgraph-checkpoint-sqlite` saver |
| 数据模型 | Pydantic v2 |
| Artifact 格式 | YAML，缺少 PyYAML 时 serializer 可退回 JSON 文本 |
| 本地存储 | Python 标准库 `sqlite3` |
| 质量门 | `subprocess.run(shlex.split(command))` |
| Web 控制台 | Python 标准库 `http.server.ThreadingHTTPServer` + 静态 HTML/CSS/JS |
| Git 能力 | 只读 Git inspection、patch diff、parallel worktree、release manifest 中的人工命令建议 |
| 测试/质量 | pytest、ruff、mypy 配置存在 |

注意：

- `pyproject.toml` 声明了 `sqlalchemy>=2.0`，但当前 `src/coductor/storage/database.py` 实际使用标准库 `sqlite3`，当前代码未发现 SQLAlchemy 存储实现。
- `codex_sdk` provider 有类和 factory 边界，但 `src/coductor/backends/codex_sdk.py` 当前是明确抛出 `BackendUnavailableError` 的占位实现。

## CLI 入口

入口定义：

- Console script：`pyproject.toml` 中 `coductor = "coductor.cli:main"`。
- 主文件：`src/coductor/cli.py`。
- `main()`：优先运行 Typer app；如果 Typer 不存在，走 `_argparse_main()`。

当前命令清单：

| 命令 | 作用 |
| --- | --- |
| `coductor` | 无子命令时显示中英文 quick start |
| `coductor --version` | 输出版本 |
| `coductor init [path]` | 在目标项目写入 `coductor.yaml`，创建 `.coductor/runs` 和 `.coductor/coductor.sqlite3` |
| `coductor run GOAL` | 创建 run，执行完整工作流 |
| `coductor run GOAL --dry-run` | 只生成 `00` 到 `03` 前置 Artifact，状态为 `human_required`，等待 `resume` |
| `coductor run GOAL --mode auto|solo|pipeline|parallel` | 指定执行模式 |
| `coductor run GOAL --backend fake|codex_sdk|codex_exec` | 覆盖配置中的 backend provider |
| `coductor status [RUN_ID]` | 查看指定或最新 run |
| `coductor status RUN_ID --json` | 输出 run row、checkpoint 摘要和 run_dir 校验结果 |
| `coductor status --watch` | 轮询状态 |
| `coductor show RUN_ID` | 输出 run row 和 YAML Artifact 列表 |
| `coductor resume RUN_ID` | 从 checkpoint 或 Artifact 链恢复 |
| `coductor report RUN_ID` | 输出 `delivery-report.md` |
| `coductor artifacts RUN_ID` | 列出 YAML Artifact，并显示 checkpoint 摘要 |
| `coductor logs RUN_ID` | 输出 SQLite events |
| `coductor logs RUN_ID --stage X --tail N --json` | 过滤/截断/JSON 输出事件 |
| `coductor explain RUN_ID` | 解释当前状态、checkpoint、下一步命令 |
| `coductor approve RUN_ID` | 审批需要人工确认的 spec 或 parallel plan |
| `coductor pause RUN_ID` | 将 running run 标记为 paused |
| `coductor stop RUN_ID` | 将 running run 标记为 stopped |
| `coductor verify RUN_ID` | 重新运行质量门并更新 `05_gate_report.yaml` |
| `coductor review RUN_ID` | 重新运行独立 review 和 evidence 交付 |
| `coductor release RUN_ID` | 基于 ready evidence 生成 `08_release_manifest.yaml` |
| `coductor serve` | 启动本地 Web 控制台，默认 `127.0.0.1:8765` |
| `coductor doctor` | 输出安装、后端、安全默认值、质量门等诊断 |

## 核心 package / module 清单

| 模块 | 主要文件 | 职责 |
| --- | --- | --- |
| CLI | `src/coductor/cli.py` | 命令入口、参数解析、进度输出、控制命令、doctor、serve 调用 |
| config | `src/coductor/config/models.py`, `loader.py` | `coductor.yaml` 模型、默认值、质量门发现、配置读写 |
| domain | `src/coductor/domain/enums.py`, `models.py`, `ids.py` | 运行状态、Artifact 类型、执行模式、ID、RunResult |
| artifacts | `src/coductor/artifacts/*` | Pydantic Artifact 模型、YAML 序列化、content hash、原子写、history、lineage 校验、JSON Schema 生成 |
| contracts | `src/coductor/contracts/*` | contract 文件 hash 与 `contracts/contracts.yml` manifest |
| repository | `src/coductor/repository/*` | Git inspection、Node/Python manifest 解析、worktree、integration diff |
| planning | `src/coductor/planning/*` | deterministic spec 派生、策略选择、plan 生成、plan validation |
| workflow | `src/coductor/workflow/*` | LangGraph 图、节点、state、runtime context、checkpoint 适配 |
| services | `src/coductor/services/*` | RunService 主编排、task execution、verification、repair、review/evidence、report、release |
| gates | `src/coductor/gates/*` | 质量门模型、命令运行、失败 fingerprint |
| backends | `src/coductor/backends/*` | CodingBackend 协议、fake backend、codex exec backend、codex SDK 边界、能力描述 |
| storage | `src/coductor/storage/database.py` | SQLite runs/events/workflow_checkpoints/run_locks |
| web | `src/coductor/web/*` | 本地 Web 控制台 API、read/control/doctor service、路径安全、静态资源 |
| prompts | `src/coductor/prompts/renderer.py` | worker/reviewer/repairer prompt 拼接 |
| security | `src/coductor/security.py` | 持久化文本和日志中的敏感信息脱敏 |

## 模块调用关系

当前主调用链：

```text
coductor.cli
  -> config.loader.load_config / discover_config
  -> services.run_service.RunService
    -> storage.database.Database
    -> workflow.checkpoint.WorkflowCheckpointStore
    -> workflow.langgraph_checkpoint.LangGraphCheckpointStore
    -> backends.factory.create_backend
    -> workflow.artifact_writer.WorkflowArtifactWriter
    -> services.task_execution_service.TaskExecutionService
    -> services.workflow_verification_service.WorkflowVerificationService
    -> services.repair_service.RepairService
    -> services.review_delivery_service.ReviewDeliveryService
    -> workflow.graph.build_workflow_graph(context=...)
      -> workflow.nodes.*
        -> artifacts.repository.ArtifactRepository
        -> repository.inspector / planning.planner / gates.runner / backends.*
```

控制面调用链：

```text
CLI control commands
  -> services.report_service.ReportService
  -> storage.database.Database locks
  -> CLI helper or service layer
```

```text
coductor serve
  -> web.server.serve_console
  -> web.app.LocalConsoleApp
    -> web.read_service.ConsoleReadService
    -> web.control_service.ConsoleControlService
    -> web.doctor_service.ConsoleDoctorService
      -> same Database / ReportService / RunService / ReleaseService helpers
```

## LangGraph 工作流相关模块

| 文件 | 职责 |
| --- | --- |
| `workflow/state.py` | `WorkflowState`，包含 `run_id`、`status`、`current_stage`、`repair_attempts`、`artifacts`、`completed_task_ids`、`stale_artifacts` 等 |
| `workflow/graph.py` | 定义 `WORKFLOW_NODES`、`build_workflow_graph()`、条件路由、contextual 节点包装、`compile_workflow_graph()` |
| `workflow/runtime.py` | `WorkflowRuntimeContext`，把 ArtifactRepository、writer、checkpoint、services 注入节点 |
| `workflow/nodes/*.py` | 每个阶段的薄节点，负责读上游 Artifact、调用 service、更新 state 和 checkpoint |
| `workflow/checkpoint.py` | 自有 SQLite workflow checkpoint 存取 |
| `workflow/langgraph_checkpoint.py` | `langgraph-checkpoint-sqlite` 适配；不可用时返回 `None` |
| `workflow/graph_runner.py` | 保留的分段 runner/helper；有测试覆盖，但当前文档和主路径均指向 contextual LangGraph |

工作流节点顺序：

```text
collect_goal
inspect_repository
draft_spec
validate_spec
create_execution_plan
validate_execution_plan
materialize_tasks
dispatch_tasks
integrate_changes
run_quality_gates
repair_failure
run_independent_review
prepare_evidence
```

条件路由：

- `validate_execution_plan` 后，如果状态是 `human_required`，结束；否则进入 `materialize_tasks`。
- `dispatch_tasks` 后，如果 worker 失败导致 `human_required`，结束；否则进入 `integrate_changes`。
- `run_quality_gates` 后：
  - 已经 `human_required`：结束。
  - gate passed：进入 `run_independent_review`。
  - gate failed 且修复次数未达到上限：进入 `repair_failure`。
  - gate failed 且达到上限：进入 `prepare_evidence`，Evidence 会降级。
- `run_independent_review` 后默认进入 `prepare_evidence`；若 `workflow.repair_after_blocking_review=true` 且有 blocking review、修复次数未达到上限，则进入 `repair_failure`。

## Pydantic 数据模型

主要模型文件：`src/coductor/artifacts/models.py`。

模型分层：

- 通用 Envelope：`ArtifactEnvelope[T]`、`Producer`、`ArtifactInput`、`ArtifactMetadata`。
- 输入/快照/规格/计划：`GoalData`、`RepositorySnapshotData`、`SpecificationData`、`ExecutionPlanData`。
- 任务执行：`PlanTask`、`TaskData`、`WorkerRequestData`、`WorkerResultData`、`FileReference`、`WorkerUsage`。
- 验证/修复/审查/证据：`IntegrationData`、`GateReportData`、`RepairRequestData`、`ReviewReportData`、`EvidenceBundleData`。
- 发布：`ReleaseManifestData`、`ReleaseGitState`、`ReleaseSafety`。

当前 schemas：

- `schemas/*.schema.json` 由 `src/coductor/artifacts/schema.py` 和 `scripts/generate_schemas.py` 从 Pydantic 模型生成。
- 当前 schema map 包括 `goal` 到 `evidence_bundle`，不包括 `release_manifest`。这是当前代码事实；是否需要为 release manifest 生成 schema 待确认。

## YAML Artifact 实现

Artifact 落盘实现：

- 写入入口：`ArtifactRepository.write()`。
- 写入方式：设置 `metadata.content_sha256`，写临时文件，再 `os.replace()` 原子替换。
- 历史：每次写入复制到 `history/<path>.revN.yaml`。
- revision：`write_next_revision()` 会读取当前 artifact 并把 revision 加 1。
- 读取：`ArtifactRepository.read()` 会重新计算 content hash，不匹配则抛错。
- lineage：每个下游 Artifact 的 `inputs` 保存上游 path、revision、sha256。
- stale 校验：`ArtifactLineageValidator.validate_inputs()` 校验上游 revision/hash；`TaskData.contracts` 还会校验 contract 文件 sha256。

当前固定 Artifact 类型与作用：

| 文件 | `artifact_type` | 作用 |
| --- | --- | --- |
| `00_goal.yaml` | `goal` | 用户目标、原始请求、请求执行模式 |
| `01_repository_snapshot.yaml` | `repository_snapshot` | Git commit、dirty 状态、语言/框架/manifest/命令/文档/风险 |
| `02_spec.yaml` | `specification` | 目标规格、范围、约束、验收标准、风险和审批 |
| `03_execution_plan.yaml` | `execution_plan` | 执行策略、任务 DAG、allowed/forbidden paths、质量门、审批和 validation |
| `tasks/<task-id>/task.yaml` | `task` | 单个 worker 的任务契约和边界 |
| `tasks/<task-id>/worker_request.yaml` | `worker_request` | backend request、sandbox、workspace、prompt template、context artifacts |
| `tasks/<task-id>/worker_result.yaml` | `worker_result` | worker 摘要、读写文件、命令、patch 引用、usage、exit reason |
| `tasks/<task-id>/patch.diff` | 非 YAML | 真实 diff 或 no-diff 标记，Evidence 的 patch evidence 来源 |
| `contracts/contracts.yml` | 非 Envelope YAML | contract manifest，记录 path/kind/sha256/producer task |
| `contracts/generated.schema.json` | 非 YAML | pipeline contract authoring 默认生成的 JSON schema 占位/契约文件 |
| `04_integration.yaml` | `integration` | solo skipped，pipeline/parallel merged tasks、conflicts、worktree diffs |
| `05_gate_report.yaml` | `gate_report` | 质量门执行结果、stdout/stderr log 路径、failure fingerprint、下一步 |
| `repairs/R###/repair_request.yaml` | `repair_request` | 修复目标、失败 gate、fingerprint、边界、resume thread |
| `repairs/R###/repair_result.yaml` | `repair_result` | 修复 worker 结果，数据模型复用 `WorkerResultData` |
| `repairs/R###/repair_result.patch` | 非 YAML | 修复 diff |
| `06_review.yaml` | `review_report` | 独立 reviewer 结果、finding、blocking 数量、verdict、usage |
| `07_evidence.yaml` | `evidence_bundle` | 最终状态、gate/review summary、usage、evidence files、rollback、PR 信息 |
| `delivery-report.md` | Markdown | 面向人的交付报告，从 Evidence 生成 |
| `08_release_manifest.yaml` | `release_manifest` | 本地发布清单、Git 状态、安全判断、人工命令 |

## SQLite / storage 层

存储文件：

- 项目本地：`.coductor/coductor.sqlite3`。
- 代码：`src/coductor/storage/database.py`。

表：

| 表 | 用途 |
| --- | --- |
| `runs` | `run_id`、`status`、`run_dir`、`updated_at` |
| `events` | run timeline，包含 stage、message、created_at |
| `workflow_checkpoints` | `WorkflowState` JSON |
| `run_locks` | 控制命令/resume 的互斥锁，支持 stale lock 释放 |

边界：

- SQLite 不保存阶段业务事实；阶段事实在 YAML Artifact。
- `ReportService`、CLI 和 Web read service 都会校验 `run_dir` 必须等于 `.coductor/runs/<run_id>`，避免 DB 行被篡改后读取外部路径。

## Codex backend / executor 层

Backend 协议：

- `src/coductor/backends/base.py` 定义 `CodingBackend`、`WorkerRequest`、`WorkerHandle`、`WorkerResult`。

当前 provider：

| provider | 当前状态 |
| --- | --- |
| `fake` | 已实现，用于离线 demo 和测试，会写 `coductor_fake_output_*.txt` 并返回成功结果 |
| `codex_exec` | 已实现，默认真实后端；通过 `subprocess.run()` 执行 `codex exec --sandbox <mode> --skip-git-repo-check -`，prompt 走 stdin |
| `codex_sdk` | 有边界但当前为占位；直接使用会抛 `BackendUnavailableError`，factory 可在 SDK 不可用且 fallback 为 `codex_exec` 时降级 |

重要边界：

- Codex CLI 输出普通文本摘要即可；`worker_result.yaml`、`review.yaml`、`gate_report.yaml`、`evidence.yaml` 等固定结构由 Coductor 本地写入。
- 当前 `CodexExecBackend.build_command()` 有 `_schema_path()` helper，但命令实际不使用 `--output-schema` 或 JSON/schema 模式。
- `BackendCapability` 用于 doctor 和 repair 是否可 resume thread 的判断。

## Git / verify / repair / review 能力

Git：

- `repository/git.py` 只读获取当前 commit 和 dirty 状态。
- `TaskExecutionService.workspace_diff()` 使用 `git diff --binary` 和 untracked file diff 捕获 patch。
- parallel 且存在 `.git` 时，`WorktreeManager` 使用 `git worktree add/remove` 为任务创建隔离工作区，并用 `git apply --3way` 回放 patch。
- release 不自动 commit/push/PR，只生成人工命令建议。

Verify：

- `GateRunner` 从配置读取质量门命令。
- 命令通过 `shlex.split()` 执行，不使用 `shell=True`。
- stdout/stderr 写入 run 目录 `logs/*.log`。
- 失败时生成 `failure_fingerprint`。

Repair：

- gate 失败且未达到 `workflow.max_repair_attempts` 时进入 `repair_failure`。
- `RepairService` 写 `repair_request.yaml`，调用 backend 的 repairer，生成 `repair_result.patch` 和 `repair_result.yaml`。
- 默认最大修复次数来自配置，默认 2。
- 如果 backend capability 支持 resume thread，repair 会记录 builder thread id；当前 `codex_exec` capability 是否支持由 `backends/capabilities.py` 决定，具体实际恢复能力需结合 provider 实现确认。

Review：

- `ReviewDeliveryService.review()` 以 read-only sandbox 启动 reviewer。
- reviewer prompt 包含 `02_spec.yaml`、`05_gate_report.yaml` 和已完成 task patch。
- review summary parser 识别 `Verdict:`、`Blocking:`、`Finding:` 行；若 blocking 或 verdict fail，则 `requires_repair=true`。

Evidence：

- `EvidenceService.build()` 汇总 gate、review、patch evidence 和 usage。
- 只有必需 gate 无失败、review 无 blocking finding、且至少存在一个真实 patch evidence 时，`final_status` 才保持 `ready_for_human_review`。
- 缺 patch、patch 无变化、gate 失败或 blocking review 都会让 Evidence validation invalid，并把 final_status 改为 `human_required`。

Release：

- `ReleaseService.create_manifest()` 只生成 `08_release_manifest.yaml` 和本地/人工命令。
- `remote_actions_allowed=false` 固定体现当前安全边界。
- 当前代码未发现自动 PR 创建、远程 push、自动 merge 的实现。

## 配置文件与运行目录结构

配置文件：

- `coductor.yaml`：当前项目配置。
- `coductor.example.yaml`：示例配置。
- `pyproject.toml`：包、依赖、测试、ruff、mypy 配置。
- `schemas/*.schema.json`：Artifact JSON Schema。

`CoductorConfig` 主要配置：

- `project`: name/root/default_branch。
- `backend`: provider/model/reasoning_effort/fallback。
- `workflow`: default_mode、max_repair_attempts、max_parallel_workers、require_spec_approval、require_plan_approval_for_parallel、repair_after_blocking_review。
- `permissions`: network/git push/PR 默认关闭，protected paths 默认包括 `.env*`、`**/secrets/**`、`**/production/**`。
- `repository.ignore`: `.git/**`、`.coductor/**`、`node_modules/**`、`.venv/**`、`vendor/**`。
- `quality_gates`: gate id/stage/command/required/timeout。
- `budgets`: max_run_minutes、max_worker_turns、max_repair_attempts。

运行目录：

```text
.coductor/
├── coductor.sqlite3
├── runs/
│   └── <run-id>/
│       ├── 00_goal.yaml
│       ├── 01_repository_snapshot.yaml
│       ├── 02_spec.yaml
│       ├── 03_execution_plan.yaml
│       ├── 04_integration.yaml
│       ├── 05_gate_report.yaml
│       ├── 06_review.yaml
│       ├── 07_evidence.yaml
│       ├── 08_release_manifest.yaml
│       ├── delivery-report.md
│       ├── contracts/
│       ├── history/
│       ├── logs/
│       ├── repairs/
│       └── tasks/<task-id>/
└── worktrees/<run-id>/<task-id>/   # parallel git worktree，执行后移除
```

## 当前主流程

从用户输入 goal 到最终交付：

1. 用户运行 `coductor run "..."`。
2. CLI 读取 `coductor.yaml`，可按 `--backend` 覆盖 provider。
3. `RunService.run()` 创建 `run_id` 和 `.coductor/runs/<run-id>`。
4. 初始化 `WorkflowState(status=running,current_stage=collect_goal)`。
5. `RunService` 保存 checkpoint 和初始事件，构建 `WorkflowRuntimeContext`。
6. LangGraph 从 `collect_goal` 开始执行：
   - 写 `00_goal.yaml`。
   - 仓库扫描写 `01_repository_snapshot.yaml`。
   - deterministic spec 派生写 `02_spec.yaml`。
   - planner 生成 `03_execution_plan.yaml`。
7. 若 spec 或 plan 需要审批，状态进入 `human_required`，等待 `coductor approve` + `coductor resume`。
8. `materialize_tasks` 和 `dispatch_tasks` 执行计划任务：
   - 写 task 和 worker request。
   - 调 backend。
   - 捕获 patch。
   - 写 worker result。
   - pipeline 按依赖顺序串行；parallel 在审批后按 ready batch 并发，并串行 apply patch。
9. `integrate_changes` 写 `04_integration.yaml`。
10. `run_quality_gates` 运行配置中的质量门并写 `05_gate_report.yaml`。
11. gate 失败且未达上限时进入 `repair_failure`，写 repair request/result，然后回到 gate。
12. gate 通过后进入 `run_independent_review`，写 `06_review.yaml`。
13. `prepare_evidence` 写 `07_evidence.yaml` 和 `delivery-report.md`。
14. `RunService` 根据最终 `WorkflowState.status` 更新 SQLite `runs` 表。
15. 用户可运行 `report`、`artifacts`、`logs`、`release` 或打开 `serve` 控制台。

## 关键状态流转

`RunStatus` enum：

- `created`
- `running`
- `human_required`
- `ready_for_human_review`
- `paused`
- `stopped`
- `failed`

实际 DB 中还可能出现控制面字符串：

- `approved`
- `verification_requested`
- `review_requested`

这些控制状态来自 `ReportService.CONTROL_STATUS`，不是 `RunStatus` enum 成员。当前代码中部分命令会直接写入这些字符串，读取端按字符串处理；如果后续需要更严格状态机，建议统一 enum 或单独建 control action 表。

主要状态转移：

```text
run start
  -> running
  -> human_required        # spec approval / plan approval / plan invalid / worker failed / stale artifact / gates exhausted / evidence invalid
  -> ready_for_human_review # evidence final_status ready
```

控制命令状态规则：

- `pause`、`stop` 只允许 `running`。
- `approve` 只允许 `human_required`。
- `verify`、`review` 允许 `human_required` 或 `ready_for_human_review`。
- `resume` 遇到 `paused` 或 `stopped` 只返回当前状态，不继续执行。

恢复规则：

- 优先读取 LangGraph checkpoint；没有则回退自有 `workflow_checkpoints`。
- 恢复前扫描 run 目录中现有 YAML Artifact 的 lineage。
- 上游 revision/hash 或 contract hash 不一致时进入 `human_required`，并记录 `stale_artifacts`。
- 如果 checkpoint 引用的 Artifact 不完整，则重置到 `collect_goal` 重放。
- 前半段节点可复用 `00` 到 `03` 既有 Artifact；后半段 `04` 到 `07` 也有入口态复用；存在 repair result 时 gate 会重新执行，避免复用修复前失败报告。

## 已实现部分

已由代码和测试共同确认：

- Python package、CLI、配置、docs、schema、测试骨架。
- `init`、`run`、`dry-run`、`status`、`show`、`resume`、`report`、`artifacts`、`logs`、`explain`、`approve`、`pause`、`stop`、`verify`、`review`、`release`、`serve`、`doctor`。
- Pydantic v2 Artifact Envelope。
- YAML hash、revision history、lineage 输入记录、stale 拦截。
- deterministic repository inspection。
- deterministic spec 和 plan 生成。
- solo、pipeline、parallel strategy。
- pipeline 依赖顺序执行。
- parallel 审批、allowed path 冲突检查、contract handoff 检查、worktree 并发、patch 串行回放。
- fake backend 离线运行。
- codex exec backend。
- 质量门执行、日志落盘、失败 fingerprint。
- 有边界的 repair loop。
- 独立 review worker 和 review parser。
- Evidence Bundle 完整性校验和 delivery report。
- SQLite run/event/checkpoint/lock。
- LangGraph graph、checkpoint adapter、resume。
- 本地 Web console，含 artifact/log/report/doctor 读取和 approve/pause/stop/resume/verify/review/release 控制。
- run_dir/path traversal/symlink escape 等控制台读取安全防护。
- release manifest 生成。

## 未实现 / 部分实现 / 待完善

| 项目 | 状态 | 代码依据 |
| --- | --- | --- |
| `codex_sdk` 真实执行 | 部分实现/占位 | `CodexSdkBackend.start_worker()` 和 `continue_worker()` 直接抛 `BackendUnavailableError` |
| SQLAlchemy 存储层 | 当前代码未发现明确实现 | 依赖声明存在，但 `Database` 使用标准库 `sqlite3` |
| 自动 PR 创建 | 当前代码未发现明确实现 | README roadmap 提到后续；`ReleaseService` 只生成人工命令 |
| 自动 git push/远程写入 | 当前代码未发现明确实现 | permissions 默认关闭；release manifest `remote_actions_allowed=false` |
| 自动 git commit | 当前代码未发现明确实现 | release manifest 只列人工 `git add` / `git commit` 命令 |
| 通知审批 | 当前代码未发现明确实现 | README roadmap 提到后续 |
| schema 生成覆盖 `release_manifest` | 部分实现 | Pydantic 模型存在，但 `ARTIFACT_DATA_MODELS` 未包含 `release_manifest` |
| model-assisted rich spec/plan | 部分实现/待确认 | 当前 `spec_builder` 和 `planner` 是 deterministic 规则；没有看到调用 LLM 生成 spec/plan 的实现 |
| dispatch/repair 执行型节点完全幂等 | 部分实现 | README/workflow 也标注后续扩展；当前已有部分 artifact reuse 和 completed task reuse |
| Web console SSE/实时推送 | 当前代码未发现明确实现 | Web UI/API 当前是普通 HTTP + 轮询形态 |
| 成熟多 backend 能力 | 部分实现 | fake 和 codex_exec 可用；SDK/更多 backend 是后续方向 |
| 严格统一状态枚举 | 部分实现 | DB 可能写入非 `RunStatus` enum 的控制状态字符串 |

## 确定事实与推断

确定事实：

- CLI 入口、命令清单、配置模型、Artifact 模型、运行目录、SQLite 表结构、LangGraph 节点、backend provider、质量门、repair/review/evidence/release 逻辑均可从源码直接确认。
- 当前主路径是 `RunService` + `build_workflow_graph(context=...)`。`README.md` 和 `tests/unit/test_documentation_contracts.py` 也在防止文档回退到旧 runner 叙述。
- YAML Artifact 是下游事实来源；SQLite 只存索引、事件、checkpoint、锁。
- `codex_exec` 不依赖 Codex CLI JSON/schema 输出。
- 完成状态由 Evidence Bundle 的 validation 和 final_status 决定，而不是 worker 自称完成。

推断：

- Coductor 面向“本地目标项目”运行，安装一次后在目标项目目录执行，这是从 README、`init_project()` 和 `.coductor/` 写入位置推断，但也符合当前代码。
- `WorkflowGraphRunner` 可能是早期主路径或测试辅助/兼容层；当前没有在 `RunService` 主执行路径中调用它。
- `sqlalchemy` 依赖可能是历史遗留或未来计划；当前代码未发现使用。

待确认：

- 是否要保留 `WorkflowGraphRunner` 作为公开内部 API，还是后续清理。
- 是否要为 `08_release_manifest.yaml` 生成 JSON Schema。
- 是否要把 `approved`、`verification_requested`、`review_requested` 纳入正式状态机。
- `codex_sdk` 的目标实现范围和是否仍需要保留 provider 名称。

## 建议绘制的图表清单

建议先画 5 张图，全部基于本清单：

1. 系统分层架构图
   - 目的：对外说明 Coductor 的整体边界。
   - 内容：CLI/Web Console、RunService、LangGraph Workflow、Service 层、Backend、YAML Artifact、SQLite、目标 Git 仓库。

2. 主业务流转图
   - 目的：展示从 goal 到 evidence 的端到端流程。
   - 内容：`collect_goal` 到 `prepare_evidence` 的节点、条件分支、repair loop、human_required/ready 状态。

3. Artifact 事实链图
   - 目的：解释为什么 Coductor 可审计、可恢复。
   - 内容：`00` 到 `08` Artifact、`inputs` lineage、hash/revision/history、contract hash、delivery report。

4. 执行策略图
   - 目的：说明 Solo First、pipeline、parallel 的区别。
   - 内容：solo 单 task，pipeline `T001 -> T002`，parallel approval + worktree + patch apply。

5. 控制面与恢复图
   - 目的：展示 CLI/Web 控制命令如何复用同一状态和锁。
   - 内容：`status/logs/artifacts/explain` 读路径，`approve/resume/verify/review/release` 写路径，SQLite lock，checkpoint，stale artifact 检测。

可选第 6 张：

- 后端边界图
  - 目的：避免误解 Codex CLI 直接产出结构化最终事实。
  - 内容：`FakeCodingBackend`、`CodexExecBackend`、`CodexSdkBackend placeholder`、WorkerResult 普通摘要、Coductor 本地封装固定 YAML。
