# Coductor Diagram Content Model

本文档记录当前架构图的内容模型。它的目标不是穷尽代码细节，而是约束 README 与架构图只表达已经落地的核心能力，避免把 planned/placeholder 能力画成已实现。

## 1. 当前定位

Coductor 是 `Verified Codex Runs` 控制面：它不替代 Codex，而是围绕 Codex run 增加固定 YAML Artifact、质量门、工具证据、目标满足评估、bounded repair、独立 review 和 Evidence Bundle。

主叙事应是：

```text
Goal -> Spec -> Verification Plan -> Execute -> Gates + Tool Checks
     -> Goal Satisfaction -> Repair / Review -> Evidence
```

旧叙事 `Goal -> Inspect -> Spec -> Plan -> Execute -> Verify <-> Repair -> Review -> Evidence` 已不完整，因为它缺少 `03_verification_plan.yaml`、`tool_runs/*` 和 `07_goal_satisfaction.yaml`。

## 2. 必须进入图中的内容

- CLI 与本地 Web Console 都进入同一服务层。
- `RunService` 构建 contextual LangGraph，节点保持薄，真实副作用在 service 层。
- YAML Artifact 是阶段正式交接事实来源。
- SQLite 保存 run/event/checkpoint/lock，不替代 YAML 事实链。
- `03_verification_plan.yaml` 把验收标准映射到 gate、tool check、manual 或 image asset evidence。
- `WorkflowVerificationService` 在质量门后运行 `ToolVerificationService`，写入 `tool_runs/*/tool_request.yaml` 和 `tool_result.yaml`。
- `07_goal_satisfaction.yaml` 以 gate/tool/manual evidence 判断每条验收标准是否 satisfied、not_satisfied 或 uncertain。
- 不满足时进入 bounded repair；默认最多 2 次，重复失败或不确定证据进入 `human_required`。
- Web Console 的 Goal Loop 视图与 `rerun-tool-checks`、`rerun-satisfaction` 动作。
- Evidence Bundle 读取 gate、review、goal satisfaction 和 tool results；完成状态由这些事实决定。

## 3. 放到文字说明，不塞进图里

- CLI 命令完整清单。
- YAML schema 字段级细节。
- SQLite 表字段细节。
- 每个 Python service 或 node 的方法名。
- GateRunner 的 subprocess 参数、stdout/stderr 文件路径。
- repair prompt 的完整上下文。
- release manifest 中的具体 Git 命令。

## 4. 不应画成已实现的能力

- 自动远程 `git push`、自动 PR、自动 merge。
- 生产 secrets 读取或生产路径写入。
- `codex_sdk` 默认可用路径；它当前只是实验/占位边界。
- Codex CLI 直接输出 Coductor 的结构化 YAML。
- SQLAlchemy storage 替代当前 SQLite stdlib 实现。
- Web Console SSE/实时推送；当前是 HTTP + 前端刷新/轮询模型。

## 5. 图 1：系统架构总览

目的：解释 Coductor 的产品边界与模块关系。

图中区域：

| 区域 | 关键词 |
| --- | --- |
| 用户入口 | CLI、Local Web Console、controlled actions |
| 控制平面 | RunService、LangGraph、WorkflowState、SQLite locks |
| 执行层 | CodexExecBackend、FakeBackend、CodexSdkBackend placeholder |
| 质量闭环 | Quality Gates、Tool Verification、Goal Satisfaction |
| 事实层 | YAML Artifacts、Tool Runs、SQLite、Target Repo |

主线必须包含：

```text
Goal -> Spec -> Verification Plan -> Execute -> Tool Checks -> Satisfaction -> Evidence
```

## 6. 图 2：端到端运行流程

目的：解释一次 run 如何从目标变成证据化交付。

主流程阶段：

| 阶段 | 图中短标签 | 关键产物 |
| --- | --- | --- |
| collect_goal | Goal | `00_goal.yaml` |
| inspect_repository | Inspect | `01_repository_snapshot.yaml` |
| draft_spec | Spec | `02_spec.yaml` |
| create_verification_plan | Verify Plan | `03_verification_plan.yaml` |
| create_execution_plan | Exec Plan | `03_execution_plan.yaml` |
| dispatch_tasks | Execute | `tasks/*/worker_result.yaml`、`patch.diff` |
| run_quality_gates | Gate + Tools | `05_gate_report.yaml`、`tool_runs/*` |
| evaluate_goal_satisfaction | Satisfaction | `07_goal_satisfaction.yaml` |
| review/evidence | Evidence | `06_review.yaml`、`07_evidence.yaml` |

关键分支：

- Spec 或 parallel plan 需要审批：进入 `human_required`，等待 `approve + resume`。
- Gate/tool/goal satisfaction 不满足：进入 repair loop，随后重新验证。
- `uncertain` 或达到修复边界：进入 `human_required`。
- Evidence valid：进入 `ready_for_human_review`。
- Release 是后置命令，只生成 `08_release_manifest.yaml`，不自动远程发布。

## 7. 图 3：Artifact / State 流转

目的：解释固定文件事实链、状态恢复与防 stale 边界。

固定 Artifact 链：

```text
00_goal
-> 01_repository_snapshot
-> 02_spec
-> 03_verification_plan
-> 03_execution_plan
-> tasks/T###/*
-> 04_integration
-> 05_gate_report
-> tool_runs/*
-> 07_goal_satisfaction
-> 06_review
-> 07_evidence
-> 08_release_manifest
```

当前兼容编号现状：`03_*` 和 `07_*` 各有两个语义文件。图中可以明确展示这一点，文字说明里强调代码按固定文件名读取。

修复链：

```text
failed evidence
-> repairs/R###/repair_request.yaml
-> repairs/R###/repair_result.yaml
-> repairs/R###/repair_result.patch
-> rerun gates/tool/satisfaction
```

状态边界：

```text
running
human_required
ready_for_human_review
paused
stopped
failed
```

控制状态字符串如 `approved`、`verification_requested`、`review_requested` 可以在文字中说明，不需要作为主状态机节点。
