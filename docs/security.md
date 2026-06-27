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
