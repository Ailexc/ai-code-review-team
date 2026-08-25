"""ReviewFlow — CrewAI Flows 外层编排（生产主路径，路线焊死）

Flows + Crews 双层架构：
- 外层 Flow：@start / @listen 确定性编排 parse → 并行 Crew → aggregate → report，
  状态用 ReviewState（Pydantic）管理，白盒可调试；
- 内层 Crew：crew_factory.build_review_crew() 为每个专业 Agent 构建独立 Crew，
  并行由 Flow 的「多 @listen 节点」机制提供（非 asyncio.gather）。

进度事件（flow_node_started/completed、agent_started/completed/failed）经
progress_emitter 推送，前端据此绘制「外层 Flow 节点 + 内层 Crew」双层视图。

本文件不存在任何降级路径：CrewAI 是唯一编排方式。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog
from crewai.flow.flow import Flow, and_, listen, start
from pydantic import BaseModel, Field

from app.agents.llm_client import get_active_llm_config
from app.flows.crew_factory import AGENT_PROFILES, build_crew_llm, build_review_crew, parse_crew_findings
from app.services.metrics import metrics
from app.services.progress import progress_emitter
from app.services.review_steps import review_step_recorder

logger = structlog.get_logger()

# review_type 片段 → agent_name（与 AGENT_PROFILES 对齐）
AGENT_REGISTRY: dict[str, str] = {
    "security": "security",
    "code_style": "code_style",
    "dependency": "dependency",
    "test_coverage": "test_coverage",
    "performance": "performance",
    "git_review": "git_review",
}


class ReviewState(BaseModel):
    """Flow 共享状态 — 在各节点间传递"""

    project_path: str = ""
    project_name: str = "Unknown"
    file_paths: list[str] | None = None
    review_type: str = "full"
    review_id: str = ""

    # 各 Agent 的产出
    findings_by_agent: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    total_findings: int = 0
    summary: str = ""


def _resolve_agents(review_type: str) -> list[str]:
    """根据审查类型解析参与的 Agent 列表"""
    if review_type == "full":
        return list(AGENT_REGISTRY.keys())
    if review_type in AGENT_REGISTRY:
        return [review_type]
    logger.warning("未知审查类型，回退到 security", review_type=review_type)
    return ["security"]


class ReviewFlow(Flow[ReviewState]):
    """代码审查编排 Flow（生产主路径）

    用法:
        flow = ReviewFlow()
        result = await flow.kickoff_async(ReviewState(project_path=..., review_type="full"))
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._llm = None

    # ---------- 辅助 ----------

    async def _get_llm(self):
        """获取 CrewAI LLM（复用项目 LLM 配置，实例级缓存）"""
        if self._llm is None:
            config = await get_active_llm_config()
            if not config:
                raise RuntimeError(
                    "未配置启用的 LLM 模型。请先在「设置 → 模型配置」中添加并启用模型，再发起审查。"
                )
            self._llm = build_crew_llm(config)
        return self._llm

    async def _emit(self, event: str, data: dict[str, Any]):
        """发布进度事件（无 review_id 时跳过，便于单元测试）"""
        if self.state.review_id:
            await progress_emitter.emit(self.state.review_id, event, data)

    async def _run_crew_node(self, agent_name: str):
        """内层 Crew 执行：构建独立 Crew 并 kickoff（上下文隔离）

        单个 Crew 失败不中断整体（记 agent_failed + 空结果），
        聚合节点继续处理其余 Agent 的结果。
        执行结果持久化到 review_steps（可观测性）。
        """
        state = self.state
        resolved = _resolve_agents(state.review_type)
        if agent_name not in resolved:
            await review_step_recorder.record(
                review_id=state.review_id, phase="outer_flow", node_type="skip_agent",
                status="skipped", agent_name=agent_name,
                action_text=(
                    f"按审查类型「{state.review_type}」，跳过 Agent「{agent_name}」"
                    f"（本次参与 Agent：{'、'.join(resolved)}）"
                ),
            )
            logger.info("ReviewFlow: 跳过 Agent", agent=agent_name, type=state.review_type)
            return

        profile = AGENT_PROFILES.get(agent_name, {})
        role = profile.get("role", agent_name)
        await self._emit("agent_started", {
            "agent": agent_name,
            "role": role,
            "goal": profile.get("goal", ""),
            "tool": f"{agent_name}_review_scan",
        })
        agent_start = time.monotonic()
        try:
            llm = await self._get_llm()
            crew = build_review_crew(agent_name, state.project_path, state.file_paths, llm)
            result = await crew.kickoff_async()
            findings = parse_crew_findings(result)
            state.findings_by_agent[agent_name] = findings
            duration_ms = int((time.monotonic() - agent_start) * 1000)
            metrics.record_agent_run(agent_name, True, time.monotonic() - agent_start, len(findings))
            await self._emit("agent_completed", {"agent": agent_name, "findings": len(findings)})
            logger.info("ReviewFlow: Crew 完成", agent=agent_name, findings=len(findings))
            await review_step_recorder.record(
                review_id=state.review_id, phase="inner_crew",
                node_type=f"run_{agent_name}_crew", status="completed",
                agent_name=agent_name,
                action_text=(
                    f"内层 Crew「{role}」执行：构建独立 Crew（Process.sequential），"
                    f"Agent 自主调用 {agent_name}_review_scan 工具完成扫描，产出 {len(findings)} 条发现"
                ),
                input_summary=f"项目：{state.project_name}（{state.project_path}）",
                output_summary=f"{len(findings)} 条发现",
                duration_ms=duration_ms,
                detail={"findings": len(findings), "tool": f"{agent_name}_review_scan", "role": role},
            )
        except Exception as e:
            metrics.record_agent_run(agent_name, False, time.monotonic() - agent_start, 0)
            logger.error("ReviewFlow: Crew 执行失败", agent=agent_name, error=str(e))
            state.findings_by_agent[agent_name] = []
            await self._emit("agent_failed", {"agent": agent_name, "error": str(e)})
            await review_step_recorder.record(
                review_id=state.review_id, phase="inner_crew",
                node_type=f"run_{agent_name}_crew", status="failed",
                agent_name=agent_name,
                action_text=f"内层 Crew「{role}」执行失败：{str(e)[:120]}",
                duration_ms=int((time.monotonic() - agent_start) * 1000),
                detail={"error": str(e), "role": role},
            )

    # ---------- 节点 1：解析 ----------

    @start()
    async def parse_project(self) -> None:
        """节点1：校验项目路径 + 预检 LLM 配置"""
        state = self.state
        await self._emit("flow_node_started", {"node": "parse_project", "label": "解析项目"})
        start = time.monotonic()
        action = "读取项目目录，校验路径并预检 LLM 配置"
        detail: dict[str, Any] = {}
        try:
            path = Path(state.project_path)
            if path.exists():
                try:
                    files = [p for p in path.rglob("*") if p.is_file()]
                    code_files = [
                        f for f in files
                        if f.suffix.lower() in {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java'}
                    ]
                    detail["total_files"] = len(files)
                    detail["code_files"] = len(code_files)
                    action += f"；扫描到 {len(files)} 个文件（代码 {len(code_files)}）"
                except Exception:
                    pass
            else:
                action += "；⚠️ 项目路径不存在"
            agents = _resolve_agents(state.review_type)
            detail["agents"] = agents
            action += f"；按审查类型「{state.review_type}」确定参与 Agent：{'、'.join(agents)}"
            await self._get_llm()
            status = "completed"
        except Exception as e:
            status = "failed"
            action += f"；失败：{str(e)[:100]}"
            detail["error"] = str(e)
        logger.info("ReviewFlow: 解析项目", path=state.project_path, type=state.review_type)
        await self._emit("flow_node_completed", {"node": "parse_project", "label": "解析项目"})
        await review_step_recorder.record(
            review_id=state.review_id, phase="outer_flow", node_type="parse_project",
            status=status, action_text=action,
            output_summary=f"参与 Agent：{len(detail.get('agents', []))} 个",
            duration_ms=int((time.monotonic() - start) * 1000), detail=detail,
        )
        if status == "failed":
            raise RuntimeError(detail.get("error", "项目解析失败"))

    # ---------- 节点 2：6 个内层 Crew 并行（Flow 多 @listen 机制）----------

    @listen(parse_project)
    async def run_security_crew(self) -> None:
        await self._run_crew_node("security")

    @listen(parse_project)
    async def run_code_style_crew(self) -> None:
        await self._run_crew_node("code_style")

    @listen(parse_project)
    async def run_dependency_crew(self) -> None:
        await self._run_crew_node("dependency")

    @listen(parse_project)
    async def run_test_coverage_crew(self) -> None:
        await self._run_crew_node("test_coverage")

    @listen(parse_project)
    async def run_performance_crew(self) -> None:
        await self._run_crew_node("performance")

    @listen(parse_project)
    async def run_git_review_crew(self) -> None:
        await self._run_crew_node("git_review")

    # ---------- 节点 3：聚合（等所有 Crew 完成）----------

    @listen(and_(
        run_security_crew,
        run_code_style_crew,
        run_dependency_crew,
        run_test_coverage_crew,
        run_performance_crew,
        run_git_review_crew,
    ))
    async def aggregate(self) -> None:
        """节点3：去重统计 + 生成摘要"""
        state = self.state
        await self._emit("flow_node_started", {"node": "aggregate", "label": "聚合结果"})
        start = time.monotonic()

        raw_count = sum(len(fs) for fs in state.findings_by_agent.values())
        seen: set[tuple] = set()
        all_findings: list[dict[str, Any]] = []
        for findings in state.findings_by_agent.values():
            for f in findings:
                key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
                if key not in seen:
                    seen.add(key)
                    all_findings.append(f)

        state.total_findings = len(all_findings)
        parts = []
        severity_dist: dict[str, int] = {}
        for sev, label in (("critical", "🔴"), ("warning", "🟡"), ("suggestion", "🔵"), ("nitpick", "⚪")):
            count = sum(1 for f in all_findings if f.get("severity") == sev)
            severity_dist[sev] = count
            if count:
                parts.append(f"{label} {count} 个{ {'critical':'严重','warning':'警告','suggestion':'建议','nitpick':'细节'}[sev] }")
        state.summary = "✅ 未发现问题" if not parts else f"发现 {state.total_findings} 个问题：" + "，".join(parts)

        logger.info("ReviewFlow: 聚合完成", total=state.total_findings)
        await self._emit("flow_node_completed", {
            "node": "aggregate", "label": "聚合结果", "total": state.total_findings,
        })
        await review_step_recorder.record(
            review_id=state.review_id, phase="outer_flow", node_type="aggregate",
            status="completed",
            action_text=(
                f"合并各 Agent 发现并去重：去重前 {raw_count} 条 → 去重后 {state.total_findings} 条；"
                f"严重度分布：" + "、".join(f"{sev} {n}" for sev, n in severity_dist.items() if n)
            ),
            input_summary=f"参与 Agent：{'、'.join(state.findings_by_agent.keys()) or '无'}",
            output_summary=state.summary,
            duration_ms=int((time.monotonic() - start) * 1000),
            detail={"raw": raw_count, "total": state.total_findings, "severity": severity_dist},
        )

    # ---------- 节点 4：完成 ----------

    @listen(aggregate)
    async def generate_report(self) -> ReviewState:
        """节点4：完成（报告生成在 API 层按需调用 ReportGenerator）"""
        await self._emit("flow_node_started", {"node": "generate_report", "label": "生成摘要"})
        logger.info("ReviewFlow: 编排完成", summary=self.state.summary)
        await self._emit("flow_node_completed", {"node": "generate_report", "label": "生成摘要"})
        await review_step_recorder.record(
            review_id=self.state.review_id, phase="outer_flow", node_type="generate_report",
            status="completed",
            action_text=f"生成审查总结摘要（供 API 层 ReportGenerator 生成完整报告）",
            input_summary=f"聚合后 {self.state.total_findings} 条发现",
            output_summary=self.state.summary,
            detail={"summary": self.state.summary, "total": self.state.total_findings},
        )
        return self.state


async def run_review_flow(
    project_path: str,
    review_type: str = "full",
    file_paths: list[str] | None = None,
    project_name: str = "Unknown",
    review_id: str = "",
) -> ReviewState:
    """便捷入口：运行 ReviewFlow 并返回最终状态（生产主路径）"""
    flow = ReviewFlow()
    inputs = {
        "project_path": project_path,
        "project_name": project_name,
        "file_paths": file_paths,
        "review_type": review_type,
        "review_id": review_id,
    }
    result = await flow.kickoff_async(inputs)
    # kickoff 返回 StateWithId 包装对象，其属性代理到底层 state
    return ReviewState(
        project_path=getattr(result, "project_path", project_path),
        project_name=getattr(result, "project_name", project_name),
        file_paths=getattr(result, "file_paths", file_paths),
        review_type=getattr(result, "review_type", review_type),
        review_id=getattr(result, "review_id", review_id),
        findings_by_agent=dict(getattr(result, "findings_by_agent", {}) or {}),
        total_findings=getattr(result, "total_findings", 0),
        summary=getattr(result, "summary", ""),
    )
