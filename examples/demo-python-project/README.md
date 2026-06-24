# Demo Python Project

极小示例仓库，用于演示 Coductor 的 fake backend 端到端流程。

从 Coductor 仓库根目录复制本目录后，可在 demo 目录内运行：

```bash
/path/to/coductor/.venv/bin/coductor init
/path/to/coductor/.venv/bin/coductor run "修复示例函数并补充测试" --backend fake
```

`coductor init` 会根据 `pyproject.toml` 生成 Python unit test gate。当前 demo 的 E2E 验证要求生成：

- `.coductor/runs/<run-id>/07_evidence.yaml`
- `.coductor/runs/<run-id>/delivery-report.md`
- evidence `final_status: ready_for_human_review`
- evidence validation `valid: true`
