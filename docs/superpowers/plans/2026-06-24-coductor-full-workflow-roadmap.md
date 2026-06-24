# Coductor Full Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善 Coductor 从 MVP 到可恢复、可审计、可验证、可扩展的确定性 AI Coding Workflow Engine。

**Architecture:** 保持 YAML Artifact 作为阶段事实来源，SQLite 作为运行索引和 checkpoint 存储，LangGraph 作为流程 runtime，Coding Backend 通过接口隔离。执行顺序采用 Solo First：先把单 Worker 链路做真实、可恢复、可验证，再扩展 pipeline、contract invalidation、parallel worktree 和交付能力。

**Tech Stack:** Python 3.12, `.venv`, Pydantic v2, PyYAML, Typer, Rich, LangGraph, SQLite, pytest, ruff, mypy, Codex SDK or `codex exec`.

---

## Baseline

Current verified baseline:

```bash
.venv/bin/python --version
.venv/bin/python -m pip check
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/coductor doctor
```

Expected current result:

```text
Python 3.12.13
No broken requirements found.
10 passed
All checks passed!
Success: no issues found in 58 source files
doctor reports config/database present and dangerous defaults disabled
```

All future tasks must keep this command set green before moving on.

## File Structure Map

- `src/coductor/services/run_service.py`: current Phase 1 vertical workflow. Gradually thin this down as LangGraph nodes become real.
- `src/coductor/workflow/graph.py`: will own `StateGraph` construction, node registration, route wiring, and checkpoint compilation.
- `src/coductor/workflow/state.py`: will expand from simple state to resumable workflow state with stage, artifacts, repair counters, and stop reasons.
- `src/coductor/workflow/nodes/*.py`: will move stage-specific execution out of `RunService`.
- `src/coductor/artifacts/*`: envelope models, schema generation, repository writes, lineage validation, stale detection.
- `src/coductor/backends/*`: fake backend, `codex exec`, SDK backend, backend factory.
- `src/coductor/planning/*`: strategy selection and deterministic plan validation.
- `src/coductor/repository/*`: repo inspection, git, and worktree integration.
- `src/coductor/gates/*`: deterministic command execution and parsing.
- `src/coductor/storage/*`: SQLite run/event/checkpoint indexes.
- `src/coductor/cli.py`: user-facing commands and resume/control/report entrypoints.

---

## Milestone 1: Real LangGraph Runtime And Resume

**Goal:** Replace the monolithic Phase 1 loop with real LangGraph node execution and persistent resume semantics.

**Files:**
- Modify: `pyproject.toml`
- Create: `src/coductor/workflow/checkpoint.py`
- Modify: `src/coductor/workflow/state.py`
- Modify: `src/coductor/workflow/graph.py`
- Modify: `src/coductor/workflow/nodes/intake.py`
- Modify: `src/coductor/workflow/nodes/inspect.py`
- Modify: `src/coductor/workflow/nodes/specify.py`
- Modify: `src/coductor/workflow/nodes/plan.py`
- Modify: `src/coductor/workflow/nodes/execute.py`
- Modify: `src/coductor/workflow/nodes/integrate.py`
- Modify: `src/coductor/workflow/nodes/verify.py`
- Modify: `src/coductor/workflow/nodes/repair.py`
- Modify: `src/coductor/workflow/nodes/review.py`
- Modify: `src/coductor/workflow/nodes/deliver.py`
- Modify: `src/coductor/services/run_service.py`
- Modify: `src/coductor/cli.py`
- Test: `tests/integration/test_langgraph_resume.py`

- [ ] **Step 1: Write failing resume test**

```python
from __future__ import annotations

from pathlib import Path

from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus
from coductor.services.run_service import RunService


def test_resume_continues_existing_run_id_after_gate_failure(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.workflow.max_repair_attempts = 2
    marker = tmp_path / "marker"
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=(
                f"{__import__('sys').executable} -c "
                f"\"from pathlib import Path; import sys; "
                f"p=Path({str(marker)!r}); sys.exit(0 if p.exists() else 1)\""
            ),
            timeout_seconds=30,
        )
    ]
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )

    service = RunService(tmp_path, config, backend=backend)
    first = service.run("修复示例函数并补充测试")
    resumed = service.resume(first.run_id)

    assert resumed.run_id == first.run_id
    assert resumed.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (tmp_path / ".coductor" / "runs" / first.run_id / "07_evidence.yaml").exists()
```

- [ ] **Step 2: Run test and verify it fails**

```bash
.venv/bin/pytest tests/integration/test_langgraph_resume.py -q
```

Expected: FAIL because `RunService.resume()` does not exist or does not use checkpointed state.

- [ ] **Step 3: Add checkpoint dependency**

Check whether `langgraph-checkpoint-sqlite` is available and compatible:

```bash
.venv/bin/python -m pip install langgraph-checkpoint-sqlite
.venv/bin/python - <<'PY'
from langgraph.checkpoint.sqlite import SqliteSaver
print(SqliteSaver)
PY
```

If unavailable, create `src/coductor/workflow/checkpoint.py` with a minimal SQLite-backed state persistence adapter used by `RunService.resume()` first, then replace with LangGraph saver once the dependency is available.

- [ ] **Step 4: Implement graph construction**

`src/coductor/workflow/graph.py` should expose:

```python
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from coductor.workflow.state import WorkflowState


def build_workflow_graph() -> StateGraph[WorkflowState]:
    graph = StateGraph(WorkflowState)
    graph.add_node("collect_goal", collect_goal_node)
    graph.add_node("inspect_repository", inspect_repository_node)
    graph.add_node("draft_spec", draft_spec_node)
    graph.add_node("create_execution_plan", create_execution_plan_node)
    graph.add_node("materialize_tasks", materialize_tasks_node)
    graph.add_node("dispatch_tasks", dispatch_tasks_node)
    graph.add_node("integrate_changes", integrate_changes_node)
    graph.add_node("run_quality_gates", run_quality_gates_node)
    graph.add_node("repair_failure", repair_failure_node)
    graph.add_node("run_independent_review", run_independent_review_node)
    graph.add_node("prepare_evidence", prepare_evidence_node)
    graph.add_edge(START, "collect_goal")
    graph.add_edge("collect_goal", "inspect_repository")
    graph.add_edge("inspect_repository", "draft_spec")
    graph.add_edge("draft_spec", "create_execution_plan")
    graph.add_edge("create_execution_plan", "materialize_tasks")
    graph.add_edge("materialize_tasks", "dispatch_tasks")
    graph.add_edge("dispatch_tasks", "integrate_changes")
    graph.add_edge("integrate_changes", "run_quality_gates")
    graph.add_conditional_edges("run_quality_gates", route_after_gates)
    graph.add_conditional_edges("run_independent_review", route_after_review)
    graph.add_edge("prepare_evidence", END)
    return graph
```

- [ ] **Step 5: Move each stage from `RunService` into nodes**

Each node returns a new `WorkflowState` with:

```python
state.current_stage = "stage_name"
state.artifacts["02_spec"] = "02_spec.yaml"
state.updated_at = utc_now()
```

Keep filesystem writes delegated to existing artifact services; do not put YAML serialization logic directly in node files.

- [ ] **Step 6: Implement `RunService.resume(run_id)`**

`RunService.resume()` must:

```python
def resume(self, run_id: str) -> RunResult:
    row = self.db.get_run(run_id)
    if row is None:
        raise CoductorError(
            f"unknown run {run_id}",
            stage="resume",
            run_id=run_id,
            recoverable=False,
        )
    return self._invoke_graph(run_id=run_id, raw_goal=None, resume=True)
```

- [ ] **Step 7: Verify**

```bash
.venv/bin/pytest tests/integration/test_langgraph_resume.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

Expected: all pass.

---

## Milestone 2: Artifact Revision, Idempotency, And Stale Detection

**Goal:** Make Artifact Repository truly audit-grade: repeated writes increment revision, existing valid outputs can be skipped, and downstream artifacts become stale when upstream hashes change.

**Files:**
- Modify: `src/coductor/artifacts/models.py`
- Modify: `src/coductor/artifacts/repository.py`
- Modify: `src/coductor/artifacts/validator.py`
- Modify: `src/coductor/workflow/state.py`
- Modify: `src/coductor/services/run_service.py`
- Test: `tests/unit/test_artifact_revisions.py`
- Test: `tests/integration/test_stale_artifacts.py`

- [ ] **Step 1: Write failing revision test**

```python
from __future__ import annotations

from pathlib import Path

from coductor.artifacts.repository import ArtifactRepository


def test_write_next_revision_preserves_history(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    first = make_goal("first")
    second = make_goal("second")

    repo.write("00_goal.yaml", first)
    updated = repo.write_next_revision("00_goal.yaml", second)

    assert updated.revision == 2
    assert (tmp_path / "history" / "00_goal.rev1.yaml").exists()
    assert (tmp_path / "history" / "00_goal.rev2.yaml").exists()
```

- [ ] **Step 2: Write failing stale test**

```python
def test_downstream_artifact_is_stale_when_input_hash_changes(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    goal = repo.write("00_goal.yaml", make_goal("first"))
    spec = repo.write("02_spec.yaml", make_spec(inputs=[repo.input_for("00_goal.yaml", goal)]))

    tampered_goal = goal.read_text(encoding="utf-8").replace("first", "changed")
    goal.write_text(tampered_goal, encoding="utf-8")

    errors = ArtifactLineageValidator(repo).validate_inputs(spec)
    assert any("hash mismatch" in error for error in errors)
```

- [ ] **Step 3: Implement repository methods**

Add methods:

```python
def write_next_revision(self, relative_path: str, envelope: ArtifactEnvelope[Any]) -> ArtifactEnvelope[Any]:
    current = self.read(relative_path) if (self.root / relative_path).exists() else None
    envelope.revision = 1 if current is None else current.revision + 1
    self.write(relative_path, envelope)
    return envelope


def is_current(self, relative_path: str, inputs: list[ArtifactInput]) -> bool:
    if not (self.root / relative_path).exists():
        return False
    artifact = self.read(relative_path)
    return artifact.inputs == inputs
```

- [ ] **Step 4: Integrate stale checks before node execution**

Before any node consumes upstream artifacts:

```python
errors = ArtifactLineageValidator(repo).validate_inputs("02_spec.yaml")
if errors:
    state.stale_artifacts.append("02_spec.yaml")
    state.current_stage = "human_required"
```

- [ ] **Step 5: Verify**

```bash
.venv/bin/pytest tests/unit/test_artifact_revisions.py tests/integration/test_stale_artifacts.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Milestone 3: Real Backend Factory, Codex Exec JSONL, And SDK Boundary

**Goal:** Make backend selection production-shaped: fake for tests, `codex exec` as working fallback, SDK behind a clean boundary without model hardcoding.

**Files:**
- Modify: `src/coductor/backends/base.py`
- Create: `src/coductor/backends/factory.py`
- Modify: `src/coductor/backends/codex_exec.py`
- Modify: `src/coductor/backends/codex_sdk.py`
- Modify: `src/coductor/config/models.py`
- Modify: `src/coductor/services/run_service.py`
- Modify: `src/coductor/prompts/renderer.py`
- Test: `tests/unit/test_backend_factory.py`
- Test: `tests/unit/test_codex_exec_backend.py`

- [ ] **Step 1: Write failing backend factory test**

```python
from coductor.backends.codex_exec import CodexExecBackend
from coductor.backends.factory import create_backend
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig


def test_backend_factory_selects_fake() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    assert isinstance(create_backend(config), FakeCodingBackend)


def test_backend_factory_falls_back_to_codex_exec_when_sdk_unavailable() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "codex_sdk"
    config.backend.fallback = "codex_exec"
    backend = create_backend(config, sdk_available=False)
    assert isinstance(backend, CodexExecBackend)
```

- [ ] **Step 2: Write failing `codex exec` command construction test**

```python
def test_codex_exec_uses_explicit_sandbox_and_schema(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex")
    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox="workspace-write",
        output_schema="worker_result",
    )
    assert "exec" in command
    assert "--sandbox" in command
    assert "workspace-write" in command
```

- [ ] **Step 3: Implement factory**

```python
def create_backend(config: CoductorConfig, *, sdk_available: bool | None = None) -> CodingBackend:
    if config.backend.provider == "fake":
        return FakeCodingBackend()
    if config.backend.provider == "codex_exec":
        return CodexExecBackend()
    if config.backend.provider == "codex_sdk" and sdk_available is False:
        return CodexExecBackend()
    return CodexSdkBackend(config.backend)
```

- [ ] **Step 4: Implement `CodexExecBackend.build_command()`**

The command must be list-based and must not use `shell=True`:

```python
return [
    self.codex_bin,
    "exec",
    "--sandbox",
    sandbox,
    "--output-schema",
    output_schema,
    prompt_path.as_posix(),
]
```

- [ ] **Step 5: Verify**

```bash
.venv/bin/pytest tests/unit/test_backend_factory.py tests/unit/test_codex_exec_backend.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

Manual real-backend smoke, only when Codex auth is available:

```bash
.venv/bin/coductor run "只检查项目并生成报告，不修改代码" --backend codex_exec --dry-run
```

---

## Milestone 4: Dynamic Pipeline Strategy

**Goal:** Support sequential multi-task workflows when tasks have real dependencies, without pretending every request is front-end/back-end/test.

**Files:**
- Modify: `src/coductor/planning/planner.py`
- Modify: `src/coductor/planning/validator.py`
- Modify: `src/coductor/artifacts/models.py`
- Modify: `src/coductor/services/run_service.py`
- Modify: `src/coductor/workflow/routers.py`
- Test: `tests/unit/test_strategy_selection.py`
- Test: `tests/integration/test_pipeline_execution.py`

- [ ] **Step 1: Write failing strategy selection tests**

```python
def test_auto_prefers_solo_for_tightly_coupled_goal() -> None:
    decision = choose_strategy("修复同一个函数并补充测试", repo_facts=small_python_repo())
    assert decision.strategy == "solo"


def test_auto_selects_pipeline_for_contract_then_consumer_goal() -> None:
    decision = choose_strategy("先定义 JSON Schema，再让 CLI 输出符合该 Schema", repo_facts=small_python_repo())
    assert decision.strategy == "pipeline"
    assert decision.reasoning
```

- [ ] **Step 2: Write failing pipeline execution test**

```python
def test_pipeline_executes_tasks_in_dependency_order(tmp_path: Path) -> None:
    result = run_pipeline_with_fake_backend(tmp_path, tasks=["T001", "T002"], edges=[["T001", "T002"]])
    events = read_events(tmp_path, result.run_id)
    assert events.index("dispatch T001") < events.index("dispatch T002")
```

- [ ] **Step 3: Implement `choose_strategy()`**

Rules:

```python
if requested_mode in {"solo", "pipeline", "parallel"}:
    return requested_mode
if dependency_markers_detected and task_count > 1:
    return "pipeline"
return "solo"
```

Dependency markers include explicit words such as `先`, `再`, `schema`, `contract`, `OpenAPI`, `上游`, `下游`.

- [ ] **Step 4: Execute pipeline tasks sequentially**

Pipeline execution must:

```python
for task in topological_sort(plan.tasks):
    materialize_task(task)
    dispatch_worker(task)
    run_task_gates(task)
```

- [ ] **Step 5: Verify**

```bash
.venv/bin/pytest tests/unit/test_strategy_selection.py tests/integration/test_pipeline_execution.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Milestone 5: Contract Before Parallelism

**Goal:** Add shared contract artifacts and stale downstream detection before allowing parallel execution.

**Files:**
- Create: `src/coductor/contracts/models.py`
- Create: `src/coductor/contracts/repository.py`
- Modify: `src/coductor/artifacts/models.py`
- Modify: `src/coductor/planning/validator.py`
- Modify: `src/coductor/services/run_service.py`
- Test: `tests/unit/test_contract_artifacts.py`
- Test: `tests/integration/test_contract_stale_downstream.py`

- [ ] **Step 1: Write failing contract artifact test**

```python
def test_contract_file_hash_is_recorded_in_downstream_task(tmp_path: Path) -> None:
    contract = ContractArtifact(path="contracts/api.schema.json", sha256="abc", kind="json_schema")
    task = make_plan_task(consumes=["contracts/api.schema.json"])
    assert contract.path in task.consumes
```

- [ ] **Step 2: Write failing stale downstream test**

```python
def test_downstream_task_becomes_stale_when_contract_hash_changes(tmp_path: Path) -> None:
    run = create_run_with_contract(tmp_path, contract_body='{"type":"object"}')
    mutate_contract(tmp_path, run.run_id, '{"type":"array"}')
    result = resume_run(tmp_path, run.run_id)
    assert result.status == RunStatus.HUMAN_REQUIRED
    assert "stale" in result.message
```

- [ ] **Step 3: Implement contract models**

```python
class ContractArtifact(StrictModel):
    path: str
    kind: Literal["json_schema", "openapi", "event_schema", "type_definition"]
    sha256: str
    producer_task_id: str
```

- [ ] **Step 4: Extend plan validator**

Validator must reject:

```text
downstream task consumes contract path with no producer
parallel task consumes stale contract hash
parallel task writes to contract path produced by another parallel task
```

- [ ] **Step 5: Verify**

```bash
.venv/bin/pytest tests/unit/test_contract_artifacts.py tests/integration/test_contract_stale_downstream.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Milestone 6: Git Worktree Parallel Execution

**Goal:** Allow safe parallel workers only when paths do not overlap and contracts are frozen.

**Files:**
- Modify: `src/coductor/repository/worktree.py`
- Create: `src/coductor/repository/merge.py`
- Modify: `src/coductor/planning/validator.py`
- Modify: `src/coductor/services/run_service.py`
- Modify: `src/coductor/workflow/nodes/integrate.py`
- Test: `tests/unit/test_worktree_manager.py`
- Test: `tests/integration/test_parallel_path_conflict.py`
- Test: `tests/integration/test_parallel_fake_backend.py`

- [ ] **Step 1: Write failing worktree command test**

```python
def test_worktree_manager_builds_safe_paths(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)
    path = manager.path_for("run_abc", "T001")
    assert path.as_posix().endswith(".coductor/worktrees/run_abc/T001")
    assert tmp_path in path.parents
```

- [ ] **Step 2: Write failing conflict test**

```python
def test_parallel_plan_with_overlapping_paths_is_human_required(tmp_path: Path) -> None:
    plan = make_parallel_plan(paths=[["src/**"], ["src/coductor/**"]])
    result = validate_and_run_plan(tmp_path, plan)
    assert result.status == RunStatus.HUMAN_REQUIRED
```

- [ ] **Step 3: Implement worktree lifecycle**

`WorktreeManager` must expose:

```python
def create(self, run_id: str, task_id: str, base_ref: str) -> Path: ...
def remove(self, run_id: str, task_id: str) -> None: ...
def diff(self, run_id: str, task_id: str) -> Path: ...
```

Commands must be list-based:

```python
["git", "worktree", "add", path.as_posix(), base_ref]
```

- [ ] **Step 4: Implement integration report**

`04_integration.yaml` must record:

```yaml
data:
  status: merged
  merged_tasks:
    - T001
    - T002
  conflicts: []
```

- [ ] **Step 5: Verify**

```bash
.venv/bin/pytest tests/unit/test_worktree_manager.py tests/integration/test_parallel_path_conflict.py tests/integration/test_parallel_fake_backend.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Milestone 7: CLI Control Plane And Observability

**Goal:** Implement the remaining user-facing commands and make run state inspectable without reading raw directories.

**Files:**
- Modify: `src/coductor/cli.py`
- Modify: `src/coductor/storage/database.py`
- Modify: `src/coductor/storage/events.py`
- Create: `src/coductor/services/report_service.py`
- Modify: `src/coductor/services/evidence_service.py`
- Test: `tests/integration/test_cli_commands.py`

- [ ] **Step 1: Write failing CLI command test**

```python
def test_cli_artifacts_lists_yaml_files(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(app, ["artifacts", "run_abc"])
    assert result.exit_code == 0
    assert "00_goal.yaml" in result.output
```

- [ ] **Step 2: Add commands**

Implement:

```text
approve
pause
stop
verify
review
artifacts
logs
explain
```

Each command must include stage, run id, recoverability, and next command when it fails.

- [ ] **Step 3: Add event query APIs**

`Database` should expose:

```python
def list_events(self, run_id: str) -> list[dict[str, str]]: ...
def update_run_status(self, run_id: str, status: str) -> None: ...
```

- [ ] **Step 4: Verify**

```bash
.venv/bin/pytest tests/integration/test_cli_commands.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Milestone 8: Review, Evidence, And Delivery Hardening

**Goal:** Make delivery status strictly evidence-based and produce human-ready reports.

**Files:**
- Modify: `src/coductor/artifacts/models.py`
- Modify: `src/coductor/services/evidence_service.py`
- Modify: `src/coductor/workflow/nodes/review.py`
- Modify: `src/coductor/workflow/nodes/deliver.py`
- Modify: `docs/yaml-contracts.md`
- Test: `tests/unit/test_evidence_service.py`
- Test: `tests/integration/test_blocking_review.py`

- [ ] **Step 1: Write failing evidence gating test**

```python
def test_evidence_is_not_ready_when_review_has_blocking_finding(tmp_path: Path) -> None:
    evidence = build_evidence_with(blocking_findings=1, required_gates_passed=True)
    assert evidence.final_status == "human_required"
```

- [ ] **Step 2: Write failing missing evidence test**

```python
def test_evidence_requires_patch_and_gate_report() -> None:
    result = EvidenceCompletenessValidator().validate(evidence_without_patch())
    assert not result.valid
    assert "patch" in result.errors[0]
```

- [ ] **Step 3: Implement completeness validator**

```python
class EvidenceCompletenessValidator:
    def validate(self, evidence: EvidenceBundleData) -> EvidenceValidation:
        errors = []
        if evidence.gate_summary.failed > 0:
            errors.append("required gates failed")
        if evidence.review_summary.blocking_findings > 0:
            errors.append("blocking review findings exist")
        if not any(item.type == "patch" for item in evidence.evidence_files):
            errors.append("missing patch evidence")
        return EvidenceValidation(valid=not errors, errors=errors)
```

- [ ] **Step 4: Verify**

```bash
.venv/bin/pytest tests/unit/test_evidence_service.py tests/integration/test_blocking_review.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Milestone 9: Documentation, Demo, And Release Readiness

**Goal:** Keep docs and examples aligned with actual behavior, not future claims.

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/workflow.md`
- Modify: `docs/security.md`
- Modify: `docs/yaml-contracts.md`
- Modify: `docs/glossary.md`
- Modify: `examples/demo-python-project/*`
- Test: `tests/e2e/test_demo_project.py`

- [ ] **Step 1: Write failing E2E test**

```python
def test_demo_project_generates_complete_evidence(tmp_path: Path) -> None:
    demo = copy_demo_project(tmp_path)
    run = invoke_coductor(demo, "修复示例函数并补充测试", backend="fake")
    assert run.status == "ready_for_human_review"
    assert (demo / ".coductor" / "runs" / run.run_id / "07_evidence.yaml").exists()
```

- [ ] **Step 2: Update docs from actual commands**

Every README command must be run with `.venv/bin/coductor` before documenting output.

- [ ] **Step 3: Verify**

```bash
.venv/bin/pytest tests/e2e/test_demo_project.py -q
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

---

## Recommended Execution Order

1. Milestone 1: Real LangGraph runtime and resume.
2. Milestone 2: Artifact revision, idempotency, stale detection.
3. Milestone 3: Backend factory and real `codex exec`.
4. Milestone 4: Dynamic pipeline.
5. Milestone 5: Contract before parallelism.
6. Milestone 6: Worktree parallel.
7. Milestone 7: CLI control plane.
8. Milestone 8: Evidence hardening.
9. Milestone 9: Docs, demo, release readiness.

## Stop Rules

Stop and ask before proceeding if:

- dependency installation requires a new network/proxy assumption;
- Codex auth is missing and a task requires real backend verification;
- Git worktree commands would mutate a user-owned repository in a risky way;
- a migration changes existing artifact fields incompatibly;
- required gates fail twice with the same fingerprint.

## Final Verification For Every Milestone

```bash
.venv/bin/python -m pip check
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/coductor doctor
```

