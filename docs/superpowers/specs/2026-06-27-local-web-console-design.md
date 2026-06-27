# Coductor Local Web Console Design

## 背景

Coductor 的核心价值是确定性工作流：每个阶段写入固定 YAML Artifact，运行状态保存在目标项目本地 `.coductor/coductor.sqlite3`，CLI 负责启动、恢复、控制和报告。当前 CLI 已具备 `status`、`artifacts`、`logs`、`explain`、`approve`、`pause`、`stop`、`verify`、`review`、`release` 等控制面能力，但复杂 run 的审查仍需要在终端和文件之间来回切换。

本设计新增一个可选的本地 Web 控制台，定位为 Coductor 的 localhost 操作台。它不替代 CLI，不引入云端后台，不创建第二套状态系统。Web 控制台读取并展示 SQLite + YAML Artifact，并通过现有服务层执行人工控制动作。

## 目标

- 提供 `coductor serve` 本地命令，默认监听 `127.0.0.1`，展示当前目标项目的 Coductor run。
- 提供生产级可用的 Run 看板、Artifact 浏览器、事件日志、Evidence/Release 视图和 Doctor 视图。
- 支持人工控制动作：approve、pause、stop、resume、verify、review、release。
- 所有控制动作复用现有服务和锁逻辑，不直接改写状态。
- 保持 YAML Artifact 是下游事实来源，Web 只做读取、展示和安全控制入口。

## 非目标

- 不做远程云控制台。
- 不默认监听 `0.0.0.0`。
- 不默认开启 git commit、git push、PR 创建、联网执行、Secrets 读取。
- 不把运行状态复制到新的数据库。
- 不把前端页面直接写入目标项目 `.coductor/runs`。
- 不把 Web UI 作为判断完成状态的来源；完成状态仍由质量门、审查和 Evidence Bundle 决定。

## 架构方案

推荐实现为单进程本地服务：

```text
coductor serve
  -> LocalConsoleApp
    -> ConsoleReadService
      -> Database(.coductor/coductor.sqlite3)
      -> ArtifactRepository(.coductor/runs/<run_id>)
    -> ConsoleControlService
      -> RunService
      -> ReportService
      -> ReleaseService
      -> WorkflowVerificationService / ReviewDeliveryService through existing helpers
    -> Static UI assets
```

后端使用 Python 标准库本地 HTTP 服务，不引入额外 Web 运行依赖。这样 `coductor serve` 可以在现有安装内直接工作，减少 pipx、离线环境和目标项目依赖冲突带来的不确定性。Web API 的类型边界仍由 Pydantic schema、服务层和集成测试保证。

前端第一版使用打包在 Python 包内的静态 HTML/CSS/JS，不引入 Node 构建链。这样可以保证 `pipx install` 后即可使用，也不会让 Coductor 本身变成一个前端 monorepo。UI 代码放在 `src/coductor/web/static/`，后续如果复杂度上升，再评估 Vite/React 构建。

## 模块边界

### `coductor.web.schemas`

定义 Web API 输出模型，字段使用英文，内容可包含中文说明。模型应只表达展示需要，不改变 Artifact 原始结构。

核心模型：

- `ConsoleRunSummary`
- `ConsoleRunDetail`
- `ConsoleArtifactSummary`
- `ConsoleArtifactDetail`
- `ConsoleEvent`
- `ConsoleDoctorReport`
- `ConsoleActionResult`

### `coductor.web.read_service`

只读服务。负责读取 SQLite、Run 目录、YAML Artifact、日志文件和 delivery report。

职责：

- 列出 runs，支持状态过滤和数量限制。
- 获取 run detail，包括 checkpoint、events、artifact list、evidence summary、release manifest summary。
- 读取单个 Artifact，返回 parsed YAML、raw text、hash、revision、输入依赖。
- 读取 gate stdout/stderr 和 worker/repair/review 关键日志。
- 不执行任何状态变更。

### `coductor.web.control_service`

控制服务。负责把 Web action 映射到已有 CLI/service 能力。

职责：

- `approve` 复用 CLI 中的审批逻辑，后续可抽到 `RunControlService` 共享。
- `pause`、`stop` 复用 `ReportService` 的状态校验和 `Database` 锁。
- `resume` 调用 `RunService.resume()`。
- `verify`、`review` 复用现有重新验证/重新审查逻辑。
- `release` 调用 `ReleaseService.create_manifest()`。
- 所有动作必须进入同一套 run lock，不能绕过 stale lock 策略。

### `coductor.web.app`

创建本地 Web app。

职责：

- 注册 API routes。
- 挂载静态 UI。
- 注入目标项目 root。
- 限制 host 默认值。
- 统一错误响应。

### `src/coductor/cli.py`

新增 `serve` 命令。

默认行为：

```bash
coductor serve
```

- 默认 host：`127.0.0.1`
- 默认 port：`8765`
- 默认不自动打开浏览器，除非传入 `--open`
- 打印访问地址和安全提示

可选参数：

```bash
coductor serve --host 127.0.0.1 --port 8765 --open
coductor serve --host 0.0.0.0 --port 8765 --allow-lan
```

如果 host 不是 loopback，必须显式传 `--allow-lan`，否则拒绝启动。

## API 设计

所有 API 仅服务本地控制台。响应统一为：

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

错误响应：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "message": "run not found",
    "recoverable": true,
    "next_command": "coductor status"
  }
}
```

核心路由：

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务健康和项目 root |
| `GET` | `/api/runs` | run 列表 |
| `GET` | `/api/runs/{run_id}` | run detail |
| `GET` | `/api/runs/{run_id}/events` | event timeline |
| `GET` | `/api/runs/{run_id}/artifacts` | artifact 列表 |
| `GET` | `/api/runs/{run_id}/artifacts/{artifact_path}` | artifact detail |
| `GET` | `/api/runs/{run_id}/report` | delivery report |
| `GET` | `/api/runs/{run_id}/logs/{log_path}` | gate/worker/review/repair 日志 |
| `POST` | `/api/runs/{run_id}/actions/{action}` | approve/pause/stop/resume/verify/review/release |
| `GET` | `/api/doctor` | backend、配置、安全默认值诊断 |

`artifact_path` 和 `log_path` 必须做路径归一化，禁止 `..`、绝对路径、软链接逃逸和非 run 目录读取。

## UI 信息架构

第一屏是可操作控制台，不做营销页。

布局：

- 左侧：Run 列表，可按 status 筛选。
- 顶部：当前项目 root、服务地址、doctor 状态摘要。
- 主区：选中 run 的 stage timeline、状态、下一步建议和控制按钮。
- 右侧或下方 tab：Artifacts、Logs、Evidence、Release、Doctor。

视图：

1. Runs
   - run_id、status、updated_at、current_stage、last_error。
   - 点击进入 detail。

2. Timeline
   - 按 event 顺序展示 stage、message、created_at。
   - 当前 stage 高亮。
   - human_required 展示下一步操作。

3. Artifacts
   - 固定阶段顺序展示 `00_goal.yaml` 到 `08_release_manifest.yaml`。
   - 展示 revision、hash、status、producer、input dependencies。
   - 支持 raw YAML 和 parsed summary。

4. Logs
   - event log。
   - gate stdout/stderr。
   - worker_result、repair_result、review report 的关键摘要。

5. Evidence
   - gate summary。
   - review blocking findings。
   - patch evidence。
   - validation errors。
   - delivery report preview。

6. Release
   - `08_release_manifest.yaml`。
   - ready/blocked。
   - local commands。
   - manual commands。
   - 明确显示 remote actions disabled。

7. Doctor
   - backend provider。
   - codex executable。
   - SDK availability。
   - backend capabilities。
   - dangerous defaults。
   - project quality gates。

视觉原则：

- 工具型、清晰、密度适中。
- 不用大面积营销 hero。
- 不用模糊装饰背景。
- 控制按钮使用明确状态和确认语，不让危险动作显得轻飘。
- 所有提示文案要温和、具体、可恢复，例如“这个运行正在被另一个操作锁定。你可以稍后刷新，或在确认旧进程已结束后重试。”

## 安全设计

默认安全策略：

- 只监听 `127.0.0.1`。
- 不设置 cookie，不引入登录态。
- 不暴露跨项目目录读取。
- 不暴露任意 shell 执行 API。
- 不暴露 secrets、env、生产配置。
- 不允许 Web 直接 git push 或 PR。
- 非 loopback host 必须传 `--allow-lan`，并打印明显风险提示。

控制动作策略：

- 所有 action 先检查 run 是否存在。
- 所有 action 进入 run lock。
- 所有 action 复用 CLI/service 校验。
- 状态不允许的 action 返回 recoverable error，不写 event，不写 Artifact。
- `resume`、`verify`、`review`、`release` 的副作用和 CLI 一致。

路径策略：

- 只允许读取选中 run_dir 内文件。
- 允许后缀：`.yaml`、`.yml`、`.log`、`.md`、`.diff`、`.patch`、`.txt`。
- 文件大小超过阈值时返回 truncated preview 和 download-disabled 提示。
- 任何路径归一化后不在 run_dir 内则返回 400。

## 可观测性

- `GET /api/health` 返回服务状态、project root、coductor version。
- 每个 Web action 写入 run event，例如 `web approve requested`。
- API 错误包含 recoverable 和 next_command。
- UI 每 2 秒轮询 run detail；后续可升级 SSE，但第一版不依赖 SSE。
- Web server 启动时打印 URL、root、host、port、安全模式。

## 测试策略

后端测试：

- `ConsoleReadService` 单元测试：run list、artifact list、artifact detail、path traversal 拦截。
- `ConsoleControlService` 单元/集成测试：approve/pause/stop/resume/verify/review/release 动作复用锁和状态校验。
- Web API 测试：health、runs、run detail、artifact detail、action error。
- CLI 测试：`serve` 参数校验、非 loopback host 需要 `--allow-lan`、缺依赖提示。

前端测试：

- 静态 UI smoke：HTML 包含 root 容器和必要资源。
- 端到端 smoke：启动 `coductor serve`，访问 `/` 和 `/api/health`，读取 demo run。
- 浏览器视觉验证：使用 Codex 内置浏览器或可用的 Playwright，对桌面和窄屏截图检查无明显重叠、空白和不可读文本。

最终验证：

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python -m pip check
```

手动 smoke：

```bash
.venv/bin/coductor serve --port 8765
```

打开：

```text
http://127.0.0.1:8765
```

## 分阶段交付

### Phase 1: Read-only Control Plane

完成后可以浏览 runs、artifacts、events、report、doctor，但不能执行动作。

验收：

- `coductor serve` 可启动。
- `/api/health`、`/api/runs`、`/api/runs/{run_id}` 可用。
- UI 能查看 demo run。
- 路径逃逸测试通过。

### Phase 2: Safe Actions

完成 approve、pause、stop、resume、verify、review、release。

验收：

- 每个 action 和 CLI 行为一致。
- 锁被占用时不产生副作用。
- 状态不允许时返回 recoverable error。
- release 生成 `08_release_manifest.yaml`。

### Phase 3: Production UI Polish

完成响应式 UI、舒适提示、证据视图、release 视图、doctor 视图。

验收：

- 桌面和窄屏无文本重叠。
- human_required、locked、failed、ready_for_human_review 都有明确下一步。
- UI 不依赖网络 CDN。

### Phase 4: Packaging And Docs

完成 README、security 文档、打包静态资源和 smoke。

验收：

- `pipx install -e .` 后可运行 `coductor serve`。
- 标准安装后可直接启动，不需要额外 Web optional dependency。
- README 说明本地安全边界。

## 风险与应对

| 风险 | 应对 |
| --- | --- |
| Web 层变成第二套状态机 | 控制动作全部复用现有 service/lock；Web 不直接改 checkpoint |
| 任意文件读取 | 路径归一化、run_dir 限制、后缀白名单、大小限制 |
| 依赖过重 | 第一版静态 JS，无 Node 构建链；HTTP 服务使用 Python 标准库 |
| UI 漂亮但不可用 | 第一屏就是 run 控制台；所有视图绑定真实 API |
| 长任务无反馈 | 第一版轮询 events；后续再加 SSE |
| LAN 暴露风险 | 默认 loopback；非 loopback 必须 `--allow-lan` |

## 决策

本地 Web 控制台值得做，并应作为 Coductor 下一轮生产级工程主线之一。第一版必须坚持“CLI 与 Artifact 是核心，Web 是可选控制面”的边界。只要这一点守住，它会显著提升 Coductor 对复杂 run 的可审查性、可恢复性和日常可用性。
