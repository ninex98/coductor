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

本仓库实现 Phase 0 + Phase 1 的首个可运行垂直切片：

- Python `src` 布局、CLI、配置、文档和测试骨架；
- Pydantic v2 YAML Artifact Envelope；
- Artifact hash、revision history、lineage 输入记录和 stale 拦截；
- `coductor init`、`run`、`status`、`show`、`resume`、`report`、`doctor`；
- 仓库扫描、模拟 Spec、solo Plan、Plan Validator；
- `FakeCodingBackend` 离线端到端运行；
- Backend Factory：测试使用 fake，SDK 不可用时按配置降级到 `codex exec`；
- `codex exec` fallback 使用显式 sandbox、JSONL 输出和 JSON Schema 响应约束；
- 质量门执行、失败指纹、有限修复循环；
- 独立 Reviewer Worker 和 Evidence Bundle；
- SQLite run/event 索引。

LangGraph、`openai-codex` SDK、Typer、Rich、PyYAML、SQLAlchemy、pytest、ruff、mypy 在 `pyproject.toml` 中声明为目标依赖。当前代码把 Coding Backend 隔离在接口后：`fake` 用于离线验证，`codex_sdk` 保持 SDK 边界，SDK 缺失且配置允许时自动 fallback 到 `codex_exec`。

`resume` 当前通过 SQLite workflow checkpoint 恢复原 `run_id`、目标、执行模式和阶段状态。恢复前会校验已有 Artifact 链路，检测到 hash 或 revision 不一致时进入 `human_required`，避免直接覆盖可疑证据。`workflow/graph.py` 已能构建最小 LangGraph `StateGraph`；后续会把各阶段副作用继续迁入薄节点，并接入 LangGraph 原生 SQLite saver。

## 最短演示

```bash
uv sync
uv run coductor init
uv run coductor doctor
uv run coductor run "修复示例函数并补充测试" --backend fake
uv run coductor status
uv run coductor show <RUN_ID>
uv run coductor report <RUN_ID>
```

在当前受限环境没有 `uv` 时，可以用 Python 3.12 做基础调用：

```bash
PYTHONPATH=src python3 -m coductor.cli doctor
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
├── history/
├── logs/
├── repairs/
└── tasks/T001/
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
  strategy: solo
  strategy_reasoning:
    - "auto 模式默认倾向 solo；当前目标可由一个连续上下文完成"
  tasks:
    - id: T001
      task_type: integrated_implementation
      role: builder
      allowed_paths:
        - "src/**"
        - "tests/**"
```

## Roadmap

- Phase 2：动态 pipeline、Task DAG、上游 Artifact 哈希失效、契约文件；
- Phase 3：Git Worktree、安全并行 Worker、写路径冲突预检查、集成；
- Phase 4：Web 控制台、通知审批、PR 创建、成本/Token 指标、更多 Backend。

危险能力默认关闭：不推送远程分支，不创建 PR，不读取生产秘密，不自动合并。
