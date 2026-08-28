# 项目进度 Check List

> 最后更新：2026-08-22（V1.0-V9.3 完成，140 测试，6 Agent 并行 + 全代码库上下文 + PR 历史学习 + 语义 Diff + 可观测性 + AI 测试项目库 + **CrewAI Flows+Crews 双层架构重构完成**）

> ## ✅ CrewAI 重构进度（2026-08-22）
>
> - [x] 内层 Crew 工厂 `app/flows/crew_factory.py`：6 Agent CrewAI 角色（role/goal/backstory）+ 确定性逻辑封装为 CrewAI @tool + Task(output_pydantic) + Crew(Process.sequential) + build_crew_llm（复用项目 LLM 配置）
> - [x] 外层 Flow `app/flows/review_flow.py`：删除降级分支与"可选路径"注释；@start parse → 6 个 @listen 并行 Crew 节点 → and_() 聚合 → 报告；进度事件扩展 flow_node_*/agent_*(含 role/goal/tool)
> - [x] 服务层 `app/services/review_service.py`：删除 asyncio.gather 编排，委托 ReviewFlow；保留 DB 持久化/指标/健康度/摘要/进度事件
> - [x] 测试：140 全通过（新增 test_crew_factory + 重写 test_review_flow 5 用例 + helpers.patch_review_flow 适配集成测试）
> - [x] 前端可学习化：ReviewProgress 新增「外层 Flow 节点流程图 + 内层 Crew 明细卡片（role）」；ReviewTrigger 修正 asyncio.gather 宣传 + 新增"快速演示模式（真实执行）"引导
> - [x] 文档清理：multi-agent-orchestration.html 重写为 CrewAI 双层架构学习文档；architecture-overview.html 移除 asyncio.gather/优雅降级表述
> - [x] 应用冒烟：ASGI 请求验证 health/projects/docs/编排文档/reviews 路由全部正常
> - [x] 已提交：分支 `refactor/crewai-flows-crews`（06970ba → e1275f1 → 2703611）
>
> ### ⏳ 待用户验收（开发侧已完成，以下需真实环境 + 真实 LLM）
>
> - [ ] 配置并启用 LLM（设置 → 模型配置，填 API Key）
> - [ ] 启动服务，跑一次「安全审查」→ 观察外层 Flow 流程图 + 内层 Crew 卡片真实流转
> - [ ] 跑「综合审查」→ 观察 6 Crew 并行 + 聚合去重 + 健康度
> - [ ] 验证无 LLM 时返回清晰错误（不静默降级）
> - [ ] Docs 页确认「多 Agent 编排」双层架构文档展示
> - [ ] 验收通过后合并分支回 main

> ## ⚠️ 路线修正记录（2026-08-22）
>
> 立项决定采用 **CrewAI Flows + Crews 双层架构**（学习项目核心目标）。开发过程中曾私自降级为手写 `asyncio.gather` 编排，偏离路线 100%。**现已焊死路线**：
> - 生产主路径 = CrewAI Flows（外层确定性编排） + Crews（内层 Agent 自主协作）；
> - 下文所有标注 `asyncio.gather` 的历史条目均标记为 **已废弃（DEPRECATED）**；
> - 禁止任何降级路径/手写编排/把 Flow 当可选骨架。

## V9.3 Dashboard 学习价值优化 ✅ 完成

- [x] 健康度趋势改为**按项目展示**（柱状图）：
  - X 轴：项目名，Y 轴：健康度（0-100）
  - 每个项目柱子颜色按健康度分级（≥80 绿 / ≥60 橙 / <60 红）
  - 直观展示"哪个项目健康、哪个项目有问题"（多 Agent 审查的综合结果）
- [x] 最近审查记录改为**规范化表格**展示：
  - 审查类型（中文：综合审查/安全审查等）
  - 状态（中文：已完成/运行中/失败等）
  - 问题数（严重/警告分布 + 总数）
  - 健康度（分数 + 颜色分级）
  - 耗时（秒）
  - 时间（格式化）
- [x] 点击表格行跳转到审查详情页
- [x] TypeScript 编译通过（0 错误）

## V9.2 运行时指标真实化 + Dashboard 优化 ✅ 完成

- [x] 新增 `llm_usage` 表（持久化每次 LLM 调用的 token，重启不丢失）
- [x] `llm_client.py` 记录 prompt_tokens / completion_tokens 到数据库
- [x] `/system/metrics` 端点改为从数据库聚合真实数据：
  - 审查总数/完成/失败/运行中（reviews 表）
  - 审查类型分布 + 平均耗时（reviews 表）
  - findings 总数 + 严重度分布 + Agent 分布（findings 表）
  - LLM 调用次数 + token 消耗（llm_usage 表）
- [x] 移除 LLM 成本估算（计费复杂，各厂商差异大，对学习无益）
- [x] 移除运行时长（不重要）
- [x] 前端 Dashboard 运行时指标卡片展示真实数据
- [x] Dashboard 优化：运行时指标去重（移除与顶部统计重复的审查统计/findings 统计）
- [x] Dashboard 布局优化：副标题 + 板块间距 + 统计卡片图标颜色
- [x] 修复 Dashboard 运行时指标 undefined 报错
- [x] Dashboard 大屏重构（从上到下板块布局）：
  - 健康度趋势改为柱状图（双 Y 轴：健康度 + 问题数）
  - 严重程度 + 处理状态两个饼图占一行（不再和健康趋势挤一起）
  - 运行时指标用进度条 + 中文标签展示（审查类型/耗时/Agent 分布）
  - LLM 调用统计用 4 个统计卡片
  - 最近审查记录占一行（中文标签）
- [x] 测试更新（131 全通过）

## V9.1 AI 测试项目库 ✅ 完成

- [x] 创建 `test-projects/` 目录（真实 AI 测试项目库）
- [x] clone 3 个个人开发者 AI 项目（非官方、star 少、开源）：
  - `python-simpleaichat`（Python，Max Woolf，MIT，3.5k star）
  - `js-chatgpt-api`（JavaScript，Travis Fischer，MIT）
  - `go-openai`（Go，Sasha Baranov，Apache-2.0）
- [x] docker-compose 加挂载 `./test-projects:/app/test-projects`
- [x] 注册 3 个项目到系统（容器内路径）
- [x] 验证：simpleaichat 安全审查发现 7 个真实问题（1 严重 + 4 警告 + 2 建议）
  - 🔴 API 密钥通过 assert 暴露在错误消息中
  - 🟡 assert 输入验证（生产环境被禁用）
  - 🟡 API 密钥硬编码风险
  - 🟡 会话管理内存泄露风险
  - 🔵 类型验证缺失
- [x] 项目 `git_remote` 字段支持（ProjectCreate/ProjectUpdate schema 补充）
- [x] 3 个 AI 项目设置 git_remote（GitHub 仓库地址）
- [x] 前端项目列表页路径列显示超链接（GitHub 标签，点击跳转仓库）
- [x] 前端项目详情页 Git远程 显示超链接（打开仓库 标签）

## V9.0 上下文理解 + 学习 + 语义 Diff + 可观测性 ✅ 完成

### P0 全代码库上下文（Context Engine）
- [x] 代码索引服务 `services/code_index.py`（AST 符号表 + 调用关系图 + 文件依赖）
- [x] 向量化检索 `services/vector_store.py`（Embedding + 语义检索，降级关键词）
- [x] 上下文引擎 `services/context_engine.py`（组装文件内容/符号/调用者/语义匹配）
- [x] Agent 上下文增强 `agents/context_enhancer.py`（安全/规范/性能 Agent 注入代码库上下文）

### P1 PR 历史学习（Learning）
- [x] 规则模型 `models/review_rule.py`（类型/置信度/权重/来源）
- [x] 规则挖掘 `services/rule_miner.py`（从历史 finding 提取高频模式）
- [x] 反馈闭环（用户确认/修复/重开 → 调整规则权重）
- [x] 规则 API `/api/v1/rules`（列表/挖掘/启停/删除）
- [x] 前端规则管理页 `/rules`
- [x] 验证：从历史审查挖掘 20 条规则（UP045/I001/BLE001/N+1 等）

### P2 语义 Diff（Semantic Diff）
- [x] AST diff `services/semantic_diff.py`（函数/类级新增/删除/修改识别）
- [x] 调用图影响分析（变更影响哪些调用方 + 风险分级）
- [x] LLM 意图分析 `services/intent_analysis.py`（变更目的 + 风险 + 遗漏修改）
- [x] 语义 diff API `/api/v1/semantic-diff`（diff + intent）
- [x] 前端语义 diff 页 `/semantic-diff`

### P3 可观测性增强（Observability）
- [x] LLM 成本统计（按模型 token 成本估算）
- [x] 审计日志（最近 100 条操作历史）
- [x] metrics 深化（cost_by_model / tokens_by_model / audit_log）
- [x] Dashboard 展示成本统计 + 最近操作

### 测试
- [x] 新增 17 个测试（上下文引擎 6 + 规则挖掘 5 + 语义 diff 4 + 可观测性 3）
- [x] 总计 131 全通过

## V8.3 审查能力中心（交互重构）✅ 完成

- [x] 触发页重构：顶部选项卡（Segmented）切换 7 种审查能力
- [x] 能力介绍折叠块：工具链 / 检测维度 / 输出格式 / 实现原理 / 文档链接
- [x] 触发区域：选项目 + 触发方式（扫描/粘贴/上传）+ 开始按钮
- [x] ReviewProgress 支持 inline 模式（内联进度卡片，替代 Modal）
- [x] 综合审查 6 Agent 并行进度卡片网格 + 聚合进度条
- [x] 审查完成后内联显示结果摘要 + 查看详情按钮
- [x] 系统文档模块（后端 `/api/v1/docs` + 前端 DocsPage + 12 篇 HTML 文档）
- [x] Dashboard 能力概览卡片（6 Agent 图标 + 工具链）
- [x] 测试：114 全通过，TypeScript 0 错误

## V8.4 WebSocket 进度修复（Vite proxy 缺 ws:true）✅ 完成

- [x] 根因：Vite proxy 配置缺 `ws: true`，导致 WebSocket 握手失败（非 OrbStack 域名问题）
- [x] 修复：vite.config.ts proxy 加 `ws: true`（支持 WS 转发）
- [x] docker-compose 加端口映射（backend 8001:8000，frontend 3000:3000）便于 localhost 访问
- [x] 验证：OrbStack 域名 + localhost 均正常，6 Agent 并行进度卡片实时更新
- [x] 手动 socket 测试 OrbStack 域名 WS 握手成功（101 Switching Protocols）
- [x] 访问地址：前端 OrbStack 域名或 localhost:3000，后端 localhost:8001

## Day 1 MVP（基础框架）✅ 全部完成

- [x] 后端项目骨架（FastAPI + SQLAlchemy + SQLite）
- [x] 数据库模型（Project / Review / Finding）
- [x] Pydantic 请求/响应模型
- [x] API 端点（项目CRUD、审查管理、发现管理、系统健康检查）
- [x] 前端项目骨架（React + TypeScript + Vite + Ant Design）
- [x] 前端页面（仪表盘、项目列表/详情）
- [x] 前端 API 客户端
- [x] Docker Compose 配置（OrbStack 域名访问，无 localhost）
- [x] 数据持久化（`./data:/app/data` volume 挂载）
- [x] 前端代理（Vite proxy → Docker 内部网络 `backend:8000`）
- [x] 热重载（uvicorn `--reload` + WatchFiles）
- [x] 网络隔离（独立 `app-network`，不与其他项目混用）
- [x] Vite allowedHosts（允许 OrbStack 域名）

---

## Day 2（触发层 + 项目管理）✅ 全部完成

### 触发层

- [x] 触发器基类与注册机制（`triggers/base.py` + `registry.py`）
- [x] 本地目录触发器（`triggers/local_dir.py`）
- [x] 代码粘贴触发器（`triggers/paste.py`）
- [x] 文件上传触发器（`triggers/upload.py`）— 支持单文件和压缩包
- [x] CLI 触发器（`triggers/cli.py`）
- [x] 触发器 API（`GET /triggers/types` + `POST /triggers` + `POST /triggers/upload`）

### 项目管理

- [x] 项目搜索与筛选（搜索名称/描述 + 语言筛选）
- [x] 项目编辑/删除功能（列表页 + 详情页双入口）
- [x] 项目详情页完善（编辑、安全审查、扫描文件、返回列表）

### 前端页面

- [x] 触发审查页面（本地目录/代码粘贴/文件上传 三种 Tab）
- [x] 审查记录列表页（`/reviews`）
- [x] 审查详情页骨架（`/reviews/:id`）

---

## Day 3（CrewAI + 安全审查）✅ 全部完成

### ✅ 已完成

- [x] CrewAI 环境配置（容器内已安装 crewai + semgrep）
- [x] 安全审查 Agent（`agents/security_agent.py`）— Semgrep 静态分析 + LLM 智能分析
- [x] 审查服务层（`services/review_service.py`）— 编排 Agent 执行
- [x] 审查触发 API（`POST /reviews/run?project_id=xxx&review_type=security`）
- [x] 审查结果入库（Finding 模型，含 severity / file_path / suggestion 等）
- [x] 审查结果摘要生成（自动统计 critical/warning/suggestion 数量）
- [x] 前端安全审查按钮（项目详情页一键触发）
- [x] 审查报告生成器（`services/report_generator.py`）— Markdown 格式
- [x] 审查报告下载 API（`GET /reviews/{id}/report`）
- [x] 前端审查详情页（Finding 列表展示）
- [x] 前端审查列表页（可点击进入详情）
- [x] LLM 智能分析集成（安全 Agent 调用 LLM 做语义分析）

### LLM 模型配置（额外完成）

- [x] 模型配置数据库模型（`models/llm_config.py`）
- [x] 模型配置 API（CRUD + 测试连接，`/api/v1/llm-configs`）
- [x] 模型配置前端页面（`/settings/models`）
- [x] 支持 OpenAI / DeepSeek / Ollama / 自定义
- [x] API Key 加密存储（前端只显示"已设置/未设置"）
- [x] 一键测试连接（显示延迟和模型回复）

### ReviewFlow（CrewAI Flows 双层架构）

- [x] ReviewFlow 骨架（`app/flows/review_flow.py`）— 白盒编排 parse→dispatch→run→aggregate→report（Phase B 完成）→ **生产主路径（重构中）**

---

## Day 4-5（报告 + 联调）✅ 全部完成

- [x] Markdown 报告生成 ✅
- [x] 前端 Finding 列表展示（严重程度 / 代码片段 / 修复建议）✅
- [x] 审查详情页完善（审查概览 + 发现列表 + 报告）✅
- [x] 审查报告下载功能 ✅
- [x] 前后端联调 ✅ — 全链路验证（触发→审查→结果→报告，真实跑通 15 findings/89s）
- [x] 集成测试 ✅ — `backend/tests/` 72 个用例全过（pytest+httpx 覆盖项目/触发器/审查/报告/模型配置/统计/Flow/健康度/进度/增量审查）

---

## Phase A（收尾 + 联调修复）✅ 完成

- [x] 修复 LLM 配置选择 bug — MIMO 非 default 导致 LLM 分析被跳过
- [x] 修复 Semgrep code_snippet 数据质量（占位符 "requires login" → 真实源码行）
- [x] LLM 分析改为并发调用（Semaphore=3），单文件 ~40s 并行化
- [x] 共享 LLM 客户端 `agents/llm_client.py` + 代码工具 `agents/utils.py`（消除重复）
- [x] 系统统计接口 `GET /system/stats`（仪表盘数据源）
- [x] 前端 Dashboard 真实统计 + 最近审查列表
- [x] 前端触发页支持审查类型选择 + 开始审查流程
- [x] 前端项目详情页支持审查类型下拉（full/security/code_style）
- [x] Pydantic v2 弃用警告清理（class Config → model_config）

---

## Phase B（V3.0 代码规范审查 + 多 Agent 编排 + 报告增强）✅ 完成

- [x] CodeStyleAgent（`agents/code_style_agent.py`）— Ruff 静态检查 + LLM 语义点评
- [x] ~~ReviewService 多 Agent 并行编排（full = security + code_style，asyncio.gather）~~ **已废弃（DEPRECATED，2026-08-22）** — 由 CrewAI Flows + Crews 双层架构重构替代
- [x] 报告增强：按 Agent 分组 + 补齐 nitpick + HTML 报告（`GET /reviews/{id}/report/html`）
- [x] 前端审查详情页新增「HTML报告」按钮
- [x] ReviewFlow（CrewAI Flows 双层编排骨架）+ 3 个编排测试 → **已升级为生产主路径（2026-08-22，重构进行中）**

### 真实跑通的验证

| 审查类型 | findings | 耗时 | 说明 |
|----------|----------|------|------|
| security | 15（7 严重/7 警告/1 建议） | 89s | Semgrep + LLM 语义分析 |
| code_style | 4（2 警告/1 建议/1 细节） | 140s | Ruff + LLM 规范点评 |
| full | 16（2 严重/10 警告/2 建议/2 细节） | 178s | security + code_style 并行聚合去重 |
| dependency | 4（2 警告/2 建议） | 112s | pip-audit + npm registry + LLM |
| test_coverage | 44（2 警告/42 建议） | 74s | AST 未测试函数 + LLM 建议 |
| incremental | 2（1 严重） | 46s | Git diff 增量，仅审查变更文件 |

---

## Phase C（V4.0 依赖审查 + 测试覆盖）✅ 完成

- [x] DependencyAgent（`agents/dependency_agent.py`）— pip-audit 漏洞扫描 + npm registry 过时检测 + LLM 风险点评
- [x] TestCoverageAgent（`agents/test_coverage_agent.py`）— AST 未测试函数识别 + LLM 测试建议
- [x] ReviewService 注册新 Agent（full 现含 4 个 Agent 并行）
- [x] 前端触发页/项目详情页支持 dependency / test_coverage 审查类型
- [x] 静态逻辑测试（pip-audit 解析、AST 覆盖识别）+ 编排测试（51 个全过）

---

## Phase D（V5.0 实时进度 + 健康度聚合）✅ 完成

- [x] 健康度评分 `services/health.py`（基于 findings 负分制 0-100）+ 审查快照 + 项目健康度更新
- [x] 进度事件总线 `services/progress.py`（内存 pub/sub）
- [x] WebSocket 端点 `GET /reviews/ws/{id}`（实时推送 agent_started/completed、review_completed，含心跳）
- [x] 非阻塞审查 `POST /reviews/run-async`（202 立即返回 running，后台执行 + 独立会话提交）
- [x] ReviewService 各阶段发布进度事件
- [x] 前端 `ReviewProgress` 组件（WS 订阅 + Agent 进度时间线 + 健康度展示）
- [x] 项目详情页接入实时进度（触发→进度→完成跳转）
- [x] 测试：健康度计算 + 进度 pub/sub + 异步审查轮询（60 个全过）
- [x] 端到端验证：WS 实时事件流（connected→agent_completed→review_completed）

### 已知限制（Phase E 优化）

- ~~WS 订阅前已发射的 agent_started 事件可能丢失~~ ✅ 已修复（事件历史回放）
- Langfuse 推理链追踪需外部服务/API Key（structlog 已覆盖结构化日志）

---

## Phase E（V6.0-V7.0 增量审查 + 优化完善）✅ 完成

- [x] WS 事件历史回放（`progress.py` 缓冲 + 订阅时回放，修复 agent_started 丢失）
- [x] Git diff 解析器 `services/diff_parser.py`（提取变更文件 + 新增行号）
- [x] 增量审查端点 `POST /reviews/run-incremental`（只审查 diff 变更文件，贴合 PR 场景）
- [x] 真实 Git 仓库端到端验证（正确识别变更文件与行号）
- [x] structlog 结构化日志（全链路已用）
- [x] 测试总数 72 个全过（含 diff 解析 9 + 增量审查 3 + 进度回放 1）

---

## Phase F（V8.0 Finding 状态 + 可观测性 + 图表）✅ 完成

- [x] Finding 状态更新 API `PUT /findings/{id}/status`（open/acknowledged/fixed）
- [x] 前端 Finding 状态操作菜单（标记已确认/已解决/重新打开）
- [x] 已解决 Finding 变灰+删除线 + 状态标签彩色展示
- [x] 运行时指标模块 `services/metrics.py`（Review/LLM/Agent 指标收集）
- [x] LLM 客户端自动记录延迟/token/成功率
- [x] ReviewService 自动记录 Agent 执行指标（成功率/耗时/发现数）
- [x] `GET /system/metrics` 端点（运行时可观测性）
- [x] `GET /system/stats` 增强（趋势数据 + 状态分布 + acknowledged 计数）
- [x] 前端 Dashboard 图表（recharts 健康度趋势折线图 + 严重程度/处理状态饼图）
- [x] 前端运行时指标卡片（Agent 成功率进度条 + LLM 调用统计）
- [x] 测试：98 个全通过（原 85 + 新增 13）

### Phase F+（V8.1 性能分析 Agent）✅ 完成

- [x] PerformanceAgent（`agents/performance_agent.py`）— AST 静态分析 + LLM 语义补充
- [x] AST 检测维度：N+1 查询（循环内 ORM 调用）、同步阻塞（async 内 time.sleep/requests）、字符串 += 拼接、无限制 .all()
- [x] LLM 性能分析（与现有 Agent 模式一致，Semaphore 并发）
- [x] 注册到 AGENT_REGISTRY（full 类型自动包含 5 Agent 并行）
- [x] 前端触发页/项目详情页支持 performance 审查类型
- [x] 测试：13 个新增（总计 98 全通过）

### Phase F++（V8.2 AutoFix + GitReviewAgent）✅ 完成

- [x] AutoFix 引擎 `services/autofix.py`（Ruff 自动修复 + diff 预览）
- [x] AutoFix API `POST /reviews/{id}/autofix`（预览模式 / 应用模式）
- [x] 前端 ReviewDetail 页「自动修复」按钮 + 补丁预览 Modal
- [x] GitReviewAgent（`agents/git_review_agent.py`）— Conventional Commits + 分支策略 + 贡献统计 + LLM 点评
- [x] 注册到 AGENT_REGISTRY（full 类型自动包含 6 Agent 并行）
- [x] 前端触发页/项目详情页支持 git_review 审查类型
- [x] 代码查看器升级（暗色主题 + 行号 + monospace）
- [x] 测试：16 个新增（总计 114 全通过）

---

## 总体完成状态

| 路线图阶段 | 状态 | 对应 Phase |
|------------|------|-----------|
| V1.0 MVP 基础框架 | ✅ | （已有） |
| V2.0 触发层 + 项目管理 | ✅ | （已有） |
| V3.0 代码安全审查 + CrewAI | ✅ | A（修复 LLM/片段） |
| V3.0+ 代码规范 + 报告增强 | ✅ | B |
| V4.0 依赖审查 + 测试覆盖 | ✅ | C |
| V5.0 实时进度 + 健康度聚合 | ✅ | D |
| V6.0 增量审查 + 可选能力 | ✅ | E |
| V7.0 优化完善 | ✅（除 Langfuse 需外部服务） | E |
| V8.0 状态闭环 + 可观测性 | ✅ | F |
| V8.1 性能分析 Agent | ✅ | F+ |
| V8.2 AutoFix + GitReview | ✅ | F++ |

**核心架构原则**：确定性工具兜底（Semgrep/Ruff/pip-audit/AST）+ LLM 补充，6 Agent 并行编排 + 结果去重聚合。

---

## 已解决的技术问题

1. ✅ 前端代理 — Vite proxy → Docker 内部网络
2. ✅ 数据持久化 — `./data:/app/data` volume 挂载
3. ✅ 热重载 — uvicorn `--reload` + WatchFiles
4. ✅ 网络隔离 — 独立 `app-network`
5. ✅ OrbStack 域名 — 去掉 localhost，`allowedHosts: true`
6. ✅ 端口冲突 — 8000 被 aicumi 占用，改用 OrbStack 域名访问

## 下一步开发规划（按优先级）

### P0 — 核心审查能力扩展

- [x] **PerformanceAgent**（性能分析）— AST 识别 N+1 查询 / 全表扫描 / 同步阻塞 / 大列表拼接 + LLM 修复建议 ✅
- [x] **AutoFix 能力** — 消费已有的 `is_auto_fixable` 字段，Ruff 自动修复 + LLM 生成补丁，前端"一键修复"按钮 ✅

### P1 — 审查维度补充

- [ ] **GitReviewAgent**（Git 审查）— 提交规范（Conventional Commits）+ 分支策略 + 贡献统计 + LLM 点评 ✅

### P2 — 文档与体验

- [ ] 文档完善（API/用户/部署文档）
- [ ] 前端代码查看器（语法高亮 + 行号 + 问题标记）

### P3 — 生产化（按需，不急）

- [ ] JWT 认证（等要部署再做）
- [ ] Redis/Celery 持久化任务（等并发量上来再做）
- [ ] GitHub Webhook 触发器（最后考虑，手动触发已够用）

---

## 当前访问地址

| 服务 | 地址 |
|------|------|
| 前端 | `http://aicodereviewteam-frontend-1.orb.local:3000` |
| 后端 API | `http://localhost:8001` |
| API 文档 | `http://localhost:8001/docs` |

> 说明：OrbStack 域名 WS 正常（根因是 Vite proxy 缺 `ws: true`，已修复）。前端可用 OrbStack 域名或 localhost:3000 访问。
