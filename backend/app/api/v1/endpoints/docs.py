"""系统文档 API — 提供架构设计、Agent 知识点、使用指南等 HTML 文档"""

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# 文档根目录
DOCS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "docs_html"

# 文档元数据（静态配置，也可从文件中读取）
DOCS_CATALOG = [
    # 架构设计
    {
        "id": "architecture-overview",
        "title": "系统架构总览",
        "category": "architecture",
        "category_label": "架构设计",
        "description": "整体架构图、数据流、技术栈选择",
        "icon": "🌐",
    },
    {
        "id": "multi-agent-orchestration",
        "title": "多 Agent 编排（CrewAI Flows + Crews 双层架构）",
        "category": "architecture",
        "category_label": "架构设计",
        "description": "外层 Flow 确定性编排 + 内层 Crew 自主协作（学习核心）",
        "icon": "🔀",
    },
    {
        "id": "deterministic-plus-llm",
        "title": "确定性工具 + LLM 模式",
        "category": "architecture",
        "category_label": "架构设计",
        "description": "Semgrep/Ruff/AST 兜底 + LLM 语义补充",
        "icon": "🧩",
    },
    # Agent 能力
    {
        "id": "security-agent",
        "title": "安全审查 Agent",
        "category": "agents",
        "category_label": "Agent 能力",
        "description": "Semgrep 静态分析 + LLM 安全语义分析",
        "icon": "🛡️",
    },
    {
        "id": "code-style-agent",
        "title": "规范审查 Agent",
        "category": "agents",
        "category_label": "Agent 能力",
        "description": "Ruff 静态检查 + LLM 规范点评",
        "icon": "📏",
    },
    {
        "id": "dependency-agent",
        "title": "依赖审查 Agent",
        "category": "agents",
        "category_label": "Agent 能力",
        "description": "pip-audit 漏洞扫描 + npm registry 过时检测",
        "icon": "📦",
    },
    {
        "id": "test-coverage-agent",
        "title": "测试覆盖 Agent",
        "category": "agents",
        "category_label": "Agent 能力",
        "description": "AST 未测试函数识别 + LLM 测试建议",
        "icon": "🧪",
    },
    {
        "id": "performance-agent",
        "title": "性能分析 Agent",
        "category": "agents",
        "category_label": "Agent 能力",
        "description": "AST 检测 N+1 查询/同步阻塞/字符串拼接",
        "icon": "⚡",
    },
    {
        "id": "git-review-agent",
        "title": "Git 审查 Agent",
        "category": "agents",
        "category_label": "Agent 能力",
        "description": "提交规范 + 分支策略 + 贡献统计",
        "icon": "🌿",
    },
    # 使用指南
    {
        "id": "quick-start",
        "title": "快速开始",
        "category": "guides",
        "category_label": "使用指南",
        "description": "从注册项目到第一次审查的完整流程",
        "icon": "🚀",
    },
    {
        "id": "autofix-guide",
        "title": "AutoFix 自动修复",
        "category": "guides",
        "category_label": "使用指南",
        "description": "Ruff 自动修复 + 补丁预览 + 一键应用",
        "icon": "🔧",
    },
    {
        "id": "incremental-review",
        "title": "增量审查",
        "category": "guides",
        "category_label": "使用指南",
        "description": "Git diff 场景、PR 审查流程",
        "icon": "📊",
    },
    # 工程实践
    {
        "id": "performance-and-observability",
        "title": "审查性能优化 + 过程可观测性",
        "category": "practices",
        "category_label": "工程实践",
        "description": "Semgrep 本地化 / 跳过收尾 LLM / 步骤持久化（完整复盘）",
        "icon": "⚡",
    },
]


class DocMeta(BaseModel):
    id: str
    title: str
    category: str
    category_label: str
    description: str
    icon: str


class DocContent(BaseModel):
    id: str
    title: str
    category: str
    html: str


@router.get("", response_model=list[DocMeta])
async def list_docs():
    """获取所有文档目录"""
    return [DocMeta(**doc) for doc in DOCS_CATALOG]


@router.get("/{category}/{doc_id}", response_model=DocContent)
async def get_doc(category: str, doc_id: str):
    """获取指定文档的 HTML 内容"""
    # 查找元数据
    meta = next((d for d in DOCS_CATALOG if d["id"] == doc_id and d["category"] == category), None)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 读取 HTML 文件
    html_file = DOCS_DIR / category / f"{doc_id}.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail=f"文档内容文件不存在: {html_file.name}")

    html_content = html_file.read_text(encoding="utf-8")
    return DocContent(
        id=doc_id,
        title=meta["title"],
        category=category,
        html=html_content,
    )
