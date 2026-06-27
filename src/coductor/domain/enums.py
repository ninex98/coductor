"""Shared enumerations used by contracts and services."""

from __future__ import annotations

from enum import StrEnum


class ExecutionMode(StrEnum):
    AUTO = "auto"
    SOLO = "solo"
    PIPELINE = "pipeline"
    PARALLEL = "parallel"


class ExecutionStrategy(StrEnum):
    SOLO = "solo"
    PIPELINE = "pipeline"
    PARALLEL = "parallel"


class ArtifactType(StrEnum):
    GOAL = "goal"
    REPOSITORY_SNAPSHOT = "repository_snapshot"
    SPECIFICATION = "specification"
    EXECUTION_PLAN = "execution_plan"
    TASK = "task"
    WORKER_REQUEST = "worker_request"
    WORKER_RESULT = "worker_result"
    INTEGRATION = "integration"
    GATE_REPORT = "gate_report"
    REPAIR_REQUEST = "repair_request"
    REPAIR_RESULT = "repair_result"
    REVIEW_REPORT = "review_report"
    EVIDENCE_BUNDLE = "evidence_bundle"
    RELEASE_MANIFEST = "release_manifest"


class ArtifactStatus(StrEnum):
    ACCEPTED = "accepted"
    COMPLETE = "complete"
    APPROVED = "approved"
    VALIDATED = "validated"
    READY = "ready"
    COMPLETED = "completed"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    HUMAN_REQUIRED = "human_required"


class ProducerKind(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    MODEL = "model"
    TOOL = "tool"


class VerificationType(StrEnum):
    AUTOMATED = "automated"
    MANUAL = "manual"


class SandboxMode(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"


class TaskType(StrEnum):
    INTEGRATED_IMPLEMENTATION = "integrated_implementation"
    CONTRACT_AUTHORING = "contract_authoring"
    VERIFICATION = "verification"


class WorkerStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    HUMAN_REQUIRED = "human_required"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
