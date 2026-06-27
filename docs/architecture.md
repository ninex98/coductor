# Coductor Architecture

Coductor 的边界是“确定性研发工作流引擎”，不是聊天客户端。大模型负责语义理解、计划、代码修改和诊断；确定性程序负责 Git、文件扫描、Schema 校验、质量门、权限和哈希；YAML Artifact 是阶段交接事实来源；SQLite 只保存运行索引、事件索引和恢复入口。

## 数据所有权

- `Goal`：用户输入，由 CLI 采集。
- `Repository Snapshot`：普通程序采集 Git、manifest、命令和风险事实。
- `Specification`：模型可辅助生成，但必须通过 Pydantic 契约校验。
- `Execution Plan`：Planner 输出，Plan Validator 决定是否可执行。
- `Worker Result`：Coding Backend 输出，仅记录声明和 patch 引用。
- `Gate Report`：Gate Runner 通过真实命令产生，是验证事实来源。
- `Review Report`：独立只读 Worker 产生，不能读取 Builder 隐藏推理。
- `Evidence Bundle`：Delivery Manager 汇总，只有必需 Gate 通过、无阻塞审查且存在 patch evidence 时才 ready。

## 流程

```text
collect_goal
  -> inspect_repository
  -> draft_spec
  -> validate_spec
  -> create_execution_plan
  -> validate_execution_plan
  -> materialize_tasks
  -> dispatch_tasks
  -> integrate_changes
  -> run_quality_gates
     -> repair_failure -> run_quality_gates
     -> run_independent_review
  -> prepare_evidence
```

当前由 `RunService` 构建 contextual LangGraph 发起这个垂直切片，并通过 SQLite workflow checkpoint 支持 `resume`。各阶段节点只做编排适配：读取上游 YAML Artifact、调用 artifact writer、task execution、verification、repair、review delivery 等服务、记录固定 Artifact 路径并保存 checkpoint。`workflow/graph.py` 负责节点注册、条件路由、按 checkpoint stage 进入图，以及 `compile_workflow_graph` 的 checkpointer 接入；`langgraph-checkpoint-sqlite` 已作为目标依赖声明。

## Solo First

`auto` 模式默认生成 `solo` 计划。当目标出现明确的先后依赖信号，例如 `先`、`再`、`schema`、`contract`、`OpenAPI`、`上游`、`下游`，Planner 会选择 `pipeline`。Pipeline 当前按任务依赖拓扑顺序串行执行，每个任务都会生成自己的 `tasks/<task-id>/task.yaml`、worker request/result 和 patch。契约文件写入 `contracts/`，并以 `ContractArtifact` 记录 path、kind、sha256 和 producer task；下游 task 消费契约时会记录该 hash，`resume` 会在契约变更后进入 `human_required`。显式 `parallel` 计划必须通过依赖图、验收覆盖、上游 Artifact、写路径冲突、冻结 contract 和策略理由检查；验证失败会直接进入 `human_required`。验证通过后默认仍需人工批准，批准写入 `03_execution_plan.yaml` 后 `resume` 从 `validate_execution_plan` 继续。真正执行时，ready tasks 在隔离 git worktree 并发运行，主仓库只在批次完成后串行应用 patch，并在 `04_integration.yaml` 记录 merged tasks 与 conflicts 列表。

## Backend Boundary

`src/coductor/backends/factory.py` 负责所有 Backend 选择。`codex_exec` 是默认真实执行路径；`fake` 是测试和离线 smoke 的确定性实现；`codex_sdk` 保留 SDK 配置边界，需要显式配置后使用。当 SDK 不可用且配置 fallback 为 `codex_exec` 时，factory 会降级到 CLI backend。

`CodexExecBackend` 使用 list-based `subprocess.run()`，prompt 通过 stdin 传入，当前命令形态是 `codex exec --sandbox <mode> --skip-git-repo-check -`。它不使用 Codex CLI 的 JSON/schema 模式：Worker 可以返回普通文本摘要，Coductor 再把摘要、退出原因、命令记录和 patch 引用包装进固定 YAML Artifact。

## 安全

默认配置关闭网络、Git push、PR 创建和生产路径访问。质量门命令来自 `coductor.yaml`，使用 `shlex.split` 执行，不拼接不可信 shell 字符串。
