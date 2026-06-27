# Local Web Console Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an optional localhost Web console for Coductor that makes runs, artifacts, logs, evidence, release manifests, and safe human controls production-usable without replacing the CLI or YAML artifact contract.

**Architecture:** Add a Python local web layer under `src/coductor/web/` with typed read/control services, a Python standard-library HTTP runtime, and package-local static UI assets. The web layer reads `.coductor/coductor.sqlite3` and `.coductor/runs/**`, and all state-changing actions reuse existing `RunService`, `ReportService`, `ReleaseService`, database locks, and YAML Artifact repositories. The CLI remains the core workflow entrypoint; `coductor serve` is an optional local control plane bound to loopback by default.

**Tech Stack:** Python 3.12, standard-library HTTP server, Pydantic v2, SQLite, existing YAML Artifact models, static HTML/CSS/JS, pytest, ruff, mypy, pip check, and localhost smoke verification.

---

## Design Reference

Primary design document:

- `docs/superpowers/specs/2026-06-27-local-web-console-design.md`

Key invariants from the design:

- YAML Artifact remains the downstream source of truth.
- Web does not create a second state store.
- Web listens on `127.0.0.1` by default.
- Non-loopback host requires `--allow-lan`.
- No remote git writes, PR creation, network execution, arbitrary shell execution, or secrets exposure.
- Control actions must reuse existing service and lock behavior.

## File Structure

Create:

- `src/coductor/web/__init__.py`
  Package marker.

- `src/coductor/web/schemas.py`
  Pydantic models for API responses and console view models.

- `src/coductor/web/paths.py`
  Path normalization, run directory containment checks, suffix allowlist, and preview size logic.

- `src/coductor/web/read_service.py`
  Read-only facade over `Database`, `ArtifactRepository`, run directories, logs, reports, evidence, and release manifest.

- `src/coductor/web/control_service.py`
  Safe action facade over existing CLI/service operations.

- `src/coductor/web/app.py`
  Framework-free app factory, API route dispatcher, static asset handling, error wrapper.

- `src/coductor/web/server.py`
  Host/port validation, standard-library HTTP server startup, optional browser open.

- `src/coductor/web/static/index.html`
  Console shell.

- `src/coductor/web/static/styles.css`
  Production-style local console layout.

- `src/coductor/web/static/app.js`
  No-build frontend application.

- `tests/unit/test_web_paths.py`

- `tests/unit/test_web_read_service.py`

- `tests/integration/test_web_api.py`

- `tests/integration/test_web_controls.py`

- `tests/integration/test_cli_serve.py`

Modify:

- `src/coductor/cli.py`
  Add `serve` command and help entry.

- `src/coductor/services/report_service.py` or new shared helper
  Extract any CLI-private control action logic that Web must reuse without duplicating state transitions.

- `README.md`
  Document `coductor serve`, local-only security posture, and standard install behavior.

- `docs/security.md`
  Add local web console boundary and LAN warning.

## Task 1: Standard-Library Web Server And CLI Surface

**Files:**

- Modify: `src/coductor/cli.py`
- Create: `src/coductor/web/__init__.py`
- Create: `src/coductor/web/server.py`
- Test: `tests/integration/test_cli_serve.py`

- [ ] **Step 1: Write failing test for CLI help**

Add a test that invokes `coductor --help` and asserts `serve` appears with bilingual description.

Run:

```bash
.venv/bin/pytest tests/integration/test_cli_serve.py::test_cli_help_lists_serve_command -q
```

Expected before implementation: fail because `serve` is not registered.

- [ ] **Step 2: Write failing test for non-loopback host guard**

Add a test that invokes `coductor serve --host 0.0.0.0 --port 8765 --dry-run-server-check` and expects exit code `1` unless `--allow-lan` is supplied. If a dry-check flag feels awkward, implement a small internal function `validate_serve_options(host, allow_lan)` and test it directly in `tests/integration/test_cli_serve.py`.

Expected before implementation: fail because validation does not exist.

- [ ] **Step 3: Keep runtime dependency-free**

Do not add FastAPI/Uvicorn or a Node build chain for the first implementation. `coductor serve` should run with the base package dependencies already used by the CLI.

- [ ] **Step 4: Implement `coductor serve` CLI registration**

Add command:

```bash
coductor serve --host 127.0.0.1 --port 8765 --open
```

Behavior:

- Default host `127.0.0.1`.
- Default port `8765`.
- `--allow-lan` required for any non-loopback host.
- Startup should print the local URL, project root, and loopback/LAN safety hint.

- [ ] **Step 5: Verify target tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_cli_serve.py -q
```

Expected after implementation: pass.

## Task 2: Safe Path Handling

**Files:**

- Create: `src/coductor/web/paths.py`
- Test: `tests/unit/test_web_paths.py`

- [ ] **Step 1: Write failing tests for path safety**

Cover:

- `00_goal.yaml` inside run_dir is allowed.
- `logs/unit_tests.stdout.log` inside run_dir is allowed.
- `../coductor.yaml` is rejected.
- Absolute paths are rejected.
- Symlink escape is rejected if symlink exists.
- Unsupported suffix such as `.sqlite3` is rejected.

Run:

```bash
.venv/bin/pytest tests/unit/test_web_paths.py -q
```

Expected before implementation: fail.

- [ ] **Step 2: Implement path resolver**

Implement:

```python
ALLOWED_PREVIEW_SUFFIXES = {".yaml", ".yml", ".log", ".md", ".diff", ".patch", ".txt"}
MAX_PREVIEW_BYTES = 512_000

def resolve_run_file(run_dir: Path, requested_path: str) -> Path:
    if Path(requested_path).is_absolute():
        raise ConsolePathError("absolute paths are not allowed")
    candidate = (run_dir / requested_path).resolve()
    root = run_dir.resolve()
    if root != candidate and root not in candidate.parents:
        raise ConsolePathError("path escapes run directory")
    if candidate.suffix not in ALLOWED_PREVIEW_SUFFIXES:
        raise ConsolePathError(f"unsupported file suffix: {candidate.suffix}")
    return candidate

def read_text_preview(path: Path) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = len(data) > MAX_PREVIEW_BYTES
    return data[:MAX_PREVIEW_BYTES].decode("utf-8", "replace"), truncated
```

Rules:

- Reject absolute paths.
- Reject `..` traversal.
- Resolve symlinks and ensure final path is inside `run_dir`.
- Reject unsupported suffix.
- Return truncated preview flag when file is larger than threshold.

- [ ] **Step 3: Verify path tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_web_paths.py -q
```

Expected: pass.

## Task 3: Typed Console Schemas

**Files:**

- Create: `src/coductor/web/schemas.py`
- Test: `tests/unit/test_web_read_service.py`

- [ ] **Step 1: Define response envelope models**

Add:

```python
class ConsoleError(BaseModel):
    message: str
    recoverable: bool = True
    next_command: str | None = None

class ConsoleResponse(BaseModel, Generic[DataT]):
    ok: bool
    data: DataT | None = None
    error: ConsoleError | None = None
```

- [ ] **Step 2: Define run and artifact view models**

Add:

- `ConsoleRunSummary`
- `ConsoleCheckpointSummary`
- `ConsoleRunDetail`
- `ConsoleArtifactSummary`
- `ConsoleArtifactDetail`
- `ConsoleEvent`
- `ConsoleDoctorReport`
- `ConsoleActionResult`

Required fields:

- Run summary: run_id, status, run_dir, updated_at, current_stage, last_error.
- Artifact summary: path, artifact_type, status, revision, sha256, producer.
- Artifact detail: summary fields plus parsed_yaml, raw_text, truncated, inputs.

- [ ] **Step 3: Validate with mypy**

Run:

```bash
.venv/bin/mypy src/coductor/web/schemas.py
```

Expected: no issues.

## Task 4: Read-only Console Service

**Files:**

- Create: `src/coductor/web/read_service.py`
- Test: `tests/unit/test_web_read_service.py`

- [ ] **Step 1: Write failing run list test**

Seed `.coductor/coductor.sqlite3` with two runs. Assert `ConsoleReadService.list_runs()` returns newest first with checkpoint current_stage when available.

- [ ] **Step 2: Write failing artifact list/detail tests**

Use an existing test helper or create minimal valid ArtifactEnvelope files. Assert:

- `list_artifacts(run_id)` includes fixed YAML files.
- `get_artifact(run_id, "07_evidence.yaml")` returns raw text, parsed YAML, revision, inputs, sha.
- invalid paths raise a recoverable service error.

- [ ] **Step 3: Write failing report/events tests**

Assert:

- `get_events(run_id, stage=None, tail=20)` delegates filter/tail semantics to `ReportService.log_events`.
- `get_report(run_id)` reads `delivery-report.md` when present and returns a clear recoverable error otherwise.

- [ ] **Step 4: Implement `ConsoleReadService`**

Constructor:

```python
class ConsoleReadService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.db = Database(root / CODUCTOR_DIR / "coductor.sqlite3")
```

Methods:

- `list_runs(status: str | None = None, limit: int = 50)`.
- `get_run(run_id: str)`.
- `get_events(run_id: str, stage: str | None = None, tail: int | None = None)`.
- `list_artifacts(run_id: str)`.
- `get_artifact(run_id: str, path: str)`.
- `get_report(run_id: str)`.
- `get_log(run_id: str, path: str)`.
- `doctor()`.

If `Database` lacks list-runs support, add `Database.list_runs(status=None, limit=50)` with unit coverage.

- [ ] **Step 5: Verify read service tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_web_read_service.py -q
```

Expected: pass.

## Task 5: Standard-Library Local App

**Files:**

- Create: `src/coductor/web/app.py`
- Test: `tests/integration/test_web_api.py`

- [ ] **Step 1: Write failing API health test**

Use the framework-free app object directly in tests. Assert:

```json
{
  "ok": true,
  "data": {
    "root": "/tmp/demo-project",
    "version": "0.1.0"
  }
}
```

- [ ] **Step 2: Write failing run API tests**

Assert:

- `GET /api/runs` returns seeded run.
- `GET /api/runs/{run_id}` returns checkpoint and artifact summary.
- `GET /api/runs/missing` returns `ok: false` and recoverable error.

- [ ] **Step 3: Write failing artifact path traversal API test**

`GET /api/runs/{run_id}/artifacts/..%2Fcoductor.yaml` must return 400-style wrapped error and never read outside run_dir.

- [ ] **Step 4: Implement app factory**

Implement:

```python
def create_app(root: Path) -> LocalConsoleApp:
    app = LocalConsoleApp(root)
    read_service = ConsoleReadService(root)
    control_service = ConsoleControlService(root)

    @app.get("/api/health")
    def health() -> ConsoleResponse[ConsoleHealth]:
        return ConsoleResponse(ok=True, data=read_service.health())

    return app
```

Routes:

- `GET /api/health`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_path:path}`
- `GET /api/runs/{run_id}/report`
- `GET /api/runs/{run_id}/logs/{log_path:path}`
- `GET /api/doctor`

Responses use `ConsoleResponse`.

- [ ] **Step 5: Verify API tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_web_api.py -q
```

Expected: pass.

## Task 6: Shared Control Service

**Files:**

- Create: `src/coductor/web/control_service.py`
- Modify: `src/coductor/cli.py` or extract new `src/coductor/services/control_service.py`
- Test: `tests/integration/test_web_controls.py`
- Test: existing `tests/integration/test_cli_commands.py`

- [ ] **Step 1: Write failing web action tests**

Seed runs for each action:

- `pause` from running -> paused.
- `stop` from running -> stopped.
- `approve` from human_required -> matches CLI approval behavior.
- `resume` from human_required checkpoint -> continues through `RunService.resume`.
- `verify` from ready/human_required -> writes new `05_gate_report.yaml`.
- `review` from ready/human_required -> writes `06_review.yaml` and `07_evidence.yaml`.
- `release` from ready -> writes `08_release_manifest.yaml`.

- [ ] **Step 2: Write failing locked-run action test**

Acquire run lock with another owner. Assert every Web action returns recoverable error and does not write status/event/artifact changes.

- [ ] **Step 3: Extract CLI-private control helpers if needed**

Current `src/coductor/cli.py` contains helper logic for `_approve_run`, `_rerun_verification`, `_rerun_review`, and `release_run`. Move shared logic into a service module if Web would otherwise duplicate it:

```text
src/coductor/services/control_service.py
```

Potential API:

```python
class ControlResult(BaseModel):
    run_id: str
    action: str
    status: str
    message: str
    next_command: str | None = None

class RunControlService:
    def approve(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._run_locked_action(run_id, "approve", actor)

    def pause(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._run_locked_action(run_id, "pause", actor)

    def stop(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._run_locked_action(run_id, "stop", actor)

    def verify(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._run_locked_action(run_id, "verify", actor)

    def review(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._run_locked_action(run_id, "review", actor)

    def resume(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._resume_locked(run_id, actor)

    def release(self, run_id: str, actor: str = "cli") -> ControlResult:
        return self._run_locked_action(run_id, "release", actor)
```

CLI then delegates to this service. Web delegates to the same service.

- [ ] **Step 4: Add Web action route**

Add:

```http
POST /api/runs/{run_id}/actions/{action}
```

Allowed actions:

- approve
- pause
- stop
- resume
- verify
- review
- release

Disallowed action returns recoverable error.

- [ ] **Step 5: Verify control tests and existing CLI regressions**

Run:

```bash
.venv/bin/pytest tests/integration/test_web_controls.py tests/integration/test_cli_commands.py -q
```

Expected: pass.

## Task 7: Static UI Shell

**Files:**

- Create: `src/coductor/web/static/index.html`
- Create: `src/coductor/web/static/styles.css`
- Create: `src/coductor/web/static/app.js`
- Modify: `src/coductor/web/app.py`
- Test: `tests/integration/test_web_api.py`

- [ ] **Step 1: Write failing static asset test**

Assert:

- `GET /` returns HTML.
- HTML contains `id="app"`.
- `GET /static/styles.css` returns CSS.
- `GET /static/app.js` returns JS.

- [ ] **Step 2: Implement static mount**

Mount package-local assets. Avoid CDN and external network dependencies.

- [ ] **Step 3: Build UI structure**

HTML:

- App root.
- Basic noscript text.
- Links to local stylesheet and app.js.

CSS:

- Dense operator console layout.
- Sidebar run list.
- Main detail panel.
- Tabs.
- Action bar.
- Status colors with readable contrast.
- Responsive layout for narrow width.

JS:

- Fetch `/api/health`, `/api/runs`, selected run detail.
- Poll selected run every 2 seconds.
- Render run list, timeline, artifacts, evidence, release, doctor.
- Submit action POSTs with confirmation for state-changing actions.
- Render recoverable errors with next command.

- [ ] **Step 4: Verify static tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_web_api.py::test_static_console_assets -q
```

Expected: pass.

## Task 8: Evidence, Release, And Doctor UI Views

**Files:**

- Modify: `src/coductor/web/read_service.py`
- Modify: `src/coductor/web/static/app.js`
- Modify: `src/coductor/web/static/styles.css`
- Test: `tests/unit/test_web_read_service.py`
- Test: `tests/integration/test_web_api.py`

- [ ] **Step 1: Add read-service summary tests**

Assert run detail includes:

- gate_summary from `07_evidence.yaml` when present.
- review_summary from `07_evidence.yaml` when present.
- evidence validation errors.
- release ready/blocked from `08_release_manifest.yaml` when present.
- doctor backend capability fields.

- [ ] **Step 2: Implement summary extraction**

Read artifacts through `ArtifactRepository` and validate artifact type. Missing optional artifacts should return empty summaries rather than errors.

- [ ] **Step 3: Render UI views**

Add tabs:

- Evidence
- Release
- Doctor

Each view must show useful next action:

- Evidence invalid -> show validation errors.
- Release missing -> show `Generate release manifest` action when run is ready.
- Doctor warning -> show install/config hint.

- [ ] **Step 4: Verify targeted tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_web_read_service.py tests/integration/test_web_api.py -q
```

Expected: pass.

## Task 9: Browser Smoke And Visual QA

**Files:**

- Test/support as needed under `tests/integration/`
- No production file required unless smoke helper is added.

- [ ] **Step 1: Start local demo run**

Use `examples/demo-python-project` or a temp project to create a real ready run with fake backend.

Command sequence:

```bash
tmpdir="$(mktemp -d)"
cp -R examples/demo-python-project "$tmpdir/demo"
cd "$tmpdir/demo"
/Users/ninex/Projects/hll-ecosystem/apps/coductor/.venv/bin/coductor init
/Users/ninex/Projects/hll-ecosystem/apps/coductor/.venv/bin/coductor run "修复示例函数并补充测试" --backend fake
```

- [ ] **Step 2: Start console**

```bash
/Users/ninex/Projects/hll-ecosystem/apps/coductor/.venv/bin/coductor serve --port 8765
```

- [ ] **Step 3: Verify browser**

Use Codex in-app browser or Playwright if available:

- Open `http://127.0.0.1:8765`.
- Confirm run list is visible.
- Open run detail.
- Open Artifacts tab.
- Open Evidence tab.
- Generate Release if missing.
- Confirm no text overlap at desktop width.
- Confirm no text overlap at narrow/mobile width.

- [ ] **Step 4: Capture issues**

Fix layout issues before final verification. Do not ship UI with hidden buttons, unreadable text, or overlapping panels.

## Task 10: Docs And Security Notes

**Files:**

- Modify: `README.md`
- Modify: `docs/security.md`
- Possibly modify: `docs/workflow.md`
- Test: `tests/unit/test_documentation_contracts.py`

- [ ] **Step 1: Add docs test if documentation contract exists**

Assert README mentions:

- `coductor serve`
- `127.0.0.1`
- standard installation without extra Web runtime dependency
- Web console does not replace YAML artifacts

- [ ] **Step 2: Update README**

Add section:

```markdown
## Local Web Console
```

Include:

- install command
- serve command
- safety defaults
- core views
- warning about LAN exposure

- [ ] **Step 3: Update security docs**

Document:

- loopback default
- `--allow-lan` risk
- no arbitrary shell API
- path traversal protection
- secrets/env not exposed
- remote git actions disabled by default

- [ ] **Step 4: Verify docs tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_documentation_contracts.py -q
```

Expected: pass.

## Task 11: Final Verification

**Files:**

- No new production files expected.

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/pytest
```

Expected:

```text
212 passed
```

- [ ] **Step 2: Run lint**

```bash
.venv/bin/ruff check .
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run type check**

```bash
.venv/bin/mypy src
```

Expected:

```text
Success: no issues found
```

- [ ] **Step 4: Run dependency check**

```bash
.venv/bin/python -m pip check
```

Expected:

```text
No broken requirements found.
```

Pip cache warning is acceptable if no broken requirements are reported.

- [ ] **Step 5: Run CLI smoke**

```bash
.venv/bin/coductor
.venv/bin/coductor doctor
.venv/bin/coductor serve --host 0.0.0.0 --port 8765
```

Expected:

- First command prints terminal Coductor banner.
- Doctor prints backend diagnostics.
- Non-loopback serve without `--allow-lan` exits with clear safety error.

- [ ] **Step 6: Run Web smoke**

Start:

```bash
.venv/bin/coductor serve --port 8765
```

Verify:

```bash
curl -i http://127.0.0.1:8765/api/health
curl -i http://127.0.0.1:8765/api/runs
```

Expected:

- HTTP 200.
- JSON `ok: true`.

## Production Acceptance Checklist

- [ ] `coductor serve` is optional, loopback-first, and does not affect `coductor run`.
- [ ] Default host is `127.0.0.1`.
- [ ] Non-loopback host requires `--allow-lan`.
- [ ] Web has no arbitrary file read.
- [ ] Web has no arbitrary command execution.
- [ ] Web does not expose secrets or env.
- [ ] Web control actions reuse existing service logic and locks.
- [ ] Locked run actions have no side effects.
- [ ] Status-disallowed actions have no side effects.
- [ ] Artifact views preserve YAML source of truth.
- [ ] UI works without CDN/network.
- [ ] UI has no text overlap in desktop and narrow view.
- [ ] All verification commands pass.

## Recommended Execution Order

1. Task 1: CLI surface and standard-library HTTP runtime.
2. Task 2: path safety foundation.
3. Task 3: schemas.
4. Task 4: read-only service.
5. Task 5: read-only API.
6. Task 7: static UI shell.
7. Task 8: evidence/release/doctor views.
8. Task 6: safe actions.
9. Task 9: browser smoke and visual QA.
10. Task 10: docs/security.
11. Task 11: final verification.

The only intentional reorder above is moving static UI before safe actions. This gives a useful read-only console early while keeping side effects behind tested service boundaries.
