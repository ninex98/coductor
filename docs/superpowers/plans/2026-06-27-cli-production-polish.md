# CLI Production Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first production-polish batch for Coductor CLI: terminal startup identity, real dry-run artifacts, watchable status, repair patch evidence, and backend doctor diagnostics.

**Architecture:** Keep the fixed YAML artifact chain as the source of truth. Add small CLI helpers and service methods rather than changing the core graph contract. Repair patch capture should reuse the existing workspace snapshot/diff approach so evidence semantics stay consistent with builder patches.

**Tech Stack:** Python 3.12, Typer/Rich fallback, Pydantic YAML artifacts, SQLite run index, pytest, ruff, mypy.

---

### Task 1: CLI Startup Identity

**Files:**
- Modify: `src/coductor/cli.py`
- Test: `tests/integration/test_cli_commands.py`

- [x] Add a failing CLI test asserting `coductor` with no subcommand prints an elephant mark, `CODUCTOR`, slogan, and common commands.
- [x] Implement startup text as terminal output only, with ASCII-compatible art and graceful no-Rich behavior.
- [x] Verify the CLI test passes.

### Task 2: Real Dry Run

**Files:**
- Modify: `src/coductor/services/run_service.py`
- Modify: `src/coductor/cli.py`
- Test: `tests/integration/test_cli_commands.py`

- [x] Add a failing CLI test asserting `coductor run --dry-run` writes `00_goal.yaml`, `01_repository_snapshot.yaml`, `02_spec.yaml`, `03_execution_plan.yaml`, and no worker artifacts.
- [x] Implement `RunService.dry_run()` using existing artifact writer methods and run/checkpoint/event storage.
- [x] Print the run id, plan artifact, and next commands from CLI.
- [x] Verify the dry-run test passes.

### Task 3: Watchable Status

**Files:**
- Modify: `src/coductor/cli.py`
- Test: `tests/integration/test_cli_commands.py`

- [x] Add a failing test for `status --watch` using a short interval and max iteration guard.
- [x] Implement bounded watch parameters internally so tests do not hang, while CLI defaults can keep polling.
- [x] Verify the status watch test passes.

### Task 4: Repair Patch Evidence

**Files:**
- Modify: `src/coductor/services/repair_service.py`
- Test: `tests/unit/test_repair_service.py`

- [x] Add a failing test asserting repair patch contains the real changed file diff and not `fake repair result`.
- [x] Capture workspace snapshot before repair, run repair worker, then write a real diff using existing task execution diff helpers.
- [x] Verify repair tests pass.

### Task 5: Backend Doctor Diagnostics

**Files:**
- Modify: `src/coductor/cli.py`
- Test: `tests/integration/test_cli_commands.py`

- [x] Add a failing test asserting `doctor` reports configured backend provider, resolved codex executable, and SDK availability.
- [x] Implement lightweight diagnostics without making network calls.
- [x] Verify doctor tests pass.

### Task 6: Full Verification

**Files:**
- No new files expected.

- [x] Run targeted CLI, repair, backend tests.
- [x] Run full `pytest`.
- [x] Run `ruff check .`.
- [x] Run `mypy src`.

### Additional Completed Production Hardening

- [x] Add SQLite run locks with owner checks, stale-lock takeover, and resume/control/release integration.
- [x] Add spec approval stop/resume flow when `workflow.require_spec_approval` is enabled.
- [x] Make repair resume idempotent when repair artifacts already exist.
- [x] Add backend capability diagnostics for fake, codex_exec, and codex_sdk providers.
- [x] Add `coductor release <run_id>` to generate `08_release_manifest.yaml` without git push or PR side effects.
- [x] Improve project discovery for Python and Node/TypeScript gates using configured tools, scripts, and lockfiles.
- [x] Run final verification: `pytest`, `ruff check .`, `mypy src`, and `python -m pip check`.
