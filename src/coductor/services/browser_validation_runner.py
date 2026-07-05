"""Generated Playwright smoke runner for browser-backed verification."""

from __future__ import annotations

import json
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from coductor.config.models import ToolCheckConfig
from coductor.security import redact_sensitive_text
from coductor.services.tool_execution import ToolExecutionResult, ToolStatus


class BrowserValidationRunner:
    def __init__(self, root: Path, *, run_dir: Path, tool_run_id: str) -> None:
        self.root = root
        self.run_dir = run_dir
        self.tool_run_id = tool_run_id

    def run(self, check: ToolCheckConfig) -> ToolExecutionResult:
        start = time.monotonic()
        artifacts: list[str] = []
        observations: dict[str, object] = {}
        script_path = self.run_dir / "browser_smoke.mjs"
        options_path = self.run_dir / "browser_options.json"
        summary_path = self.run_dir / "browser_summary.json"
        console_path = self.run_dir / "browser_console.log"
        screenshot_path = self.run_dir / "browser_screenshot.png"
        self._write_script(script_path)
        artifacts.append(self._relative(script_path))
        url = self._target_url(check)
        if url is None:
            return ToolExecutionResult(
                status="failed",
                exit_code=2,
                duration_ms=int((time.monotonic() - start) * 1000),
                stdout="",
                stderr="browser check requires browser.url or browser.static_path",
                artifacts=artifacts,
                observations={"browser_error": "missing_target"},
            )
        options = {
            "url": url,
            "timeoutMs": check.timeout_seconds * 1000,
            "viewport": {
                "width": check.browser.viewport_width,
                "height": check.browser.viewport_height,
            },
            "selectors": check.browser.selectors,
            "text": check.browser.text,
            "failOnConsoleError": check.browser.fail_on_console_error,
            "screenshotPath": screenshot_path.as_posix() if check.browser.screenshot else None,
            "summaryPath": summary_path.as_posix(),
            "consolePath": console_path.as_posix(),
        }
        options_path.write_text(
            json.dumps(options, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.append(self._relative(options_path))
        server = self._start_server(check)
        try:
            if server is not None and not self._wait_for_url(
                url,
                check.browser.ready_timeout_seconds,
            ):
                duration_ms = int((time.monotonic() - start) * 1000)
                return ToolExecutionResult(
                    status="timeout",
                    exit_code=None,
                    duration_ms=duration_ms,
                    stdout="",
                    stderr=f"browser target did not become ready: {url}",
                    artifacts=artifacts,
                    observations={"url": url, "ready": False},
                )
            completed = subprocess.run(
                ["node", script_path.as_posix(), options_path.as_posix()],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=check.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolExecutionResult(
                status="timeout",
                exit_code=None,
                duration_ms=int((time.monotonic() - start) * 1000),
                stdout=_timeout_output(exc.stdout),
                stderr=_timeout_output(exc.stderr),
                artifacts=artifacts,
                observations={"url": url},
            )
        except FileNotFoundError as exc:
            return ToolExecutionResult(
                status="failed",
                exit_code=127,
                duration_ms=int((time.monotonic() - start) * 1000),
                stdout="",
                stderr=f"executable not found: {exc.filename}",
                artifacts=artifacts,
                observations={"url": url},
            )
        finally:
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
        stdout = redact_sensitive_text(completed.stdout)
        stderr = redact_sensitive_text(completed.stderr)
        summary = _read_json(summary_path)
        observations.update(summary)
        for path in [summary_path, console_path, screenshot_path]:
            if path.exists():
                artifacts.append(self._relative(path))
        status: ToolStatus = "passed" if completed.returncode == 0 else "failed"
        if summary.get("status") in {"passed", "failed"}:
            status = summary["status"]  # type: ignore[assignment]
        return ToolExecutionResult(
            status=status,
            exit_code=completed.returncode,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout=stdout,
            stderr=stderr,
            artifacts=sorted(dict.fromkeys(artifacts)),
            observations=observations,
        )

    def _target_url(self, check: ToolCheckConfig) -> str | None:
        if check.browser.url:
            return check.browser.url
        if check.browser.static_path:
            static_path = (self.root / check.browser.static_path).resolve()
            return static_path.as_uri()
        return None

    def _start_server(self, check: ToolCheckConfig) -> subprocess.Popen[str] | None:
        if not check.browser.start_command:
            return None
        return subprocess.Popen(
            shlex.split(check.browser.start_command),
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def _wait_for_url(self, url: str, timeout_seconds: int) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1):
                    return True
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        return False

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.run_dir.parent.parent).as_posix()

    def _write_script(self, path: Path) -> None:
        path.write_text(_PLAYWRIGHT_SMOKE_SCRIPT, encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _timeout_output(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


_PLAYWRIGHT_SMOKE_SCRIPT = r"""
import fs from "node:fs/promises";

const options = JSON.parse(await fs.readFile(process.argv[2], "utf8"));
const consoleMessages = [];
const assertions = [];
let browser;
let status = "passed";

function recordAssertion(kind, expected, actual, passed) {
  assertions.push({
    kind,
    expected,
    actual: String(actual),
    status: passed ? "passed" : "failed"
  });
  if (!passed) status = "failed";
}

try {
  const playwright = await import("playwright");
  const chromium = playwright.chromium || playwright.default?.chromium;
  if (!chromium) {
    throw new Error("playwright chromium is unavailable");
  }
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: options.viewport });
  page.on("console", (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });
  page.on("pageerror", (error) => {
    consoleMessages.push({ type: "pageerror", text: error.message });
  });
  await page.goto(options.url, { waitUntil: "networkidle", timeout: options.timeoutMs });
  for (const selector of options.selectors || []) {
    const count = await page.locator(selector).count();
    recordAssertion("selector", selector, count, count > 0);
  }
  for (const expectedText of options.text || []) {
    const count = await page.getByText(expectedText, { exact: false }).count();
    recordAssertion("text", expectedText, count, count > 0);
  }
  if (options.screenshotPath) {
    await page.screenshot({ path: options.screenshotPath, fullPage: true });
  }
} catch (error) {
  status = "failed";
  consoleMessages.push({ type: "runner_error", text: error?.message || String(error) });
} finally {
  if (browser) await browser.close();
}

const consoleErrors = consoleMessages.filter((item) =>
  ["error", "pageerror", "runner_error"].includes(item.type)
);
if (options.failOnConsoleError && consoleErrors.length > 0) {
  status = "failed";
}
await fs.writeFile(
  options.consolePath,
  consoleMessages.map((item) => `[${item.type}] ${item.text}`).join("\n") + "\n",
  "utf8"
);
await fs.writeFile(
  options.summaryPath,
  JSON.stringify(
    {
      status,
      url: options.url,
      console_errors: consoleErrors,
      assertions,
      screenshot_path: options.screenshotPath
    },
    null,
    2
  ) + "\n",
  "utf8"
);
process.exit(status === "passed" ? 0 : 1);
""".lstrip()
