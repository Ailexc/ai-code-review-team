# Checklist：CrewAI Flows + Crews 双层架构重构（防跑偏清单）

**创建日期**：2026-08-22
**路线**：已焊死 —— CrewAI Flows + Crews 双层架构是唯一编排方式（详见 `开发计划-CrewAI重构-2026-08-22.md`、`复盘-2026-08-22.md`、`PLAN.md`）
**用途**：重构过程逐项勾选 + 每次提交前红线自查，防止项目再次跑偏。

---

## 一、红线自查（每次提交 / 每个阶段结束必须过）

- [ ] 编排层（`review_service.py` / `review_flow.py`）无 `asyncio.gather`
- [ ] 全仓库无"降级路径 / 可选路径 / 可选编排 / 双层骨架 / 生产路径仍是 / 实验性"字样（`grep -rn "asyncio.gather\|降级\|可选路径\|骨架" backend/app backend/docs_html` 核对）
- [ ] 无 `_CREWAI_AVAILABLE` 之类降级分支
- [ ] 生产主路径 = CrewAI Flow + Crew，无任何手写编排替代
- [ ] 代码注释不出现"手搓 / 自己实现编排"的表述
- [ ] 文档与实现一致：README / PLAN / 本 Checklist / 架构文档 与代码同步

> 说明：工具内部（如 LLM 并发调用 `llm_client.py`）的 asyncio 并发属于实现细节，允许；但不得承担编排职责。

---

## 二、重构阶段清单

### 阶段 0：垃圾清理 ✅（2026-08-22 完成）

- [x] 删除 `DOCUMENTATION_GUIDE.md`（手搓 asyncio 范例指导）
- [x] 删除 `plans/下一阶段开发规划.md`（过时中间规划）
- [x] 重写 `backend/docs_html/architecture/multi-agent-orchestration.html` → CrewAI Flows + Crews 学习文档
- [x] 修正 `backend/app/api/v1/endpoints/docs.py` 目录描述
- [x] 修正 `security-agent.html` "自动降级"措辞
- [x] 路线焊死：PLAN.md / README.md / CHECKLIST.md / 技术架构设计.md / 项目结构.md / 复盘-2026-08-22.md
- [x] 复盘文件重命名为中文+日期：`复盘-2026-08-22.md`

### 阶段 1：内层 Crew 工厂（`backend/app/flows/crew_factory.py`）

- [ ] 6 个 Agent 的 CrewAI 角色定义（role/goal/backstory 中文专业人设）
- [ ] 确定性审查逻辑封装为 CrewAI `@tool`（async，返回 findings JSON）
- [ ] 每个 Agent 一个 `Task`（描述 + 期望输出 + `output_pydantic`）
- [ ] 每个 Agent 一个 `Crew`（`Process.sequential`，独立 Crew = 上下文隔离）
- [ ] `build_crew_llm()`：复用项目 LLM 配置构造 CrewAI LLM；无配置抛清晰错误
- [ ] Agent/Task 体现"调用工具 + 自主分析"

### 阶段 2：外层 Flow 重构（`backend/app/flows/review_flow.py`）

- [ ] 删除降级分支与"可选路径"注释
- [ ] `ReviewState` 增加 `review_id`
- [ ] `@start parse_project`（校验 + `flow_node_*` 进度事件）
- [ ] 6 个 `@listen(parse_project)` 并行 Crew 节点（按 review_type 过滤）
- [ ] `@listen(6个节点)` 聚合（去重 + 统计 + 摘要）
- [ ] 完成节点返回 ReviewState
- [ ] `run_review_flow()` 入口保留

### 阶段 3：服务层改造（`backend/app/services/review_service.py`）

- [ ] 删除 asyncio.gather 并行编排（133-135 行）
- [ ] `run_review()` 委托 ReviewFlow，拿 findings_by_agent 入库
- [ ] 保留进度事件 / 指标 / 健康度 / 摘要 / 异常处理
- [ ] 进度事件扩展 `flow_node_*`
- [ ] API 层调用签名不变（run / run-incremental / run-async）

### 阶段 4：测试

- [ ] 更新 `test_review_flow.py`（6 节点并行 / 聚合 / review_type 过滤，mock Crew+LLM）
- [ ] 新增 `test_crew_factory.py`（工具封装 / LLM 构建 / 无配置抛错）
- [ ] 更新 `test_review_service.py`（委托 Flow 全链路，mock findings）
- [ ] 全量测试通过（133 + 新增，无回归）

### 阶段 5：前端可学习化（重点）

- [ ] 审查页"编排架构"面板：外层 Flow 节点流程图（实时状态流转）
- [ ] 内层 Crew 明细卡片：role/goal、Task、工具调用摘要、findings 数、耗时
- [ ] 审查详情时间线（Flow 节点 + Crew 执行）
- [ ] 单 Agent 触发入口（观察单个 Crew 完整流程）
- [ ] 演示/快速模式（真实 LLM + 真实工具，单 Agent + 小范围文件，完整观察双层流程）
- [ ] Docs 页联调：重写后的编排文档正常展示
- [ ] `architecture-overview.html` 重写为 CrewAI 架构总览（待用户确认后执行）

### 阶段 6：收尾验收

- [ ] 全仓库 grep 校验通过（红线自查）
- [ ] README / CHECKLIST 与实现一致
- [ ] 前端走查：双层架构清晰可见
- [ ] git 提交（本 Checklist + 开发计划一并提交）

---

## 三、验收标准（全部满足才算完成）

| # | 验收项 | 通过标准 | 状态 |
|---|--------|----------|------|
| 1 | 编排方式 | 生产路径 100% CrewAI Flow + Crew | ☐ |
| 2 | 双层体现 | 外层 Flow 节点 + 内层 Crew 分层清晰 | ☐ |
| 3 | 前端可视化 | 审查页实时显示 Flow 节点流转 + Crew 明细 | ☐ |
| 4 | 真实演示 | 演示/快速模式一键触发，真实 LLM + 工具完整观察双层流程 | ☐ |
| 5 | 学习文档 | Docs 页展示 CrewAI 双层架构 | ☐ |
| 6 | 测试 | 全量通过，含 Flow 编排测试 | ☐ |
| 7 | 一致性 | 文档与代码实现一致 | ☐ |

---

**最后更新**：2026-08-22
**维护者**：AI Code Review Team
