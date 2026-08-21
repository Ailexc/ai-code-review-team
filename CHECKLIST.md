# 项目进度 Check List

> 最后更新：2026-08-21（Phase A+B+C 完成）

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

## Day 3（CrewAI + 安全审查）✅ 大部分完成 ~95%

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

### ❌ 未完成

- [x] ReviewFlow 骨架（CrewAI Flows 双层架构）✅ `app/flows/review_flow.py` — 白盒编排 parse→dispatch→run→aggregate→report

---

## Day 4-5（报告 + 联调）✅ 全部完成

- [x] Markdown 报告生成 ✅
- [x] 前端 Finding 列表展示（严重程度 / 代码片段 / 修复建议）✅
- [x] 审查详情页完善（审查概览 + 发现列表 + 报告）✅
- [x] 审查报告下载功能 ✅
- [x] 前后端联调 ✅ — 全链路验证（触发→审查→结果→报告，真实跑通 15 findings/89s）
- [x] 集成测试 ✅ — `backend/tests/` 43 个用例全过（pytest+httpx 覆盖项目/触发器/审查/报告/模型配置/统计/Flow）

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
- [x] ReviewService 多 Agent 并行编排（full = security + code_style，asyncio.gather）
- [x] 报告增强：按 Agent 分组 + 补齐 nitpick + HTML 报告（`GET /reviews/{id}/report/html`）
- [x] 前端审查详情页新增「HTML报告」按钮
- [x] ReviewFlow（CrewAI Flows 双层编排骨架）+ 3 个编排测试

### 真实跑通的验证

| 审查类型 | findings | 耗时 | 说明 |
|----------|----------|------|------|
| security | 15（7 严重/7 警告/1 建议） | 89s | Semgrep + LLM 语义分析 |
| code_style | 4（2 警告/1 建议/1 细节） | 140s | Ruff + LLM 规范点评 |
| full | 见下方后台验证 | - | security + code_style 并行 |

---

## Phase C（V4.0 依赖审查 + 测试覆盖）✅ 完成

- [x] DependencyAgent（`agents/dependency_agent.py`）— pip-audit 漏洞扫描 + npm registry 过时检测 + LLM 风险点评
- [x] TestCoverageAgent（`agents/test_coverage_agent.py`）— AST 未测试函数识别 + LLM 测试建议
- [x] ReviewService 注册新 Agent（full 现含 4 个 Agent 并行）
- [x] 前端触发页/项目详情页支持 dependency / test_coverage 审查类型
- [x] 静态逻辑测试（pip-audit 解析、AST 覆盖识别）+ 编排测试（51 个全过）

---

## 已解决的技术问题

1. ✅ 前端代理 — Vite proxy → Docker 内部网络
2. ✅ 数据持久化 — `./data:/app/data` volume 挂载
3. ✅ 热重载 — uvicorn `--reload` + WatchFiles
4. ✅ 网络隔离 — 独立 `app-network`
5. ✅ OrbStack 域名 — 去掉 localhost，`allowedHosts: true`
6. ✅ 端口冲突 — 8000 被 aicumi 占用，改用 OrbStack 域名访问

## 待解决

1. ~~LLM API Key 未配置~~ ✅ 已配置 MIMO 模型（mimo-v2.5 推理模型）
2. ~~Semgrep 首次下载规则较慢~~ ✅ 规则已缓存，后续扫描正常
3. ~~审查结果前端展示待完善~~ ✅ 已完成
4. LLM 为推理模型，单文件分析 ~40s（已通过并发优化，多文件并行）
5. 后续阶段：~~依赖审查 + 测试覆盖（V4.0）~~ ✅ 完成；实时进度 + 健康度（V5.0）、增量审查 + 优化（V6.0-V7.0）

---

## 当前访问地址

| 服务 | 地址 |
|------|------|
| 前端 | `http://aicodereviewteam-frontend-1.orb.local:3000` |
| 后端 API | `http://aicodereviewteam-backend-1.orb.local:8000` |
| API 文档 | `http://aicodereviewteam-backend-1.orb.local:8000/docs` |
