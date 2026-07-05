from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import ArtifactEnvelope, ToolResultData
from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import BrowserCheckConfig, CoductorConfig, ToolCheckConfig
from coductor.domain.enums import ArtifactType
from coductor.services.evidence_service import EvidenceService
from coductor.services.tool_verification_service import ToolVerificationService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


def test_browser_runner_validates_local_static_page(tmp_path: Path) -> None:
    _install_fake_playwright(tmp_path)
    (tmp_path / "index.html").write_text(
        '<html><body><main id="app">Hello Coductor</main></body></html>',
        encoding="utf-8",
    )
    repo, result = _run_browser_check(tmp_path, selectors=["body", "#app"])

    assert result.data.status == "passed"
    assert result.data.observations["status"] == "passed"
    assert "tool_runs/browser-smoke/browser_summary.json" in result.data.artifacts
    assert "tool_runs/browser-smoke/browser_screenshot.png" in result.data.artifacts
    assert (repo.root / "tool_runs/browser-smoke/browser_screenshot.png").exists()


def test_browser_runner_fails_on_console_error(tmp_path: Path) -> None:
    _install_fake_playwright(tmp_path)
    (tmp_path / "index.html").write_text(
        "<html><body><script>console.error('boom')</script></body></html>",
        encoding="utf-8",
    )
    _repo, result = _run_browser_check(tmp_path)

    assert result.data.status == "failed"
    assert "console_errors" in result.data.observations
    assert result.data.failure_fingerprint


def test_browser_runner_screenshot_is_recorded_in_evidence(tmp_path: Path) -> None:
    _install_fake_playwright(tmp_path)
    (tmp_path / "index.html").write_text(
        "<html><body><main>Hello Coductor</main></body></html>",
        encoding="utf-8",
    )
    repo, result = _run_browser_check(tmp_path, selectors=["body"])

    evidence = EvidenceService().build(
        run_dir=repo.root,
        goal_title="browser smoke",
        strategy="solo",
        gate_report=_empty_gate_report(),
        review=_empty_review(),
        completed_tasks=[],
    )

    paths = {item.path for item in evidence.evidence_files}
    assert result.data.status == "passed"
    assert "tool_runs/browser-smoke/tool_result.yaml" in paths
    assert "tool_runs/browser-smoke/browser_screenshot.png" in paths


def _run_browser_check(
    root: Path,
    *,
    selectors: list[str] | None = None,
) -> tuple[ArtifactRepository, ArtifactEnvelope[ToolResultData]]:
    config = CoductorConfig.default()
    config.quality_gates = []
    config.tool_checks = [
        ToolCheckConfig(
            id="browser-smoke",
            tool="browser",
            timeout_seconds=30,
            browser=BrowserCheckConfig(
                static_path="index.html",
                selectors=selectors or ["body"],
                screenshot=True,
            ),
        )
    ]
    repo = ArtifactRepository(root / ".coductor" / "runs" / "run_browser")
    writer = WorkflowArtifactWriter(root, config)
    [result] = ToolVerificationService(root, config, writer).run_checks(repo, "run_browser")
    loaded = ArtifactEnvelope[ToolResultData].model_validate(
        repo.read(
            "tool_runs/browser-smoke/tool_result.yaml",
            ArtifactType.TOOL_RESULT,
        ).model_dump(mode="json")
    )
    return repo, loaded


def _install_fake_playwright(root: Path) -> None:
    module_dir = root / "node_modules" / "playwright"
    module_dir.mkdir(parents=True)
    (module_dir / "package.json").write_text(
        '{"type":"module","main":"index.js"}\n',
        encoding="utf-8",
    )
    (module_dir / "index.js").write_text(
        """
import fs from "node:fs";

const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64"
);

export const chromium = {
  async launch() {
    return {
      async newPage() {
        let html = "";
        const handlers = {};
        return {
          on(type, handler) {
            handlers[type] = handler;
          },
          async goto(url) {
            html = fs.readFileSync(new URL(url), "utf8");
            if (html.includes("console.error")) {
              handlers.console?.({ type: () => "error", text: () => "boom" });
            }
          },
          locator(selector) {
            return {
              async count() {
                if (selector === "body") return html.includes("<body") ? 1 : 0;
                if (selector === "#app") return html.includes('id="app"') ? 1 : 0;
                return html.includes(selector) ? 1 : 0;
              }
            };
          },
          getByText(text) {
            return {
              async count() {
                return html.includes(text) ? 1 : 0;
              }
            };
          },
          async screenshot({ path }) {
            fs.writeFileSync(path, png);
          }
        };
      },
      async close() {}
    };
  }
};
""".lstrip(),
        encoding="utf-8",
    )


def _empty_gate_report():
    from coductor.artifacts.models import GateReportData

    return GateReportData(
        base_commit="base",
        head_commit="head",
        gates=[],
        required_gates_passed=True,
        next_action="review",
    )


def _empty_review():
    from coductor.artifacts.models import ReviewReportData

    return ReviewReportData(
        reviewer_thread_id="thread_review",
        reviewed_base_commit="base",
        reviewed_head_commit="head",
    )
