"""Configuration models for managed repositories."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from coductor.domain.enums import ExecutionMode


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ProjectConfig(ConfigModel):
    name: str = "coductor-managed-project"
    root: str = "."
    default_branch: str = "main"


class BackendConfig(ConfigModel):
    provider: str = "codex_sdk"
    model: str | None = None
    reasoning_effort: str | None = None
    fallback: str = "codex_exec"


class WorkflowConfig(ConfigModel):
    default_mode: ExecutionMode = ExecutionMode.AUTO
    max_repair_attempts: int = 2
    max_parallel_workers: int = 2
    require_spec_approval: bool = False
    require_plan_approval_for_parallel: bool = True


class PermissionConfig(ConfigModel):
    network_access: bool = False
    allow_git_commit: bool = False
    allow_git_push: bool = False
    allow_pull_request: bool = False
    protected_paths: list[str] = Field(
        default_factory=lambda: [".env*", "**/secrets/**", "**/production/**"]
    )


class RepositoryConfig(ConfigModel):
    ignore: list[str] = Field(
        default_factory=lambda: [
            ".git/**",
            ".coductor/**",
            "node_modules/**",
            ".venv/**",
            "vendor/**",
        ]
    )


class QualityGateConfig(ConfigModel):
    id: str
    stage: str = "final"
    command: str
    required: bool = True
    timeout_seconds: int = 300


class BudgetConfig(ConfigModel):
    max_run_minutes: int = 45
    max_worker_turns: int = 8
    max_repair_attempts: int = 2


class CoductorConfig(ConfigModel):
    schema_version: str = "1.0"
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    backend: BackendConfig = Field(default_factory=BackendConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    permissions: PermissionConfig = Field(default_factory=PermissionConfig)
    repository: RepositoryConfig = Field(default_factory=RepositoryConfig)
    quality_gates: list[QualityGateConfig] = Field(
        default_factory=lambda: [
            QualityGateConfig(id="unit_tests", command="pytest -q", timeout_seconds=300),
            QualityGateConfig(id="lint", command="ruff check .", timeout_seconds=120),
        ]
    )
    budgets: BudgetConfig = Field(default_factory=BudgetConfig)

    @classmethod
    def default(cls) -> CoductorConfig:
        return cls()
