# Coductor

**Coductor** 是面向 AI Coding Agent 的确定性研发工作流引擎。

英文定位：**Deterministic AI Coding Workflow Engine**  
Slogan：**From goal to verified change.**

Coductor 将自然语言研发目标转换为可审计、可恢复、可验证的工程工作流：

```text
Goal -> Inspect -> Spec -> Plan -> Execute -> Verify <-> Repair -> Review -> Evidence
```

它不是普通聊天客户端，也不是多 Agent 数量展示工具。首版默认 **Solo First**：能由一个 Codex Thread 完成的任务，不启动多个写代码 Worker。

## 当前范围

本仓库实现本地可运行的核心垂直切片：

- Python `src` 布局、CLI、配置、文档和测试骨架；
- Pydantic v2 YAML Artifact Envelope；
- Artifact hash、revision history、lineage 输入记录和 stale 拦截；
- `coductor init`、`run`、`status`、`show`、`resume`、`report`、`doctor`；
- `coductor artifacts`、`logs`、`explain`、`approve`、`pause`、`stop`、`verify`、`review` 控制面命令；
- 仓库扫描、模拟 Spec、solo Plan、Plan Validator；
- `FakeCodingBackend` 离线端到端运行；
- Backend Factory：默认真实后端为 `codex exec`，测试和离线 smoke 使用 fake，`codex_sdk` 作为显式实验边界保留；
- `codex exec` fallback 使用显式 sandbox 和 stdin prompt；Codex CLI 返回普通文本，固定 YAML Artifact 由 Coductor 本地写入；
- `auto` 会在检测到明确先后依赖时生成顺序 pipeline，并按任务依赖顺序执行；
- Contract Artifact 记录契约文件 hash，下游 task 消费契约时会被 stale 校验保护；
- 显式 `parallel` 计划会先检查写路径冲突和 contract handoff，默认要求人工审批；`approve` 后 `resume` 会按 `max_parallel_workers` 在隔离 git worktree 并发执行独立任务，再串行回放 patch 并写 integration report；
- 质量门执行、失败指纹、有限修复循环；
- 独立 Reviewer Worker 和 Evidence Bundle；Evidence 只有在必需 Gate 通过、无 blocking review、且存在 patch evidence 时才 ready；
- SQLite run/event 索引。

LangGraph、`openai-codex` SDK、Typer、Rich、PyYAML、SQLAlchemy、pytest、ruff、mypy 在 `pyproject.toml` 中声明为目标依赖。当前代码把 Coding Backend 隔离在接口后：`codex_exec` 是默认真实执行路径，`fake` 用于离线验证，`codex_sdk` 保持 SDK 实验边界且需要显式配置。Backend 只提供执行摘要、命令记录和退出原因；`worker_result.yaml`、`review.yaml`、`gate_report.yaml`、`evidence.yaml` 等固定结构文件始终由 Coductor 写入，不能依赖外部 CLI 的 schema 模式。

`RunService` 当前构建 contextual LangGraph 执行主 workflow：节点保持薄，按固定 Artifact 读取上游事实，并调用 artifact writer、task execution、verification、repair、review delivery 等服务写入下游 YAML。`resume` 通过 SQLite workflow checkpoint 恢复原 `run_id`、目标、执行模式、阶段状态和修复次数；恢复前会校验已有 Artifact 链路，检测到 hash 或 revision 不一致时进入 `human_required`，避免直接覆盖可疑证据。链路完整时 graph 会从 checkpoint stage 继续；checkpoint 缺少必要 Artifact 时回退到 `collect_goal` 重放。`compile_workflow_graph` 支持传入 checkpointer，`langgraph-checkpoint-sqlite` 已作为目标依赖声明。

## 最短演示

推荐先把 Coductor 作为独立 CLI 工具安装，而不是在每个目标项目里复制源码：

```bash
pipx install -e /Users/ninex/Projects/hll-ecosystem/apps/coductor
coductor --help
coductor --version
```

`pipx install -e` 是 editable 安装：日常修改 Coductor 源码后通常不需要重装；如果改了依赖、入口脚本或 `pyproject.toml`，再执行 `pipx reinstall coductor`。运行 `coductor` 时，它只会在当前目标项目写入 `coductor.yaml` 和 `.coductor/`，不会把运行产物写回 Coductor 源码目录。

```bash
cd /path/to/target-project
coductor init
coductor doctor
coductor run "修复示例函数并补充测试" --backend fake
coductor status <RUN_ID>
coductor artifacts <RUN_ID>
coductor logs <RUN_ID>
coductor explain <RUN_ID>
coductor report <RUN_ID>
```

这些命令已用 `examples/demo-python-project` 和当前 `.venv/bin/coductor` 验证。一次 fake backend demo 的稳定输出要点：

```text
状态: ready_for_human_review
Final status: ready_for_human_review
Required gates: 1/1 passed
Evidence validation: valid
```

## 生成目录

```text
.coductor/runs/<run-id>/
├── 00_goal.yaml
├── 01_repository_snapshot.yaml
├── 02_spec.yaml
├── 03_execution_plan.yaml
├── 04_integration.yaml
├── 05_gate_report.yaml
├── 06_review.yaml
├── 07_evidence.yaml
├── delivery-report.md
├── contracts/
│   ├── contracts.yml
│   └── generated.schema.json
├── history/
├── logs/
├── repairs/
└── tasks/<task-id>/
    ├── task.yaml
    ├── worker_request.yaml
    ├── worker_result.yaml
    └── patch.diff
```

## YAML 示例

```yaml
schema_version: "1.0"
artifact_type: execution_plan
status: validated
data:
  strategy: pipeline
  strategy_reasoning:
    - "目标包含明确的先后依赖信号"
  tasks:
    - id: T001
      task_type: contract_authoring
      role: builder
      depends_on: []
    - id: T002
      task_type: integrated_implementation
      role: builder
      depends_on:
        - T001
      allowed_paths:
        - "src/**"
        - "tests/**"
```

## Roadmap

- 已完成：artifact lineage、resume stale 检测、codex exec fallback、动态 pipeline、contract stale 检测、安全 parallel 预检、parallel 审批恢复、worktree 并发执行、CLI 控制面真实 verify/review、evidence hardening、demo E2E。
- 后续：Web 控制台、通知审批、PR 创建、成本/Token 指标、更多 Backend、LangGraph 原生 checkpoint 生命周期清理。

危险能力默认关闭：不推送远程分支，不创建 PR，不读取生产秘密，不自动合并。
