# AI Code Review Team

多 Agent 协作代码审查系统 — 支持 4 个专业 Agent 并行审查、实时进度、增量审查与结构化报告。

## 功能特性

- **4 个专业 Agent 并行审查**（`full` 类型并发运行 + 结果去重聚合）
  - 🔒 安全审查：Semgrep 静态分析 + LLM 语义分析
  - 📐 代码规范：Ruff 静态检查 + LLM 命名/复杂度/重复代码点评
  - 📦 依赖审查：pip-audit 漏洞扫描 + npm registry 过时检测 + LLM 风险点评
  - 🧪 测试覆盖：AST 未测试函数识别 + LLM 测试建议
- **实时进度**：WebSocket 推送 Agent 启动/完成、审查结果与健康度（含事件历史回放）
- **增量审查**：基于 Git diff 只审查变更文件（贴合 PR 场景，控制 token 成本）
- **健康度评分**：基于 findings 的 0-100 负分制，随审查更新项目健康度
- **报告**：Markdown + HTML 双格式，按 Agent/严重度分组
- **触发方式**：本地目录 / 代码粘贴 / 文件上传 / CLI / 增量 diff
- **LLM 配置**：支持 OpenAI / DeepSeek / Ollama / 自定义，API Key 加密存储 + 一键测试

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
# 后端集成测试（72 个，容器内运行）
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
| 多 Agent 编排 | CrewAI Flows（双层骨架） + asyncio 并行 |
| 后端 | FastAPI + SQLAlchemy + SQLite (aiosqlite) |
| 前端 | React + TypeScript + Vite + Ant Design |
| 静态分析 | Semgrep + Ruff + pip-audit + AST |
| LLM | OpenAI 兼容 API（默认 MIMO mimo-v2.5） |
| 实时通信 | WebSocket |
| 可观测性 | structlog 结构化日志（Langfuse 可选） |

## 项目结构

```
AICodeReviewTeam/
├── backend/
│   ├── app/
│   │   ├── agents/        # 4 个 Agent + 共享 LLM 客户端/工具
│   │   ├── flows/         # CrewAI Flows 编排骨架
│   │   ├── services/      # 审查编排/报告/健康度/进度/diff解析
│   │   ├── api/v1/        # REST + WebSocket 端点
│   │   ├── triggers/      # 触发器（目录/粘贴/上传/CLI）
│   │   └── models/        # 数据模型
│   └── tests/            # 72 个集成测试
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

**确定性工具兜底 + LLM 补充**：每个 Agent 先用确定性工具（Semgrep/Ruff/pip-audit/AST）做第一道检查，再用 LLM 做语义补充，不完全依赖 LLM，保证准确性。

## License

MIT
