# Coductor Architecture Diagram Style Guide

本文档定义 Coductor 后续架构图、流程图、状态图的视觉与信息表达规范。目标是让图表具备成熟工程基础设施产品的展示质量：premium、minimal、enterprise-grade、clean、structured、editorial layout。

## 1. 总体原则

Coductor 图表不是“把代码关系全部画出来”，而是帮助读者快速理解系统定位、主线流程和关键边界。

- 图表必须服务于一个明确问题：这张图要让读者理解什么？
- 每张图只承载一个主叙事，不把系统架构、运行流程、状态机、数据结构硬塞进同一张图。
- 优先呈现主线，旁路能力只在必要时以侧边卡片或注释形式出现。
- 复杂信息必须拆分，多图组合优于一张巨型蜘蛛网。
- 只画当前代码中真实存在的能力；规划中或占位能力必须标注 `Planned`，并使用虚线或低强调样式。

## 2. 视觉风格

推荐风格：

- 高端、现代、专业，接近成熟工程基础设施产品官网或技术白皮书配图。
- 轻量边框、低饱和色块、充分留白、稳定网格。
- 图表应像产品架构设计稿，而不是课堂流程图或传统企业流程图。

避免：

- Mermaid 默认主题直接作为最终图。
- 节点自由散落、连线密集交叉。
- 颜色花哨或高饱和堆叠。
- 为了完整性把大量文本塞入节点。

## 3. 画布与布局

推荐画布比例：

- 文档首页或 README 主图：16:9 横向。
- 技术说明图：16:9 或 4:3 横向。
- 状态机或 Artifact 链：可横向长图，但要保证主线阅读方向稳定。

推荐布局模式：

- 横向阶段流：适合 `Goal -> Spec -> Plan -> Execute -> Verify -> Review -> Deliver`。
- 分层架构卡片：适合展示入口、控制平面、编排层、执行层、存储层。
- 泳道式流程：适合展示用户、编排、执行、质量、存储之间的协作。
- 卡片矩阵：适合展示模块清单、职责边界、Artifact 类型。
- 中心主线 + 侧边说明：适合总览图，主流程放中间，质量闭环、存储、Artifact 放侧边。

布局规则：

- 必须有明确分区，不允许所有节点自由散落。
- 主线方向只能选一个：横向或纵向，不要中途反复转向。
- 大模块之间保留足够间距，避免局部拥挤。
- 不允许同时出现大片空白和局部密集。
- 关键连线不应超过视觉焦点；辅助关系使用虚线、细线或移到图下注释。
- 出现大量交叉线时，优先重组布局或拆图。

## 4. 色彩规范

色彩用于信息层级，不用于装饰。

推荐色板：

| 用途 | 颜色 | 示例 |
| --- | --- | --- |
| 主色 / 标题 / 强调 | 深海军蓝、blue-slate | `#172033`, `#1E2A44`, `#334155` |
| 背景 | 白色、浅灰蓝 | `#FFFFFF`, `#F8FAFC`, `#F1F5F9` |
| 边框 | 冷灰蓝 | `#CBD5E1`, `#D8E0EA` |
| 编排 / 主流程 | 低饱和绿色 | `#EAF7F1`, `#2E8B57` |
| 执行 / 适配 | 暖灰橙 | `#FFF3EA`, `#C76B32` |
| Artifact / 数据契约 | 低饱和靛蓝 | `#F5F3FF`, `#7C3AED` |
| 存储 | 极浅青蓝 | `#ECFEFF`, `#0891B2` |
| 审批 / 等待 | 柔和琥珀 | `#FFF7D6`, `#B7791F` |
| 失败 / 阻塞 | 柔和红 | `#FEEEEE`, `#C25A5A` |
| Planned | 浅灰 + 虚线 | `#F6F6F6`, `#888888` |

禁止：

- 高饱和大红、大绿、大紫。
- 大面积渐变、装饰性光斑、彩虹配色。
- 同一张图超过 5 种主要语义色。

## 5. 字体与中文

SVG、HTML、Mermaid 主题必须指定中文字体 fallback：

```css
font-family: "Inter", "SF Pro Display", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
```

中文表达规则：

- 标签短而明确，优先 2 行内完成。
- 节点内不写大段解释，细节放到 Markdown 正文或图下注释。
- 中英混合时，英文保留领域关键词，例如 `LangGraph`、`RunService`、`YAML Artifact`、`Evidence Bundle`。
- 避免生硬直译；优先使用自然表达，例如“可恢复状态”优于“恢复检查点状态数据”。

## 6. 卡片与节点

卡片内容上限：

- 标题 1 行。
- 副标题 1 行。
- 关键词 2 到 3 个。

节点命名建议：

```text
RunService
创建 Run / 恢复 / 进度事件
```

不要这样写：

```text
RunService 会负责创建 run_id、更新 SQLite runs 表、写入 events、调用 LangGraph、保存 workflow checkpoint，并处理所有恢复逻辑
```

图形元素：

- 使用圆角卡片、轻边框、统一阴影或无阴影。
- 决策节点可以使用 Decision Card，不必大量使用传统菱形。
- 图例必须短小，放边缘区域，不抢主线视觉焦点。
- Planned 能力必须用虚线边框或低强调灰色卡片。

## 7. 连线规则

箭头只表达关键流转。

必须画的连线：

- 主流程阶段输入输出。
- 明确调用或控制关系。
- 质量门失败后的修复回路。
- Artifact 作为下游事实来源的输入关系。
- Run 状态变化。

不建议画的连线：

- “可能读取”的宽泛关系。
- 重复表达同一含义的多条线。
- 为了显得完整而连接所有模块。
- 跨越全图的辅助线；这类关系应改成图下注释或拆成专题图。

线条语义：

- 实线：当前代码已实现的主要关系。
- 虚线：控制动作、状态请求、Planned 能力或弱关系。
- 红/琥珀色线：仅用于失败、等待、人工介入等少量关键分支。

## 8. Mermaid 规范

允许使用 Mermaid 作为源文件，但不能使用默认主题作为最终展示效果。

推荐在 `.mmd` 文件顶部加入统一初始化配置：

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Inter, SF Pro Display, PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif","primaryColor":"#F8FAFC","primaryTextColor":"#172033","primaryBorderColor":"#CBD5E1","lineColor":"#64748B","secondaryColor":"#F1F5F9","tertiaryColor":"#FFFFFF","clusterBkg":"#FBFDFF","clusterBorder":"#D8E0EA","edgeLabelBackground":"#FFFFFF"},"flowchart":{"htmlLabels":true,"curve":"basis","nodeSpacing":48,"rankSpacing":72,"padding":18}}}%%
```

Mermaid 使用规则：

- 优先 `flowchart LR` 或 `flowchart TB`，根据主线方向选择。
- 使用 `subgraph` 明确分区。
- 使用 `direction LR` / `direction TB` 固定分区内部方向。
- 用 `classDef` 定义语义颜色，不在节点上零散写样式。
- 避免使用 Mermaid 关键字作为 node id，例如 `graph`、`class`、`style`。
- Mermaid 无法满足精细排版时，改用 HTML + CSS + SVG/PNG 导出。

## 9. 输出格式

优先输出：

- 可编辑源文件：`.mmd` 或 `.html`。
- 可引用成品：`.svg`。

可选输出：

- 对外传播或幻灯片需要时输出 `.png`。
- 高精度排版可先生成 HTML + CSS，再用浏览器截图导出 PNG。

路径规范：

- Mermaid 源文件：`docs/architecture/*.mmd`
- SVG 文件：`docs/architecture/*.svg`
- HTML 源文件：`docs/architecture/*.html`
- PNG 文件：`docs/architecture/*.png`

所有图必须能在 README 或文档中直接引用。

## 10. 质量检查清单

每张图交付前检查：

- 是否一眼能看出主线？
- 是否有明确分区？
- 是否没有大量交叉线？
- 是否没有单个节点超过 3 行说明？
- 是否区分当前已实现和 Planned？
- 是否没有画出当前代码中不存在的能力？
- 中文是否清晰、自然、无乱码？
- SVG 是否能正常打开并被文档引用？
- 是否保留了源文件？

## 11. 禁止事项

- 禁止 Mermaid 默认主题直接截图作为最终图。
- 禁止生成乱码中文。
- 禁止用过密文本填满图。
- 禁止传统企业流程图风格。
- 禁止为了“全”而牺牲可读性。
- 禁止大量交叉线、蜘蛛网式模块关系。
- 禁止画出当前项目代码中不存在的能力。
- 禁止将 Planned 能力和已实现能力混在同一视觉层级。

## 12. 推荐的 3 张核心图表

### 1. 系统总览主图

适合讲：

- Coductor 是什么。
- 用户入口、LangGraph 编排、Codex Backend 执行、YAML Artifact 交接、质量闭环、SQLite 持久化之间的整体关系。
- 项目的核心价值：确定性工作流 + 可恢复状态 + Evidence 驱动交付。

不应该包含：

- 每个 CLI 子命令的完整说明。
- 每个 YAML 字段。
- 每个 Python 类之间的细粒度依赖。
- 所有异常分支。

### 2. 端到端业务流程图

适合讲：

- 从用户输入 Goal 到最终 Evidence Bundle 的完整运行过程。
- `Goal -> Spec -> Plan -> Execute -> Verify -> Repair -> Review -> Deliver` 主线。
- 审批、暂停、恢复、修复、审查这些关键分支如何接入主流程。

不应该包含：

- 模块架构分层。
- SQLite 表结构细节。
- Artifact hash / revision / lineage 的完整机制。
- 后端实现类的细节。

### 3. YAML Artifact 与状态流转图

适合讲：

- Coductor 如何用固定结构 YAML 作为阶段事实来源。
- 每个阶段产物如何成为下游输入。
- Run 状态如何在 `created / running / human_required / ready_for_human_review / paused / stopped / failed` 之间变化。
- `clarification / resume / repair` 与 checkpoint、lineage、stale artifact 的关系。

不应该包含：

- 所有服务类和方法名。
- CLI 帮助文本。
- Git worktree 细节。
- 具体质量门命令输出。
