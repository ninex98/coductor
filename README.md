# Coductor

> Verified Codex Runs
> From a natural-language goal to evidence-backed delivery.

Coductor 是一个本地 AI Coding 工作流控制面。它不试图替代 Codex，也不是“更聪明的聊天客户端”；它的核心价值是把一次 Codex 研发任务变成可审计、可恢复、可验证的 run：目标被拆成验收标准，验证计划写入 YAML Artifact，质量门和工具证据被记录，目标满足度被独立评估，最终由 Evidence Bundle 决定是否进入交付状态。

```text
Goal -> Spec -> Verification Plan -> Execute -> Gates + Tool Checks
     -> Goal Satisfaction -> Repair / Review -> Evidence
```

![Coductor system overview](docs/architecture/exported/coductor-system-overview.png)

## 目录

- [中文版本](#中文版本)
- [English Version](#english-version)

---

# 中文版本

## 一句话理解

Coductor 的作用不是“跑一圈命令”，而是给 Codex run 加上目标满足闭环：如果测试通过但目标证据不足，它应该能写出缺什么、尝试修复或补证据，并在达到边界时进入 `human_required`，而不是口头宣布完成。

## 当前能力

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| CLI 主流程 | 已实现 | `init`、`run`、`dry-run`、`resume`、`status`、`report`、`artifacts`、`logs`、`explain` |
| 本地 Web 控制台 | 已实现 | `coductor serve`，默认 `127.0.0.1:8765`，提供 Overview、Artifacts、Timeline、Logs、Evidence、Goal Loop、Release、Doctor |
| YAML Artifact 契约 | 已实现 | Envelope、hash、revision、lineage、history、stale 拦截、JSON Schema 生成 |
| LangGraph 编排 | 已实现 | `RunService` 构建 contextual LangGraph，节点保持薄，副作用在 service 层 |
| 目标满足循环 | 已实现 | `03_verification_plan.yaml` 规划证据，`07_goal_satisfaction.yaml` 判断每条验收标准是否满足 |
| 工具验证 | 已实现 | `tool_runs/*/tool_request.yaml` 和 `tool_result.yaml` 记录 command、browser、image/image_generation 等工具证据 |
| 浏览器验证 | 已实现 | 可生成 Playwright smoke runner，支持 URL/static path、selector/text、console error、screenshot |
| 生图证据契约 | 已实现基础版 | 默认不批量生图；无生成后端时写出 image asset request 并进入 human/actionable evidence |
| 质量闭环 | 已实现 | 质量门、失败指纹、最多 2 次修复循环、独立 Review、Evidence Bundle |
| 后端边界 | 已实现/显式边界 | 默认真实路径为 `codex_exec`，离线测试用 `fake`，`codex_sdk` 仍是实验占位边界 |
| 安全控制 | 已实现 | 默认关闭网络、Git push、PR、生产路径访问；控制命令有状态校验和 run lock |

## 它比直接用 Codex 多什么

- 目标不是只靠聊天上下文保存，而是落到 `00_goal.yaml`、`02_spec.yaml` 和验收标准。
- 测试通过不等于目标满足；`07_goal_satisfaction.yaml` 会把每条标准映射到 gate、browser、image 或其他工具证据。
- 不满足时会进入 bounded repair，默认最多 2 次；重复失败、缺人工输入或证据不确定时进入 `human_required`。
- `resume` 基于 checkpoint 与 Artifact lineage 恢复，发现 stale 输入会拒绝静默覆盖。
- Web Console 可以重跑工具检查和目标满足评估，而不是只能看一次性终端输出。

## 快速开始

建议把 Coductor 作为独立 CLI 工具安装，然后在任意目标项目里使用：

```bash
pipx install -e /Users/ninex/Projects/hll-ecosystem/apps/coductor
coductor --help
coductor --version
```

进入目标项目：

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

本地控制台：

```bash
coductor serve
```

默认地址：

```text
http://127.0.0.1:8765
```

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `coductor run "<goal>"` | 执行研发目标 |
| `coductor run "<goal>" --dry-run` | 只生成前置 Artifact，不派发 Worker |
| `coductor resume <RUN_ID>` | 从 checkpoint 和 Artifact 链恢复 |
| `coductor verify <RUN_ID>` | 重跑质量门并更新 `05_gate_report.yaml` |
| `coductor review <RUN_ID>` | 重跑独立审查与 Evidence |
| `coductor release <RUN_ID>` | 生成 `08_release_manifest.yaml` |
| `coductor serve` | 启动本地 Web 控制台 |
| `coductor doctor` | 检查配置、后端能力、安全默认值和质量门 |

Web 控制台的受控动作包括 `approve`、`pause`、`stop`、`resume`、`verify`、`review`、`release`、`rerun-tool-checks`、`rerun-satisfaction`。它不提供任意 shell，也不替代 YAML Artifact 作为下游事实来源。

## 运行产物

Coductor 的正式交接文件是固定 YAML Artifact。一次 run 可能写入：

```text
.coductor/runs/<run-id>/
├── 00_goal.yaml
├── 01_repository_snapshot.yaml
├── 02_spec.yaml
├── 03_verification_plan.yaml
├── 03_execution_plan.yaml
├── 04_integration.yaml
├── 05_gate_report.yaml
├── 06_review.yaml
├── 07_goal_satisfaction.yaml
├── 07_evidence.yaml
├── 08_release_manifest.yaml
├── delivery-report.md
├── contracts/
├── history/
├── logs/
├── repairs/R###/
│   ├── repair_request.yaml
│   ├── repair_result.yaml
│   └── repair_result.patch
├── tool_runs/<tool-run-id>/
│   ├── tool_request.yaml
│   ├── tool_result.yaml
│   ├── stdout.log
│   └── stderr.log
└── tasks/<task-id>/
    ├── task.yaml
    ├── worker_request.yaml
    ├── worker_result.yaml
    └── patch.diff
```

并非每个 run 都一定产生所有文件；例如未 release 的 run 不会有 `08_release_manifest.yaml`。当前为了兼容已有契约，`03_*` 和 `07_*` 各有两个语义文件，代码按固定文件名读取。

## 架构与执行流

![Coductor runtime flow](docs/architecture/exported/coductor-runtime-flow.png)

核心边界：

- 确定性程序负责 Git、文件扫描、Schema 校验、质量门、权限、哈希、run lock 和状态恢复。
- 模型/后端负责语义理解、计划、编码、诊断与审查建议。
- `03_verification_plan.yaml` 把验收标准映射到 gate、tool check、manual 或 image asset evidence。
- `WorkflowVerificationService` 在质量门后运行工具检查，写入 `tool_runs/*`。
- `07_goal_satisfaction.yaml` 汇总 gate/tool/manual evidence，决定 satisfied、not_satisfied 或 uncertain。
- Evidence Bundle 读取 review、goal satisfaction 和工具结果；完成状态由这些事实决定，而不是由 Agent 声称。

![Coductor artifact state flow](docs/architecture/exported/coductor-artifact-state-flow.png)

## Backend Boundary

`src/coductor/backends/factory.py` 负责后端选择：

- `codex_exec`：默认真实执行路径，通过 `codex exec` 调用 Codex CLI。
- `fake`：测试和离线 smoke 的确定性实现。
- `codex_sdk`：显式实验边界；Doctor 会报告 `backend_implemented`、`backend_stability` 和说明，不把它伪装成默认能力。

Codex CLI 可以返回普通文本摘要；`worker_result.yaml`、`review.yaml`、`gate_report.yaml`、`goal_satisfaction.yaml`、`evidence.yaml` 等结构化文件由 Coductor 本地写入。

## 本地开发

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
mypy src
```

生成 Schema：

```bash
python scripts/generate_schemas.py
```

重新生成架构图：

```bash
.venv/bin/python docs/architecture/generate_diagrams.py --export-png
```

## Roadmap

已完成的近期主线：Goal Satisfaction Loop、tool-aware verification、browser runner、image asset request contract、Web Goal Loop、Evidence hardening、backend capability hardening。

后续重点：

- 让 spec/verification plan 从规则生成进一步走向更强的模型辅助。
- 为常见前端、后端、数据任务沉淀 tool check 模板。
- 改进 `human_required` UX，让“缺什么证据、下一步怎么补”更直接。
- 更充分地在真实项目中 dogfood 长 run 和多轮 repair。

危险能力仍默认关闭：不自动推送远程分支，不自动创建 PR，不读取生产秘密，不自动合并。

更多文档：

- [Workflow](docs/workflow.md)
- [Architecture](docs/architecture.md)
- [YAML Contracts](docs/yaml-contracts.md)
- [Security](docs/security.md)
- [Architecture Diagrams](docs/architecture/README.md)

---

# English Version

## What Is Coductor?

Coductor is a local control plane for verified Codex runs. It turns a natural-language engineering goal into structured YAML artifacts, quality gates, tool evidence, bounded repair, independent review, and an Evidence Bundle.

It is not a chat client and not a replacement for Codex. It wraps coding agents with deterministic contracts and verification.

## Highlights

| Area | Status | Notes |
| --- | --- | --- |
| CLI workflow | Shipped | `init`, `run`, `dry-run`, `resume`, `status`, `report`, `artifacts`, `logs`, `explain` |
| Local console | Shipped | Overview, Artifacts, Timeline, Logs, Evidence, Goal Loop, Release, Doctor |
| YAML contracts | Shipped | Envelope, hash, revision, lineage, history, stale checks, generated JSON Schemas |
| Goal satisfaction loop | Shipped | `03_verification_plan.yaml` plus `07_goal_satisfaction.yaml` |
| Tool verification | Shipped | `tool_runs/*/tool_request.yaml` and `tool_result.yaml` for command/browser/image evidence |
| Verification loop | Shipped | Gates, failure fingerprints, bounded repair, independent review, Evidence Bundle |
| Backends | Shipped boundary | `codex_exec` default, `fake` for offline smoke, `codex_sdk` experimental |
| Safety | Shipped | Network, git push, PR creation, and production paths are disabled by default |

## Quick Start

```bash
pipx install -e /Users/ninex/Projects/hll-ecosystem/apps/coductor
cd /path/to/target-project
coductor init
coductor doctor
coductor run "fix the sample function and add tests" --backend fake
coductor report <RUN_ID>
```

Local console:

```bash
coductor serve
```

Default URL:

```text
http://127.0.0.1:8765
```

## Artifact Layout

```text
.coductor/runs/<run-id>/
├── 00_goal.yaml
├── 01_repository_snapshot.yaml
├── 02_spec.yaml
├── 03_verification_plan.yaml
├── 03_execution_plan.yaml
├── 04_integration.yaml
├── 05_gate_report.yaml
├── 06_review.yaml
├── 07_goal_satisfaction.yaml
├── 07_evidence.yaml
├── 08_release_manifest.yaml
├── repairs/R###/
├── tool_runs/<tool-run-id>/
└── tasks/<task-id>/
```

Resume validates hashes, revisions, and input lineage before continuing.

## Architecture

- Deterministic code handles Git, repository scanning, schema validation, quality gates, tool checks, permissions, hashes, locks, and run state.
- Backends handle semantic reasoning, implementation, repair diagnosis, and review suggestions.
- YAML artifacts are the handoff source of truth.
- SQLite stores run indexes, events, locks, and checkpoint entry points.
- Completion is decided by gates, tool evidence, goal satisfaction, review, and Evidence Bundle validation.

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
mypy src
```

## License

MIT
