# AI Code Review Team

多Agent协作代码审查系统 - 学习项目

## 快速开始

### 方式一：本地开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

### 方式二：Docker

```bash
docker-compose up --build
```

访问：
- 前端：http://localhost:3000
- 后端API文档：http://localhost:8000/docs

## 技术栈

| 组件 | 技术 |
|------|------|
| 多Agent框架 | CrewAI (Flows + Crews) |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | React + TypeScript + Vite + Ant Design |
| 静态分析 | Semgrep + Ruff + coverage.py |
| 可观测性 | Langfuse + structlog |

## 项目结构

```
AICodeReviewTeam/
├── backend/          # 后端项目
├── frontend/         # 前端项目
├── agents/           # AI Agent模块（CrewAI）
├── tools/            # 工具集成
├── docs/             # 文档
├── plans/            # 规划文档
└── tests/            # 测试
```

## 文档

- [技术架构设计](plans/技术架构设计.md)
- [开发规划](plans/开发规划.md)
- [项目结构](plans/项目结构.md)
- [Agent学习笔记](docs/agent-learning-notes.md)
