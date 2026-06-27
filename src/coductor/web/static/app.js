const state = {
  runs: [],
  selectedRunId: null,
  busyAction: null,
  activeTab: "overview",
  currentRun: null,
  doctor: null,
  notice: null,
};

const controlToken =
  document.querySelector('meta[name="coductor-control-token"]')?.getAttribute("content") || "";

async function fetchJson(path, options = {}) {
  const requestOptions = { ...options };
  if (requestOptions.method === "POST" && controlToken) {
    requestOptions.headers = {
      ...(requestOptions.headers || {}),
      "X-Coductor-Token": controlToken,
    };
  }
  const response = await fetch(path, requestOptions);
  const payload = await response.json();
  if (!payload.ok) {
    const message = payload.error?.message || "Request failed";
    throw new Error(message);
  }
  return payload.data;
}

function statusClass(status) {
  return String(status || "").replaceAll(" ", "_");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function actionLabel(action) {
  return (
    {
      approve: "Approve",
      pause: "Pause",
      stop: "Stop",
      resume: "Resume",
      verify: "Verify",
      review: "Review",
      release: "Release",
    }[action] || action
  );
}

function setActiveTab(tab) {
  state.activeTab = tab;
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.classList.toggle("is-active", button.dataset.tab === tab);
  }
  if (tab === "doctor" && !state.doctor) {
    loadDoctor();
  }
  renderCurrentView();
}

function renderRuns() {
  const list = document.querySelector("#runList");
  if (!state.runs.length) {
    list.innerHTML = '<div class="empty-state">No runs yet.</div>';
    return;
  }
  list.innerHTML = state.runs
    .map(
      (run) => `
        <button class="run-item ${run.run_id === state.selectedRunId ? "is-active" : ""}"
          type="button" data-run-id="${escapeHtml(run.run_id)}">
          <div class="run-id">${escapeHtml(run.run_id)}</div>
          <div class="run-meta">
            <span class="status-pill ${statusClass(run.status)}">${escapeHtml(run.status)}</span>
            <span>${escapeHtml(run.current_stage || "no checkpoint")}</span>
          </div>
        </button>
      `,
    )
    .join("");
  for (const button of list.querySelectorAll("[data-run-id]")) {
    button.addEventListener("click", () => selectRun(button.dataset.runId));
  }
}

function renderDetail(run) {
  state.currentRun = run;
  renderCurrentView();
}

function renderCurrentView() {
  if (!state.currentRun && state.activeTab !== "doctor") {
    return;
  }
  const panel = document.querySelector("#runDetail");
  const run = state.currentRun;
  if (state.activeTab === "doctor") {
    renderDoctor(panel);
    return;
  }
  if (state.activeTab === "artifacts") {
    renderArtifacts(panel, run);
    return;
  }
  if (state.activeTab === "timeline") {
    renderTimeline(panel, run);
    return;
  }
  if (state.activeTab === "logs") {
    renderLogs(panel, run);
    return;
  }
  if (state.activeTab === "evidence") {
    renderEvidence(panel, run);
    return;
  }
  if (state.activeTab === "release") {
    renderRelease(panel, run);
    return;
  }
  renderOverview(panel, run);
}

function renderOverview(panel, run) {
  const actions = ["approve", "pause", "stop", "resume", "verify", "review", "release"];
  panel.innerHTML = `
    <article class="summary-card">
      <div class="summary-header">
        <div>
          <div class="summary-title">${escapeHtml(run.run_id)}</div>
          <div class="summary-subtitle">${escapeHtml(run.run_dir)}</div>
        </div>
        <span class="status-pill ${statusClass(run.status)}">${escapeHtml(run.status)}</span>
      </div>
      <div class="action-row">
        ${actions
          .map(
            (action) => `
              <button class="action-button ${action === "stop" ? "danger" : ""}"
                type="button" data-action="${action}"
                ${state.busyAction ? "disabled" : ""}>
                ${state.busyAction === action ? "Working..." : actionLabel(action)}
              </button>
            `,
          )
          .join("")}
      </div>
      <div id="actionNotice" class="action-notice" aria-live="polite"></div>
    </article>
    <section class="metric-row">
      <div class="metric-card">
        <span>Artifacts</span>
        <strong>${escapeHtml(run.artifacts?.length || 0)}</strong>
      </div>
      <div class="metric-card">
        <span>Events</span>
        <strong>${escapeHtml(run.events?.length || 0)}</strong>
      </div>
      <div class="metric-card">
        <span>Stage</span>
        <strong>${escapeHtml(run.current_stage || "pending")}</strong>
      </div>
    </section>
  `;
  renderNotice();
  for (const button of panel.querySelectorAll("[data-action]")) {
    button.addEventListener("click", () => runAction(button.dataset.action));
  }
}

function renderArtifacts(panel, run) {
  const artifacts = run.artifacts || [];
  panel.innerHTML = `
    <section class="data-card">
      <h2>Artifacts</h2>
      <div class="artifact-grid">
        ${
          artifacts.length
            ? artifacts
                .map(
                  (artifact) => `
                    <button class="artifact-item" type="button"
                      data-artifact-path="${escapeHtml(artifact.path)}">
                      <div class="artifact-path">${escapeHtml(artifact.path)}</div>
                      <div class="run-meta">
                        <span>${escapeHtml(artifact.artifact_type)}</span>
                        <span>rev ${escapeHtml(artifact.revision)}</span>
                      </div>
                    </button>
                  `,
                )
                .join("")
            : '<div class="empty-inline">No artifacts found.</div>'
        }
      </div>
    </section>
    <section id="artifactPreview" class="data-card preview-card">
      <h2>Preview</h2>
      <pre>Select an artifact to inspect its YAML.</pre>
    </section>
  `;
  for (const button of panel.querySelectorAll("[data-artifact-path]")) {
    button.addEventListener("click", () => previewArtifact(button.dataset.artifactPath));
  }
}

function renderTimeline(panel, run) {
  const events = run.events || [];
  panel.innerHTML = `
    <section class="data-card">
      <h2>Timeline</h2>
      <div class="event-list">
        ${
          events.length
            ? events
                .map(
                  (event) => `
                    <div class="event-item">
                      <strong>${escapeHtml(event.stage)}</strong>
                      <div>${escapeHtml(event.message)}</div>
                      <small>${escapeHtml(event.created_at)}</small>
                    </div>
                  `,
                )
                .join("")
            : '<div class="empty-inline">No events recorded.</div>'
        }
      </div>
    </section>
  `;
}

function renderLogs(panel, run) {
  const events = run.events || [];
  const logArtifacts = (run.artifacts || []).filter((artifact) => artifact.path.includes("logs/"));
  panel.innerHTML = `
    <section class="data-card">
      <h2>Logs</h2>
      <div class="event-list">
        ${
          events.length
            ? events
                .map(
                  (event) => `
                    <div class="event-item">
                      <strong>${escapeHtml(event.stage)}</strong>
                      <div>${escapeHtml(event.message)}</div>
                      <small>${escapeHtml(event.created_at)}</small>
                    </div>
                  `,
                )
                .join("")
            : '<div class="empty-inline">No events recorded.</div>'
        }
      </div>
    </section>
    <section class="data-card">
      <h2>Log Files</h2>
      <div class="artifact-grid">
        ${
          logArtifacts.length
            ? logArtifacts
                .map(
                  (artifact) => `
                    <button class="artifact-item" type="button"
                      data-log-path="${escapeHtml(artifact.path)}">
                      <div class="artifact-path">${escapeHtml(artifact.path)}</div>
                      <div class="run-meta">
                        <span>${escapeHtml(artifact.status)}</span>
                        <span>rev ${escapeHtml(artifact.revision)}</span>
                      </div>
                    </button>
                  `,
                )
                .join("")
            : '<div class="empty-inline">No log files found.</div>'
        }
      </div>
    </section>
    <section id="logPreview" class="data-card preview-card">
      <h2>Preview</h2>
      <pre>Select a log file to inspect it.</pre>
    </section>
  `;
  for (const button of panel.querySelectorAll("[data-log-path]")) {
    button.addEventListener("click", () => previewLog(button.dataset.logPath));
  }
}

function renderEvidence(panel, run) {
  const evidence = run.evidence;
  if (!evidence) {
    panel.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">No evidence yet</div>
        <p>Evidence appears after gates, review, and delivery artifacts are written.</p>
      </div>
    `;
    return;
  }
  const validation = evidence.validation || {};
  panel.innerHTML = `
    <section class="summary-card">
      <div class="summary-header">
        <div>
          <div class="summary-title">Evidence</div>
          <div class="summary-subtitle">Final status and delivery validation</div>
        </div>
        <span class="status-pill ${statusClass(evidence.final_status)}">
          ${escapeHtml(evidence.final_status)}
        </span>
      </div>
    </section>
    <section class="metric-row">
      ${metricCard("Gates passed", evidence.gate_summary?.passed ?? 0)}
      ${metricCard("Gates failed", evidence.gate_summary?.failed ?? 0)}
      ${metricCard("Blocking review", evidence.review_summary?.blocking_findings ?? 0)}
    </section>
    <section class="data-card">
      <h2>Validation</h2>
      ${listBlock(validation.errors || [], "No validation errors.")}
    </section>
    <section class="data-card">
      <h2>Evidence Files</h2>
      ${evidence.evidence_files?.length ? evidence.evidence_files.map(fileRow).join("") : '<div class="empty-inline">No evidence files listed.</div>'}
    </section>
    <section class="data-card">
      <h2>Risks And Manual Checks</h2>
      ${listBlock([...(evidence.known_risks || []), ...(evidence.manual_checks || [])], "No manual checks or known risks listed.")}
    </section>
  `;
}

function renderRelease(panel, run) {
  const release = run.release;
  if (!release) {
    panel.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">No release manifest</div>
        <p>Generate one from a ready run with the Release action.</p>
      </div>
    `;
    return;
  }
  panel.innerHTML = `
    <section class="summary-card">
      <div class="summary-header">
        <div>
          <div class="summary-title">Release</div>
          <div class="summary-subtitle">Remote actions are ${release.remote_actions_allowed ? "enabled" : "disabled"}.</div>
        </div>
        <span class="status-pill ${release.ready ? "ready_for_human_review" : "human_required"}">
          ${release.ready ? "ready" : "blocked"}
        </span>
      </div>
    </section>
    <section class="data-card">
      <h2>Local Commands</h2>
      ${commandList(release.local_commands)}
    </section>
    <section class="data-card">
      <h2>Manual Commands</h2>
      ${commandList(release.manual_commands)}
    </section>
    <section class="data-card">
      <h2>Blockers</h2>
      ${listBlock(release.reasons || [], "No release blockers listed.")}
    </section>
  `;
}

function renderDoctor(panel) {
  const checks = state.doctor?.checks;
  if (!checks) {
    panel.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">Doctor loading</div>
        <p>Reading local configuration and backend capabilities.</p>
      </div>
    `;
    return;
  }
  const permission = checks.permission_defaults || {};
  panel.innerHTML = `
    <section class="data-card">
      <h2>Doctor</h2>
      <div class="doctor-grid">
        ${doctorItem("Backend", checks.backend_provider)}
        ${doctorItem("Available", checks.backend_available)}
        ${doctorItem("Codex", checks.codex)}
        ${doctorItem("Database", checks.database)}
        ${doctorItem("Network", permission.network_access)}
        ${doctorItem("Git push", permission.allow_git_push)}
      </div>
    </section>
    <section class="data-card preview-card">
      <h2>Raw Checks</h2>
      <pre>${escapeHtml(JSON.stringify(checks, null, 2))}</pre>
    </section>
  `;
}

function metricCard(label, value) {
  return `
    <div class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function listBlock(items, emptyText) {
  if (!items.length) {
    return `<div class="empty-inline">${escapeHtml(emptyText)}</div>`;
  }
  return `<ul class="fact-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function fileRow(file) {
  return `
    <div class="file-row">
      <span>${escapeHtml(file.type || "file")}</span>
      <code>${escapeHtml(file.path)}</code>
    </div>
  `;
}

function commandList(commands) {
  if (!commands?.length) {
    return '<div class="empty-inline">No commands listed.</div>';
  }
  return `
    <div class="command-list">
      ${commands.map((command) => `<code>${escapeHtml(command)}</code>`).join("")}
    </div>
  `;
}

function doctorItem(label, value) {
  return `
    <div class="doctor-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

async function loadHealth() {
  const health = await fetchJson("/api/health");
  document.querySelector("#projectRoot").textContent = health.root;
  document.querySelector("#healthBadge").textContent = `Coductor ${health.version}`;
}

async function loadDoctor() {
  state.doctor = await fetchJson("/api/doctor");
  if (state.activeTab === "doctor") {
    renderCurrentView();
  }
}

async function loadRuns() {
  state.runs = await fetchJson("/api/runs");
  if (!state.runs.some((run) => run.run_id === state.selectedRunId)) {
    state.selectedRunId = state.runs[0]?.run_id || null;
  }
  renderRuns();
  if (state.selectedRunId) {
    await selectRun(state.selectedRunId, { skipRunRender: true });
    return;
  }
  renderCurrentView();
}

async function selectRun(runId, options = {}) {
  state.selectedRunId = runId;
  if (!options.skipRunRender) {
    renderRuns();
  }
  const run = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
  renderDetail(run);
}

async function runAction(action) {
  if (!state.selectedRunId || state.busyAction) {
    return;
  }
  state.busyAction = action;
  try {
    await selectRun(state.selectedRunId);
    const result = await fetchJson(
      `/api/runs/${encodeURIComponent(state.selectedRunId)}/actions/${encodeURIComponent(action)}`,
      { method: "POST" },
    );
    state.notice = {
      tone: "success",
      message: `${actionLabel(action)} complete. ${result.next_command || ""}`,
    };
    await loadRuns();
  } catch (error) {
    state.notice = { tone: "error", message: error.message };
    renderNotice();
  } finally {
    state.busyAction = null;
    if (state.selectedRunId) {
      await selectRun(state.selectedRunId);
    }
  }
}

async function previewArtifact(path) {
  if (!state.selectedRunId) {
    return;
  }
  const preview = document.querySelector("#artifactPreview pre");
  preview.textContent = "Loading...";
  try {
    const artifact = await fetchJson(
      `/api/runs/${encodeURIComponent(state.selectedRunId)}/artifacts/${encodeURIComponent(path)}`,
    );
    preview.textContent = artifact.raw_text || JSON.stringify(artifact.parsed, null, 2);
  } catch (error) {
    preview.textContent = error.message;
  }
}

async function previewLog(path) {
  if (!state.selectedRunId) {
    return;
  }
  const preview = document.querySelector("#logPreview pre");
  preview.textContent = "Loading...";
  try {
    const log = await fetchJson(
      `/api/runs/${encodeURIComponent(state.selectedRunId)}/logs/${encodeURIComponent(path)}`,
    );
    preview.textContent = log.raw_text || "";
  } catch (error) {
    preview.textContent = error.message;
  }
}

function showNotice(message, tone) {
  state.notice = { message, tone };
  renderNotice();
}

function renderNotice() {
  const notice = document.querySelector("#actionNotice");
  if (!notice) {
    return;
  }
  notice.className = `action-notice ${state.notice?.tone || ""}`;
  notice.textContent = state.notice?.message || "";
}

async function boot() {
  try {
    await loadHealth();
    await loadDoctor();
    await loadRuns();
  } catch (error) {
    document.querySelector("#runDetail").innerHTML = `
      <div class="empty-state">
        <div class="empty-title">Console unavailable</div>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  }
}

document.querySelector("#refreshRuns").addEventListener("click", loadRuns);
for (const button of document.querySelectorAll("[data-tab]")) {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
}
boot();
