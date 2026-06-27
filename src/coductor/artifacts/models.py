"""Pydantic models for YAML artifact contracts."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from coductor.contracts.models import ContractArtifact
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ExecutionStrategy,
    ProducerKind,
    SandboxMode,
    TaskType,
    VerificationType,
)

DataT = TypeVar("DataT", bound=BaseModel)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Producer(StrictModel):
    kind: ProducerKind
    name: str


class ArtifactInput(StrictModel):
    artifact_type: ArtifactType
    path: str
    revision: int
    sha256: str


class ArtifactMetadata(StrictModel):
    content_sha256: str = ""


class ArtifactEnvelope(StrictModel, Generic[DataT]):  # noqa: UP046
    schema_version: Literal["1.0"] = "1.0"
    artifact_type: ArtifactType
    artifact_id: str
    run_id: str
    revision: int = Field(ge=1)
    status: ArtifactStatus | str
    created_at: str
    producer: Producer
    inputs: list[ArtifactInput] = Field(default_factory=list)
    metadata: ArtifactMetadata = Field(default_factory=ArtifactMetadata)
    data: DataT


class GoalData(StrictModel):
    title: str
    raw_request: str
    goal_type: str
    requested_mode: ExecutionMode
    target_repository: str = "."
    user_constraints: list[str] = Field(default_factory=list)


class RepositoryManifest(StrictModel):
    path: str
    sha256: str


class DiscoveredCommands(StrictModel):
    test: list[str] = Field(default_factory=list)
    lint: list[str] = Field(default_factory=list)
    typecheck: list[str] = Field(default_factory=list)
    build: list[str] = Field(default_factory=list)


class RepositorySnapshotData(StrictModel):
    base_commit: str
    dirty_worktree: bool
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    manifests: list[RepositoryManifest] = Field(default_factory=list)
    relevant_paths: list[str] = Field(default_factory=list)
    discovered_commands: DiscoveredCommands = Field(default_factory=DiscoveredCommands)
    existing_documents: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class Assumption(StrictModel):
    id: str
    statement: str
    confidence: Literal["low", "medium", "high"]
    requires_human_confirmation: bool = False


class AcceptanceCriterion(StrictModel):
    id: str
    statement: str
    verification: VerificationType
    priority: Literal["required", "optional"] = "required"


class Approval(StrictModel):
    required: bool = False
    approved_by: str | None = None


class SpecificationData(StrictModel):
    objective: str
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    approval: Approval = Field(default_factory=Approval)


class PlanTask(StrictModel):
    id: str
    title: str
    task_type: TaskType
    role: str
    depends_on: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    quality_gates: list[str] = Field(default_factory=list)
    sandbox: SandboxMode


class PlanValidation(StrictModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExecutionPlanData(StrictModel):
    strategy: ExecutionStrategy
    strategy_reasoning: list[str]
    base_commit: str
    tasks: list[PlanTask]
    graph: dict[str, Any] = Field(default_factory=lambda: {"edges": []})
    approval: Approval = Field(default_factory=Approval)
    validation: PlanValidation = Field(default_factory=PlanValidation)


class TaskData(StrictModel):
    task_id: str
    objective: str
    role: str
    depends_on: list[str] = Field(default_factory=list)
    global_context: list[str] = Field(default_factory=list)
    upstream_artifacts: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    contracts: list[ContractArtifact] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    quality_gates: list[str] = Field(default_factory=list)


class WorkerRequestData(StrictModel):
    worker_id: str
    backend: str
    thread_policy: Literal["new", "resume"] = "new"
    existing_thread_id: str | None = None
    role: str
    sandbox: SandboxMode
    approval_policy: str = "on_request"
    network_access: bool = False
    workspace_path: str = "."
    prompt_template: str
    context_artifacts: list[str] = Field(default_factory=list)
    output_schema: str
    timeout_seconds: int = 1800


class FileReference(StrictModel):
    path: str
    sha256: str
    bytes: int


class WorkerUsage(StrictModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    estimated: bool = True
    estimated_cost_usd: float | None = None


class WorkerResultData(StrictModel):
    worker_id: str
    thread_id: str
    task_id: str
    summary: str
    files_read: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    tests_claimed: list[str] = Field(default_factory=list)
    generated_artifacts: list[str] = Field(default_factory=list)
    patch: FileReference
    unresolved_issues: list[str] = Field(default_factory=list)
    usage: WorkerUsage = Field(default_factory=WorkerUsage)
    exit_reason: str = "completed"


class IntegrationData(StrictModel):
    status: str
    reason: str
    merged_tasks: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    worktree_diffs: list[FileReference] = Field(default_factory=list)


class GateResultData(StrictModel):
    id: str
    required: bool
    status: Literal["passed", "failed", "skipped", "timeout"]
    command: str
    exit_code: int | None
    duration_ms: int
    stdout_path: str
    stderr_path: str
    failure_fingerprint: str | None = None


class AcceptanceCoverage(StrictModel):
    criterion_id: str
    status: Literal["passed", "failed", "manual"]
    evidence: list[str] = Field(default_factory=list)


class GateReportData(StrictModel):
    scope: str = "final"
    base_commit: str
    head_commit: str
    gates: list[GateResultData] = Field(default_factory=list)
    acceptance_coverage: list[AcceptanceCoverage] = Field(default_factory=list)
    required_gates_passed: bool
    next_action: Literal["review", "repair", "human_required"]


class RepairRequestData(StrictModel):
    repair_id: str
    target_task_id: str
    resume_thread_id: str | None
    attempt: int
    max_attempts: int
    failed_gates: list[str]
    failure_fingerprints: list[str]
    evidence_paths: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    instruction: str = "只修复导致当前 Gate 失败的最小范围，不进行无关重构。"


class Finding(StrictModel):
    id: str
    severity: Literal["low", "medium", "high", "critical"]
    category: str
    file: str | None = None
    line: int | None = None
    description: str
    recommendation: str


class ReviewReportData(StrictModel):
    reviewer_thread_id: str
    reviewed_base_commit: str
    reviewed_head_commit: str
    findings: list[Finding] = Field(default_factory=list)
    blocking_findings: int = 0
    verdict: Literal["pass", "fail"] = "pass"
    requires_repair: bool = False
    usage: WorkerUsage = Field(default_factory=WorkerUsage)

    @field_validator("blocking_findings")
    @classmethod
    def blocking_findings_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("blocking_findings must be non-negative")
        return value


class GateSummary(StrictModel):
    required: int
    passed: int
    failed: int


class ReviewSummary(StrictModel):
    blocking_findings: int


class Rollback(StrictModel):
    method: str
    instructions: str


class PullRequestInfo(StrictModel):
    created: bool = False
    title: str = ""
    body_path: str = "delivery-report.md"


class EvidenceFile(StrictModel):
    type: str
    path: str
    sha256: str


class EvidenceValidation(StrictModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)


class EvidenceBundleData(StrictModel):
    goal_title: str
    final_status: str
    strategy_used: ExecutionStrategy
    base_commit: str
    head_commit: str
    completed_tasks: list[str] = Field(default_factory=list)
    acceptance_results: list[AcceptanceCoverage] = Field(default_factory=list)
    gate_summary: GateSummary
    review_summary: ReviewSummary
    usage_summary: WorkerUsage = Field(default_factory=WorkerUsage)
    evidence_files: list[EvidenceFile] = Field(default_factory=list)
    validation: EvidenceValidation = Field(default_factory=EvidenceValidation)
    known_risks: list[str] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    rollback: Rollback
    pull_request: PullRequestInfo = Field(default_factory=PullRequestInfo)
