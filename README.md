# AI Code Review Team

多 Agent 协作代码审查系统 — 基于 **CrewAI Flows + Crews 双层架构**，6 个专业 Agent 并行审查、实时进度、增量审查与结构化报告。

## 功能特性

- **6 个专业 Agent 并行审查**（`full` 类型并发运行 + 结果去重聚合）
  - 🔒 安全审查：Semgrep 静态分析 + LLM 语义分析
  - 📐 代码规范：Ruff 静态检查 + LLM 命名/复杂度/重复代码点评
  - 📦 依赖审查：pip-audit 漏洞扫描 + npm registry 过时检测 + LLM 风险点评
  - 🧪 测试覆盖：AST 未测试函数识别 + LLM 测试建议
  - ⚡ 性能分析：AST 数据库调用模式 + LLM 性能反模式判断
  - 🧬 Git 变更审查：变更文件分析 + LLM 变更风险点评
- **实时进度**：WebSocket 推送 Agent 启动/完成、审查结果与健康度（含事件历史回放）
- **增量审查**：基于 Git diff 只审查变更文件（贴合 PR 场景，控制 token 成本）
- **健康度评分**：基于 findings 的 0-100 负分制，随审查更新项目健康度
- **报告**：Markdown + HTML 双格式，按 Agent/严重度分组
- **触发方式**：本地目录 / 代码粘贴 / 文件上传 / CLI / 增量 diff
- **LLM 配置**：支持 OpenAI / DeepSeek / Ollama / 自定义，API Key 加密存储 + 一键测试

### 语言支持能力矩阵（真实工具，非模拟）

| Agent | Python | TypeScript/JS | Go |
|---|---|---|---|
| 🔒 安全审查 | Semgrep（337 规则）+ LLM | Semgrep（203 规则）+ LLM | Semgrep（78 规则）+ LLM |
| 📐 代码规范 | Ruff | **ESLint 9** + typescript-eslint | **golangci-lint** |
| 📦 依赖审查 | pip-audit | npm audit + npm outdated | **OSV-Scanner** |
| 🧪 测试覆盖 | AST 分析 + LLM | LLM 语义层 | LLM 语义层 |
| ⚡ 性能分析 | AST 模式检测 + LLM | LLM 语义层 | LLM 语义层 |
| 🧬 Git 审查 | ✅ 语言无关 | ✅ | ✅ |

> 原则：确定性层只用各生态的官方标准工具（Ruff/ESLint/golangci-lint/pip-audit/npm audit/OSV-Scanner/Semgrep），
> 不做模拟或降级实现；无标准工具等价物的维度（覆盖/性能的非 Python 分析）明确标注由 LLM 语义层承担。

### 编排模式（学习对比）

- ⚡ **并行模式**（默认）：6 个独立 Crew 并行执行 → 代码层去重聚合。快、省 token、结果稳定
- 🎯 **派发模式**（实验）：单个 Crew 容纳全部 Agent，`Process.hierarchical` 由 Manager LLM 统一调度，
  Agent 可互相委派。消耗数倍 token，输出依赖模型能力 —— 用于对比两种编排范式的能力差异

## 快速开始

### Docker（推荐）

```bash
docker-compose up --build
```

访问：
- 前端：http://aicodereviewteam-frontend-1.orb.local:3000
- 后端 API 文档：http://aicodereviewteam-backend-1.orb.local:8000/docs

### 本地开发

```bash
# 后端
cd backend
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend && npm install && npm run dev
```

## 测试

```bash
# 后端集成测试（140 个，容器内运行）
docker exec -w /app aicodereviewteam-backend-1 python -m pytest tests/ -v

# 或本地
cd backend && python -m pytest tests/ -v
```

## 审查类型

| 类型 | 说明 | 示例耗时 |
|------|------|----------|
| `full` | 并行运行所有 Agent | ~180s |
| `security` | 仅安全审查 | ~90s |
| `code_style` | 仅规范审查 | ~140s |
| `dependency` | 仅依赖审查 | ~110s |
| `test_coverage` | 仅测试覆盖 | ~75s |
| `incremental` | Git diff 增量审查 | ~45s |

> LLM 为推理模型，单文件分析约 40s，多文件通过并发优化。

## 技术栈

| 组件 | 技术 |
|------|------|
| 多 Agent 编排 | **CrewAI Flows + Crews 双层架构**（唯一编排方式，无降级/替代路径） |
| 后端 | FastAPI + SQLAlchemy + SQLite (aiosqlite) |
| 前端 | React + TypeScript + Vite + Ant Design |
| 静态分析 | Semgrep + Ruff + pip-audit + AST（经 CrewAI Agent 工具调用） |
| LLM | OpenAI 兼容 API（默认 MIMO mimo-v2.5） |
| 实时通信 | WebSocket |
| 可观测性 | structlog 结构化日志 |

## 项目结构

```
AICodeReviewTeam/
├── backend/
│   ├── app/
│   │   ├── agents/        # 6 个专业 Agent（CrewAI 角色）
│   │   ├── flows/         # CrewAI Flows 外层编排（主路径）
│   │   ├── services/      # 审查编排/报告/健康度/进度/diff解析
│   │   ├── api/v1/        # REST + WebSocket 端点
│   │   ├── triggers/      # 触发器（目录/粘贴/上传/CLI）
│   │   └── models/        # 数据模型
│   └── tests/            # 140 个集成测试
├── frontend/
│   └── src/              # 仪表盘/项目/审查/设置/进度组件
├── plans/                # 架构与开发规划
├── docs/                 # Agent 学习笔记
└── CHECKLIST.md          # 进度清单
```

## 文档

- [技术架构设计](plans/技术架构设计.md)
- [开发规划](plans/开发规划.md)
- [项目结构](plans/项目结构.md)
- [Agent 学习笔记](docs/agent-learning-notes.md)
- [进度清单](CHECKLIST.md)

## 架构理念

**CrewAI Flows + Crews 双层架构（路线焊死，学习项目核心）**：
- **外层 Flow**：用 `@start/@listen/@router` 装饰器做确定性编排（解析 → 分派 → 运行 → 聚合 → 报告），状态用 Pydantic model 管理，白盒可调试；
- **内层 Crew**：每个专业 Agent 以 CrewAI `Agent + Task + Crew` 定义，通过工具调用（Semgrep/Ruff/pip-audit/AST）完成自主审查，上下文隔离；
- **确定性工具兜底 + LLM 补充**：工具做第一道检查，LLM 做语义补充，不完全依赖 LLM。

> ⚠️ **本项目禁止**：手写 asyncio.gather 编排替代 CrewAI、保留"降级路径"、把 Flow 当可选骨架。这是学习 CrewAI 的项目，编排方式只有 CrewAI Flows + Crews 一种。

## License

MIT
