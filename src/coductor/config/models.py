"""Configuration models for managed repositories."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coductor.domain.enums import ExecutionMode


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ProjectConfig(ConfigModel):
    name: str = "coductor-managed-project"
    root: str = "."
    default_branch: str = "main"


class BackendConfig(ConfigModel):
    provider: str = "codex_exec"
    model: str | None = None
    reasoning_effort: str | None = None
    fallback: str = "codex_exec"


class WorkflowConfig(ConfigModel):
    default_mode: ExecutionMode = ExecutionMode.AUTO
    max_repair_attempts: int = 2
    max_parallel_workers: int = 2
    require_spec_approval: bool = False
    require_plan_approval_for_parallel: bool = True
    repair_after_blocking_review: bool = False


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


class BrowserCheckConfig(ConfigModel):
    url: str | None = None
    static_path: str | None = None
    start_command: str | None = None
    ready_timeout_seconds: int = 30
    viewport_width: int = 1280
    viewport_height: int = 720
    selectors: list[str] = Field(default_factory=lambda: ["body"])
    text: list[str] = Field(default_factory=list)
    fail_on_console_error: bool = True
    screenshot: bool = True


class ImageGenerationConfig(ConfigModel):
    prompt: str = ""
    purpose: str = ""
    output_path: str = "assets/generated/image.png"
    width: int = Field(default=1024, ge=1)
    height: int = Field(default=1024, ge=1)
    candidate_count: int = Field(default=1, ge=1)
    batch_approved: bool = False
    reference_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def batch_requires_approval(self) -> ImageGenerationConfig:
        if self.candidate_count > 1 and not self.batch_approved:
            raise ValueError("batch image requests require batch_approved=true")
        return self


class ToolCheckConfig(ConfigModel):
    id: str
    tool: str = "command"
    command: str = ""
    required: bool = True
    timeout_seconds: int = 300
    description: str = ""
    criterion_ids: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    browser: BrowserCheckConfig = Field(default_factory=BrowserCheckConfig)
    image: ImageGenerationConfig = Field(default_factory=ImageGenerationConfig)


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
    tool_checks: list[ToolCheckConfig] = Field(default_factory=list)
    budgets: BudgetConfig = Field(default_factory=BudgetConfig)

    @classmethod
    def default(cls) -> CoductorConfig:
        return cls()
