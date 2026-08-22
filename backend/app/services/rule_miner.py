"""规则挖掘服务 — 从历史审查记录中学习团队规范

对标 Qodo 的 Rule Miner / CodeRabbit 的持续学习：
1. 从历史 finding 中统计高频 message 模式
2. 提取团队反复标记的问题类型为规则
3. 结合用户反馈（确认/忽略/修复）调整规则权重
"""

import re
from collections import Counter
from typing import Any

import structlog
from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.models.finding import Finding
from app.models.review_rule import ReviewRule

logger = structlog.get_logger()

# 常见规则前缀（用于识别规则类型）
RULE_PREFIXES = {
    "PERF": "性能",
    "SEC": "安全",
    "STYLE": "规范",
    "DEP": "依赖",
    "TEST": "测试",
    "GIT": "Git",
    "LLM": "LLM 分析",
}


class RuleMiner:
    """规则挖掘器"""

    async def mine_from_history(self, min_occurrences: int = 3) -> list[ReviewRule]:
        """从历史 finding 中挖掘高频规则

        Args:
            min_occurrences: 最小出现次数（低于此不生成规则）

        Returns:
            新生成的规则列表
        """
        async with async_session_factory() as db:
            # 统计 message 前缀模式（按 rule_id 前缀 + message 关键词）
            result = await db.execute(
                select(Finding.agent_name, Finding.message, func.count(Finding.id).label("cnt"))
                .group_by(Finding.agent_name, Finding.message)
                .order_by(func.count(Finding.id).desc())
                .limit(50)
            )
            rows = result.all()

            # 提取高频模式
            patterns = Counter()
            for agent, message, cnt in rows:
                if cnt < min_occurrences:
                    continue
                # 提取 message 中的关键词模式
                key = self._extract_pattern(message)
                if key:
                    patterns[(agent, key)] += cnt

            # 生成规则
            new_rules = []
            for (agent, pattern), cnt in patterns.most_common(20):
                # 检查是否已存在相似规则
                existing = await db.execute(
                    select(ReviewRule).where(
                        ReviewRule.agent_name == agent,
                        ReviewRule.pattern == pattern,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                rule = ReviewRule(
                    name=f"{RULE_PREFIXES.get(agent.split('_')[0].upper(), '')} 高频问题: {pattern[:30]}",
                    description=f"从历史审查中自动挖掘的高频问题模式（出现 {cnt} 次）",
                    rule_type="pattern",
                    agent_name=agent,
                    severity="suggestion",
                    pattern=pattern,
                    source_message=pattern,
                    confidence=min(1.0, cnt / 10),
                    occurrence_count=cnt,
                    weight=min(2.0, 1.0 + cnt / 20),
                    source="auto",
                )
                db.add(rule)
                new_rules.append(rule)

            await db.commit()
            if new_rules:
                logger.info("规则挖掘完成", new_rules=len(new_rules))
            return new_rules

    def _extract_pattern(self, message: str) -> str | None:
        """从 message 提取可复用的模式

        提取规则 ID 前缀 + 核心关键词
        """
        if not message:
            return None
        # 提取 [RULE_ID] 前缀
        m = re.match(r"\[([A-Z0-9\-+]+)\]", message)
        if m:
            return m.group(1)
        # 提取前 50 字符作为模式
        return message[:50]

    async def apply_feedback(self, finding_id: str, action: str) -> None:
        """根据用户对 finding 的操作调整规则权重

        Args:
            finding_id: finding ID
            action: acknowledged(确认) / fixed(修复) / open(重新打开)
        """
        async with async_session_factory() as db:
            finding = await db.execute(select(Finding).where(Finding.id == finding_id))
            finding = finding.scalar_one_or_none()
            if not finding:
                return

            pattern = self._extract_pattern(finding.message)
            if not pattern:
                return

            # 查找匹配规则
            rule = await db.execute(
                select(ReviewRule).where(
                    ReviewRule.agent_name == finding.agent_name,
                    ReviewRule.pattern == pattern,
                )
            )
            rule = rule.scalar_one_or_none()

            if action == "fixed":
                # 用户修复了 → 规则有效，提高权重
                if rule:
                    rule.weight = min(3.0, rule.weight + 0.5)
                    rule.confidence = min(1.0, rule.confidence + 0.1)
                else:
                    # 创建新规则（用户主动修复的高频问题）
                    rule = ReviewRule(
                        name=f"用户确认修复: {pattern[:30]}",
                        description="用户主动修复的问题，标记为重要规则",
                        rule_type="preference",
                        agent_name=finding.agent_name,
                        severity=finding.severity,
                        pattern=pattern,
                        source_message=finding.message,
                        confidence=0.8,
                        occurrence_count=1,
                        weight=1.5,
                        source="feedback",
                    )
                    db.add(rule)
            elif action == "acknowledged":
                # 用户确认了 → 规则有效，轻微提高
                if rule:
                    rule.weight = min(3.0, rule.weight + 0.2)
            elif action == "open":
                # 用户重新打开 → 可能是误报，降低权重
                if rule:
                    rule.weight = max(0.1, rule.weight - 0.3)

            await db.commit()
            logger.info("规则反馈已应用", finding_id=finding_id, action=action)

    async def get_active_rules(self, agent_name: str | None = None) -> list[ReviewRule]:
        """获取启用的规则"""
        async with async_session_factory() as db:
            query = select(ReviewRule).where(ReviewRule.is_enabled == True)
            if agent_name:
                query = query.where(ReviewRule.agent_name == agent_name)
            query = query.order_by(ReviewRule.weight.desc())
            result = await db.execute(query)
            return result.scalars().all()


# 全局单例
rule_miner = RuleMiner()