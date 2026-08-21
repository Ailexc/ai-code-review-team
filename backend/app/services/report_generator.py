"""审查报告生成器"""

from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()


class ReportGenerator:
    """生成 Markdown 格式的审查报告"""

    def generate(
        self,
        review: Any,
        findings: list[Any],
        project_name: str = "Unknown",
    ) -> str:
        """生成审查报告"""
        lines = []

        # 标题
        lines.append(f"# 代码审查报告")
        lines.append("")

        # 基本信息
        lines.append("## 审查信息")
        lines.append("")
        lines.append(f"| 项目 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 项目名称 | {project_name} |")
        lines.append(f"| 审查ID | `{review.id}` |")
        lines.append(f"| 审查类型 | {review.review_type} |")
        lines.append(f"| 触发方式 | {review.trigger_type} |")
        lines.append(f"| 状态 | {self._status_badge(review.status)} |")
        lines.append(f"| 开始时间 | {self._format_time(review.started_at)} |")
        lines.append(f"| 完成时间 | {self._format_time(review.completed_at)} |")
        lines.append(f"| 耗时 | {review.duration_seconds or 0}s |")
        lines.append("")

        # 统计摘要
        lines.append("## 统计摘要")
        lines.append("")
        lines.append(f"| 严重程度 | 数量 |")
        lines.append(f"|----------|------|")
        if review.critical_count:
            lines.append(f"| 🔴 严重 | {review.critical_count} |")
        if review.warning_count:
            lines.append(f"| 🟡 警告 | {review.warning_count} |")
        if review.suggestion_count:
            lines.append(f"| 🔵 建议 | {review.suggestion_count} |")
        if review.nitpick_count:
            lines.append(f"| ⚪ 细节 | {review.nitpick_count} |")
        lines.append(f"| **总计** | **{review.total_findings}** |")
        lines.append("")

        if review.summary:
            lines.append(f"> {review.summary}")
            lines.append("")

        # 问题详情
        if findings:
            lines.append("## 问题详情")
            lines.append("")

            # 按严重程度分组
            critical = [f for f in findings if f.severity == "critical"]
            warning = [f for f in findings if f.severity == "warning"]
            suggestion = [f for f in findings if f.severity == "suggestion"]

            if critical:
                lines.append("### 🔴 严重问题")
                lines.append("")
                for i, f in enumerate(critical, 1):
                    lines.extend(self._format_finding(i, f))
                    lines.append("")

            if warning:
                lines.append("### 🟡 警告")
                lines.append("")
                for i, f in enumerate(warning, 1):
                    lines.extend(self._format_finding(i, f))
                    lines.append("")

            if suggestion:
                lines.append("### 🔵 建议")
                lines.append("")
                for i, f in enumerate(suggestion, 1):
                    lines.extend(self._format_finding(i, f))
                    lines.append("")
        else:
            lines.append("## ✅ 未发现问题")
            lines.append("")
            lines.append("本次审查未发现任何安全问题。")
            lines.append("")

        # 页脚
        lines.append("---")
        lines.append("")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        lines.append("*由 AI Code Review Team 自动生成*")

        return "\n".join(lines)

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

        lines.append(f"- **Agent**: {finding.agent_name}")
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

    def _status_badge(self, status: str) -> str:
        """状态徽章"""
        badges = {
            "pending": "⏳ 待执行",
            "running": "🔄 执行中",
            "completed": "✅ 已完成",
            "failed": "❌ 失败",
        }
        return badges.get(status, status)

    def _format_time(self, dt: Any) -> str:
        """格式化时间"""
        if dt is None:
            return "-"
        if isinstance(dt, str):
            return dt[:19]
        return dt.strftime("%Y-%m-%d %H:%M:%S")
