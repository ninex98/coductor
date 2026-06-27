# Security

Coductor 默认最小权限：

- Planner、Inspector、Reviewer 默认只读；
- Builder 和 Repairer 只允许 workspace-write；
- 网络默认关闭；
- Git commit、push、PR 创建默认关闭；
- `.env*`、`**/secrets/**`、`**/production/**` 默认保护；
- 不自动提升权限；
- 显式 `parallel` 计划默认需要人工审批，审批前不会派发 worker；
- 不伪造测试、构建或审查成功。
- Evidence 必须包含通过的必需 Gate、无 blocking review 和 patch evidence 才能进入 `ready_for_human_review`。

质量门命令必须来自配置或明确的人类输入。当前实现使用 `subprocess.run(shlex.split(command))`，避免 `shell=True` 拼接。

## Local Web Console

`coductor serve` 是本地控制台，不是远程管理后台。

- 默认监听 `127.0.0.1:8765`。
- 非 loopback host 必须显式传入 `--allow-lan`；这会把控制台暴露给局域网，应只在可信网络中短时间使用。
- Web API 不提供任意 shell 执行入口。
- Web API 不默认开启 git push、PR 创建、联网执行或 Secrets 读取。
- Artifact 和日志预览必须位于 `.coductor/runs/<run-id>/` 内；路径解析会拒绝 `..`、绝对路径、软链接逃逸和非预览后缀。
- Web 控制动作复用 CLI/service 层的状态校验、SQLite run lock 和 stale lock 策略。
- 完成状态仍由质量门、独立审查和 Evidence Bundle 决定；Web UI 不作为下游事实来源。
