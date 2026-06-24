# YAML Contracts

每个 Artifact 都使用 Envelope：

```yaml
schema_version: "1.0"
artifact_type: goal
artifact_id: art_goal_...
run_id: run_...
revision: 1
status: accepted
created_at: "2026-06-24T00:00:00Z"
producer:
  kind: human
  name: cli-user
inputs: []
metadata:
  content_sha256: "..."
data: {}
```

规则：

- `metadata.content_sha256` 对除自身 hash 字段外的规范 JSON 表示计算；
- 写入时先写临时文件，再 rename；
- 每次写入复制到 `history/`，同一路径通过 `write_next_revision()` 写入时 revision 单调递增；
- 读取时重新计算 hash，不匹配则拒绝；
- `inputs` 记录上游路径、revision 和 sha256；
- `TaskData.contracts` 记录被消费契约的 path、kind、sha256 和 producer task；
- 下游 Artifact 在执行前必须校验所有 `inputs`，上游 revision 或 hash 改变时视为 stale；
- 下游 task 记录的 contract 文件 hash 改变时也视为 stale；
- `resume` 检测到 stale Artifact 时进入 `human_required`，不会静默覆盖旧链路。
- `EvidenceBundleData.validation` 记录交付完整性检查结果；
- evidence 只有在必需质量门无失败、独立 review 无 blocking findings、且至少包含一个 patch evidence 时才允许 `ready_for_human_review`；
- blocking review 或缺失 patch 时仍会写入 `07_evidence.yaml` 与 `delivery-report.md`，但 `final_status` 必须为 `human_required`。
