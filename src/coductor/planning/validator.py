"""Deterministic execution plan validation."""

from __future__ import annotations

from coductor.artifacts.models import AcceptanceCriterion, ExecutionPlanData, PlanValidation
from coductor.domain.enums import ExecutionStrategy


class PlanValidator:
    def __init__(
        self,
        *,
        acceptance_criteria: list[AcceptanceCriterion],
        produced_artifacts: set[str],
    ) -> None:
        self.acceptance_criteria = acceptance_criteria
        self.produced_artifacts = produced_artifacts

    def validate(self, plan: ExecutionPlanData) -> PlanValidation:
        errors: list[str] = []
        warnings: list[str] = []
        ids = [task.id for task in plan.tasks]
        id_set = set(ids)
        if len(ids) != len(id_set):
            errors.append("task ids must be unique")
        for task in plan.tasks:
            for dependency in task.depends_on:
                if dependency not in id_set:
                    errors.append(f"task {task.id} depends on unknown task {dependency}")
            for consumed in task.consumes:
                if consumed not in self.produced_artifacts:
                    errors.append(f"task {task.id} consumes unknown artifact {consumed}")
        if self._has_cycle(plan):
            errors.append("task dependency graph contains a cycle")
        covered = {criterion for task in plan.tasks for criterion in task.acceptance_criteria}
        for criterion in self.acceptance_criteria:
            if criterion.priority == "required" and criterion.id not in covered:
                errors.append(f"required acceptance criterion {criterion.id} is not covered")
        if plan.strategy == ExecutionStrategy.PARALLEL:
            errors.extend(self._parallel_errors(plan))
        if plan.strategy == ExecutionStrategy.SOLO and len(plan.tasks) > 1:
            warnings.append("solo strategy normally uses one integrated task")
        return PlanValidation(valid=not errors, errors=errors, warnings=warnings)

    def _has_cycle(self, plan: ExecutionPlanData) -> bool:
        graph = {task.id: set(task.depends_on) for task in plan.tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> bool:
            if task_id in visiting:
                return True
            if task_id in visited:
                return False
            visiting.add(task_id)
            for dependency in graph.get(task_id, set()):
                if visit(dependency):
                    return True
            visiting.remove(task_id)
            visited.add(task_id)
            return False

        return any(visit(task_id) for task_id in graph)

    def _parallel_errors(self, plan: ExecutionPlanData) -> list[str]:
        errors: list[str] = []
        tasks = plan.tasks
        for left_index, left in enumerate(tasks):
            for right in tasks[left_index + 1 :]:
                for left_path in left.allowed_paths:
                    for right_path in right.allowed_paths:
                        if paths_overlap(left_path, right_path):
                            errors.append(
                                "parallel path overlap between "
                                f"{left.id}:{left_path} and {right.id}:{right_path}"
                            )
        if len(plan.strategy_reasoning) < 2:
            errors.append(
                "parallel strategy requires explicit benefit and stable-contract reasoning"
            )
        return errors


def paths_overlap(left: str, right: str) -> bool:
    left_prefix = left.replace("**", "").rstrip("/*")
    right_prefix = right.replace("**", "").rstrip("/*")
    if not left_prefix or not right_prefix:
        return True
    return left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix)
