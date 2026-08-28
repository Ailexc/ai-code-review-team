# Checklist：CrewAI Flows + Crews 双层架构重构（防跑偏清单）

**创建日期**：2026-08-22
**路线**：已焊死 —— CrewAI Flows + Crews 双层架构是唯一编排方式（详见 `开发计划-CrewAI重构-2026-08-22.md`、`复盘-2026-08-22.md`、`PLAN.md`）
**用途**：重构过程逐项勾选 + 每次提交前红线自查，防止项目再次跑偏。
**执行状态**：✅ **开发侧全部完成**（阶段 0-6 勾选完毕，140 测试全过，已提交分支 `refactor/crewai-flows-crews`）；⏳ **待用户真实环境验收**（见文末"四、待用户验收"）

---

## 一、红线自查（每次提交 / 每个阶段结束必须过）

- [x] 编排层（`review_service.py` / `review_flow.py`）无 `asyncio.gather`
- [x] 全仓库无"降级路径 / 可选路径 / 可选编排 / 双层骨架 / 生产路径仍是 / 实验性"字样（`grep -rn "asyncio.gather\|降级\|可选路径\|骨架" backend/app backend/docs_html` 核对）
- [x] 无 `_CREWAI_AVAILABLE` 之类降级分支
- [x] 生产主路径 = CrewAI Flow + Crew，无任何手写编排替代
- [x] 代码注释不出现"手搓 / 自己实现编排"的表述
- [x] 文档与实现一致：README / PLAN / 本 Checklist / 架构文档 与代码同步

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

- [x] 6 个 Agent 的 CrewAI 角色定义（role/goal/backstory 中文专业人设）
- [x] 确定性审查逻辑封装为 CrewAI `@tool`（async，返回 findings JSON）
- [x] 每个 Agent 一个 `Task`（描述 + 期望输出 + `output_pydantic`）
- [x] 每个 Agent 一个 `Crew`（`Process.sequential`，独立 Crew = 上下文隔离）
- [x] `build_crew_llm()`：复用项目 LLM 配置构造 CrewAI LLM；无配置抛清晰错误
- [x] Agent/Task 体现"调用工具 + 自主分析"

### 阶段 2：外层 Flow 重构（`backend/app/flows/review_flow.py`）

- [x] 删除降级分支与"可选路径"注释
- [x] `ReviewState` 增加 `review_id`
- [x] `@start parse_project`（校验 + `flow_node_*` 进度事件）
- [x] 6 个 `@listen(parse_project)` 并行 Crew 节点（按 review_type 过滤）
- [x] `@listen(6个节点)` 聚合（去重 + 统计 + 摘要）
- [x] 完成节点返回 ReviewState
- [x] `run_review_flow()` 入口保留

### 阶段 3：服务层改造（`backend/app/services/review_service.py`）

- [x] 删除 asyncio.gather 并行编排（133-135 行）
- [x] `run_review()` 委托 ReviewFlow，拿 findings_by_agent 入库
- [x] 保留进度事件 / 指标 / 健康度 / 摘要 / 异常处理
- [x] 进度事件扩展 `flow_node_*`
- [x] API 层调用签名不变（run / run-incremental / run-async）

### 阶段 4：测试

- [x] 更新 `test_review_flow.py`（6 节点并行 / 聚合 / review_type 过滤，mock Crew+LLM）
- [x] 新增 `test_crew_factory.py`（工具封装 / LLM 构建 / 无配置抛错）
- [x] 更新 `test_review_service.py`（委托 Flow 全链路，mock findings）
- [x] 全量测试通过（133 + 新增，无回归）

### 阶段 5：前端可学习化（重点）

- [x] 审查页"编排架构"面板：外层 Flow 节点流程图（实时状态流转）
- [x] 内层 Crew 明细卡片：role/goal、Task、工具调用摘要、findings 数、耗时
- [x] 审查详情时间线（Flow 节点 + Crew 执行）
- [x] 单 Agent 触发入口（观察单个 Crew 完整流程）
- [x] 演示/快速模式（真实 LLM + 真实工具，单 Agent + 小范围文件，完整观察双层流程）
- [x] Docs 页联调：重写后的编排文档正常展示
- [x] `architecture-overview.html` 重写为 CrewAI 架构总览（待用户确认后执行）

### 阶段 6：收尾验收

- [x] 全仓库 grep 校验通过（红线自查）
- [x] README / CHECKLIST 与实现一致
- [x] 前端走查：双层架构清晰可见
- [x] git 提交（本 Checklist + 开发计划一并提交）

---

## 三、验收标准

| # | 验收项 | 通过标准 | 状态 |
|---|--------|----------|------|
| 1 | 编排方式 | 生产路径 100% CrewAI Flow + Crew | ✅ 已达成（红线自查通过） |
| 2 | 双层体现 | 外层 Flow 节点 + 内层 Crew 分层清晰 | ✅ 已达成（crew_factory + review_flow） |
| 3 | 前端可视化 | 审查页实时显示 Flow 节点流转 + Crew 明细 | ✅ 已达成（ReviewProgress 双层面板） |
| 4 | 真实演示 | 演示/快速模式一键触发，真实 LLM + 工具完整观察双层流程 | ⏳ 待用户配 Key 后真实链路验收 |
| 5 | 学习文档 | Docs 页展示 CrewAI 双层架构 | ✅ 已达成（multi-agent-orchestration 重写） |
| 6 | 测试 | 全量通过，含 Flow 编排测试 | ✅ 已达成（140 全过） |
| 7 | 一致性 | 文档与代码实现一致 | ✅ 已达成（README/PLAN/Checklist/架构文档同步） |

---

## 四、待用户验收（接下来你要做的）

> 开发侧（代码/文档/测试）已完成并提交。以下验收动作需要**真实环境 + 真实 LLM**，请逐项勾选：

### 4.1 环境准备

- [ ] 配置 LLM：进入「设置 → 模型配置」，添加并**启用**一个模型（填 API Key；系统默认兼容 OpenAI 端点，如 MIMO/DeepSeek/Ollama）
- [ ] 启动服务：后端 `cd backend && uvicorn app.main:app --port 8000`；前端 `cd frontend && npm run dev`（或 docker-compose）

### 4.2 真实链路验收（CrewAI 双层架构）

- [ ] **单 Agent 快速演示**：审查能力中心 → 选「安全审查」→ 选项目 → 触发 → 观察：
  - 外层 Flow 流程图实时流转（①解析项目 → ②并行 Crew → ③聚合结果 → ④生成摘要）
  - 内层 Crew 卡片显示 Agent 中文角色、执行状态、findings 数
  - 确认 Agent 真实调用工具（Semgrep + LLM 分析）并产出发现
- [ ] **综合审查（6 Crew 并行）**：选「综合审查」触发 → 确认 6 个 Crew 并行执行、聚合去重、健康度生成
- [ ] **无 LLM 保护**：停用所有模型配置后再触发 → 应返回清晰错误"请先在设置→模型配置启用模型"（不静默降级）
- [ ] **Docs 学习文档**：Docs 页 → 架构设计 →「多 Agent 编排（CrewAI Flows + Crews 双层架构）」→ 确认展示重写后的双层架构文档

### 4.3 问题反馈

- [ ] 若真实链路报错（如 CrewAI 工具调用不稳定、LLM 配置格式不兼容、output_pydantic 解析失败），把报错信息发我，我在分支 `refactor/crewai-flows-crews` 上继续修
- [ ] 全部验收通过后：合并分支回 `main`（`git checkout main && git merge refactor/crewai-flows-crews`）

---

**最后更新**：2026-08-22
**维护者**：AI Code Review Team
