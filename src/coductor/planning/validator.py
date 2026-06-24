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
                if self._is_contract_path(consumed) and not self._has_upstream_contract_producer(
                    plan, task.id, consumed
                ):
                    errors.append(
                        f"task {task.id} consumes contract {consumed} without upstream producer"
                    )
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
        contract_writers: dict[str, str] = {}
        for left_index, left in enumerate(tasks):
            for produced in left.produces:
                if not self._is_contract_path(produced):
                    continue
                previous = contract_writers.get(produced)
                if previous is not None:
                    errors.append(
                        f"parallel contract writer conflict for {produced}: "
                        f"{previous} and {left.id}"
                    )
                contract_writers[produced] = left.id
            for right in tasks[left_index + 1 :]:
                for left_path in left.allowed_paths:
                    for right_path in right.allowed_paths:
                        if paths_overlap(left_path, right_path):
                            errors.append(
                                "parallel path overlap between "
                                f"{left.id}:{left_path} and {right.id}:{right_path}"
                            )
                for produced in left.produces:
                    if self._is_contract_path(produced) and produced in right.consumes:
                        errors.append(
                            f"parallel contract handoff is not allowed for {produced}: "
                            f"{left.id} -> {right.id}"
                        )
                for produced in right.produces:
                    if self._is_contract_path(produced) and produced in left.consumes:
                        errors.append(
                            f"parallel contract handoff is not allowed for {produced}: "
                            f"{right.id} -> {left.id}"
                        )
        if len(plan.strategy_reasoning) < 2:
            errors.append(
                "parallel strategy requires explicit benefit and stable-contract reasoning"
            )
        return errors

    def _has_upstream_contract_producer(
        self,
        plan: ExecutionPlanData,
        task_id: str,
        contract_path: str,
    ) -> bool:
        tasks = {task.id: task for task in plan.tasks}
        visited: set[str] = set()

        def produced_by_dependency(current_id: str) -> bool:
            task = tasks[current_id]
            for dependency_id in task.depends_on:
                if dependency_id in visited or dependency_id not in tasks:
                    continue
                visited.add(dependency_id)
                dependency = tasks[dependency_id]
                if contract_path in dependency.produces:
                    return True
                if produced_by_dependency(dependency_id):
                    return True
            return False

        if task_id not in tasks:
            return False
        return produced_by_dependency(task_id)

    def _is_contract_path(self, path: str) -> bool:
        return path.startswith("contracts/")


def paths_overlap(left: str, right: str) -> bool:
    left_prefix = left.replace("**", "").rstrip("/*")
    right_prefix = right.replace("**", "").rstrip("/*")
    if not left_prefix or not right_prefix:
        return True
    return left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix)
