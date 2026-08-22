"""审查报告生成器 — Markdown 与 HTML 两种格式"""

import html
from datetime import datetime
from typing import Any, Optional

import structlog

logger = structlog.get_logger()

SEVERITY_ORDER = ["critical", "warning", "suggestion", "nitpick"]
SEVERITY_LABELS = {
    "critical": "🔴 严重",
    "warning": "🟡 警告",
    "suggestion": "🔵 建议",
    "nitpick": "⚪ 细节",
}
AGENT_LABELS = {
    "security": "安全审查",
    "code_style": "代码规范",
    "dependency": "依赖审查",
    "test_coverage": "测试覆盖",
    "performance": "性能分析",
    "git_review": "Git 审查",
}


class ReportGenerator:
    """生成 Markdown / HTML 格式的审查报告"""

    def generate(
        self,
        review: Any,
        findings: list[Any],
        project_name: str = "Unknown",
    ) -> str:
        """生成 Markdown 报告"""
        lines = []
        lines.append("# 代码审查报告")
        lines.append("")

        lines.append("## 审查信息")
        lines.append("")
        lines.append("| 项目 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 项目名称 | {project_name} |")
        lines.append(f"| 审查ID | `{review.id}` |")
        lines.append(f"| 审查类型 | {self._review_type_label(review.review_type)} |")
        lines.append(f"| 触发方式 | {review.trigger_type} |")
        lines.append(f"| 状态 | {self._status_badge(review.status)} |")
        lines.append(f"| 开始时间 | {self._format_time(review.started_at)} |")
        lines.append(f"| 完成时间 | {self._format_time(review.completed_at)} |")
        lines.append(f"| 耗时 | {review.duration_seconds or 0}s |")
        lines.append("")

        # 统计摘要
        lines.append("## 统计摘要")
        lines.append("")
        lines.append("| 严重程度 | 数量 |")
        lines.append("|----------|------|")
        for sev in SEVERITY_ORDER:
            count = getattr(review, f"{sev}_count", 0)
            if count:
                lines.append(f"| {SEVERITY_LABELS.get(sev, sev)} | {count} |")
        lines.append(f"| **总计** | **{review.total_findings}** |")
        lines.append("")

        # 按 Agent 分布
        if findings:
            lines.append("| Agent | 数量 |")
            lines.append("|-------|------|")
            by_agent: dict[str, int] = {}
            for f in findings:
                by_agent[f.agent_name] = by_agent.get(f.agent_name, 0) + 1
            for agent, count in by_agent.items():
                lines.append(f"| {AGENT_LABELS.get(agent, agent)} | {count} |")
            lines.append("")

        if review.summary:
            lines.append(f"> {review.summary}")
            lines.append("")

        # 问题详情（按 Agent + 严重程度分组）
        if findings:
            lines.append("## 问题详情")
            lines.append("")
            grouped: dict[str, list[Any]] = {}
            for f in findings:
                grouped.setdefault(f.agent_name, []).append(f)

            for agent in sorted(grouped, key=lambda a: 0 if a == "security" else 1):
                agent_findings = grouped[agent]
                lines.append(f"### {AGENT_LABELS.get(agent, agent)} ({len(agent_findings)})")
                lines.append("")
                for sev in SEVERITY_ORDER:
                    group = [f for f in agent_findings if f.severity == sev]
                    if not group:
                        continue
                    lines.append(f"#### {SEVERITY_LABELS.get(sev, sev)}")
                    lines.append("")
                    for i, f in enumerate(group, 1):
                        lines.extend(self._format_finding(i, f))
                        lines.append("")
        else:
            lines.append("## ✅ 未发现问题")
            lines.append("")
            lines.append("本次审查未发现任何问题。")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        lines.append("*由 AI Code Review Team 自动生成*")

        return "\n".join(lines)

    def generate_html(
        self,
        review: Any,
        findings: list[Any],
        project_name: str = "Unknown",
    ) -> str:
        """生成 HTML 报告（浏览器可读）"""
        sev_color = {
            "critical": "#ff4d4f",
            "warning": "#faad14",
            "suggestion": "#1677ff",
            "nitpick": "#8c8c8c",
        }

        def _finding_card(f: Any, index: int) -> str:
            loc = ""
            if f.file_path:
                loc = f.file_path
                if f.line_number:
                    loc += f":{f.line_number}"
            snippet = html.escape(f.code_snippet or "")
            return f"""
            <div style="border:1px solid #eee;border-left:4px solid {sev_color.get(f.severity, '#999')};border-radius:6px;padding:12px 16px;margin:10px 0;background:#fff;">
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <span style="font-weight:600;color:{sev_color.get(f.severity, '#333')};">#{index} {html.escape(f.message)}</span>
                <span style="background:{sev_color.get(f.severity, '#eee')};color:#fff;padding:1px 8px;border-radius:10px;font-size:12px;">{f.severity}</span>
                {f'<code style="background:#f5f5f5;padding:2px 6px;border-radius:4px;font-size:12px;">{html.escape(loc)}</code>' if loc else ''}
              </div>
              {f'<pre style="background:#f6f8fa;padding:10px;border-radius:4px;overflow:auto;font-size:13px;margin-top:8px;"><code>{snippet}</code></pre>' if snippet else ''}
              {f'<div style="margin-top:8px;color:#333;"><strong>修复建议：</strong>{html.escape(f.suggestion or "")}</div>' if f.suggestion else ''}
            </div>"""

        cards = ""
        if findings:
            for i, f in enumerate(findings, 1):
                cards += _finding_card(f, i)
        else:
            cards = '<p style="color:#52c41a;">✅ 本次审查未发现任何问题。</p>'

        sev_rows = ""
        for sev in SEVERITY_ORDER:
            count = getattr(review, f"{sev}_count", 0)
            if count:
                sev_rows += f'<tr><td>{SEVERITY_LABELS.get(sev, sev)}</td><td style="color:{sev_color.get(sev, "#333")};font-weight:600;">{count}</td></tr>'

        return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>代码审查报告 - {html.escape(project_name)}</title>
<style>
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background:#f0f2f5; margin:0; padding:24px; }}
.container {{ max-width:900px; margin:0 auto; }}
.header {{ background:linear-gradient(135deg,#1677ff,#0958d9); color:#fff; padding:24px 32px; border-radius:10px; margin-bottom:20px; }}
.header h1 {{ margin:0 0 8px; }}
.meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
.card {{ background:#fff; border-radius:8px; padding:16px 20px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,0.06); }}
table {{ border-collapse:collapse; width:100%; }}
td,th {{ border:1px solid #eee; padding:8px 12px; text-align:left; }}
.footer {{ color:#999; font-size:12px; text-align:center; margin-top:24px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>代码审查报告</h1>
    <div>项目：{html.escape(project_name)} ｜ 审查类型：{self._review_type_label(review.review_type)} ｜ 状态：{self._status_badge(review.status)}</div>
    <div style="margin-top:8px;font-size:13px;opacity:0.9;">审查ID：{review.id} ｜ 触发方式：{review.trigger_type} ｜ 耗时：{review.duration_seconds or 0}s</div>
  </div>

  <div class="card">
    <h2 style="margin-top:0;">统计摘要</h2>
    <table>
      <tr><th>严重程度</th><th>数量</th></tr>
      {sev_rows}
      <tr><td><strong>总计</strong></td><td><strong>{review.total_findings}</strong></td></tr>
    </table>
    {f'<p style="margin-top:12px;">{html.escape(review.summary or "")}</p>' if review.summary else ''}
  </div>

  <div class="card">
    <h2 style="margin-top:0;">问题详情（{len(findings)}）</h2>
    {cards}
  </div>

  <div class="footer">报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ｜ 由 AI Code Review Team 自动生成</div>
</div>
</body>
</html>"""

    def _format_finding(self, index: int, finding: Any) -> list[str]:
        """格式化单个发现"""
        lines = []
        lines.append(f"**{index}. {finding.message}**")
        lines.append("")

        if finding.file_path:
            location = finding.file_path
            if finding.line_number:
                location += f":{finding.line_number}"
            lines.append(f"- **位置**: `{location}`")

        lines.append(f"- **Agent**: {AGENT_LABELS.get(finding.agent_name, finding.agent_name)}")
        lines.append(f"- **分类**: {finding.category}")
        lines.append(f"- **状态**: {finding.status}")

        if finding.code_snippet:
            lines.append("")
            lines.append("```python")
            lines.append(finding.code_snippet[:300])
            lines.append("```")

        if finding.suggestion:
            lines.append("")
            lines.append(f"**修复建议**: {finding.suggestion}")

        return lines

    def _review_type_label(self, review_type: str) -> str:
        labels = {
            "full": "综合审查",
            "security": "安全审查",
            "code_style": "代码规范审查",
            "dependency": "依赖审查",
            "test_coverage": "测试覆盖审查",
        }
        return labels.get(review_type, review_type)

    def _status_badge(self, status: str) -> str:
        badges = {
            "pending": "⏳ 待执行",
            "running": "🔄 执行中",
            "completed": "✅ 已完成",
            "failed": "❌ 失败",
        }
        return badges.get(status, status)

    def _format_time(self, dt: Any) -> str:
        if dt is None:
            return "-"
        if isinstance(dt, str):
            return dt[:19]
        return dt.strftime("%Y-%m-%d %H:%M:%S")
