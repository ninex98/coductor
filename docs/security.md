# Security

Coductor 默认最小权限：

- Planner、Inspector、Reviewer 默认只读；
- Builder 和 Repairer 只允许 workspace-write；
- 网络默认关闭；
- Git commit、push、PR 创建默认关闭；
- `.env*`、`**/secrets/**`、`**/production/**` 默认保护；
- 不自动提升权限；
- 不伪造测试、构建或审查成功。

质量门命令必须来自配置或明确的人类输入。MVP 使用 `subprocess.run(shlex.split(command))`，避免 `shell=True` 拼接。
