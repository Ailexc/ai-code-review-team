"""健康度评分 — 基于审查发现计算项目质量分数（0-100）

评分模型（负分制，从 100 起扣）：
- critical: -15 分/个
- warning:  -5 分/个
- suggestion: -2 分/个
- nitpick: -0.5 分/个
- 无测试/无依赖锁版本等结构性问题额外扣分（已含在 finding 严重度中）
下限 0，上限 100。
"""

from app.models.review import Review
from app.models.finding import Finding

# 严重程度扣分权重
SEVERITY_PENALTY = {
    "critical": 15.0,
    "warning": 5.0,
    "suggestion": 2.0,
    "nitpick": 0.5,
}


def compute_health_score(review: Review, findings: list[Finding] | None = None) -> float:
    """根据审查发现计算健康度分数（0-100）

    Args:
        review: 审查记录（用其 *_count 字段）
        findings: 发现列表（可选，若提供则按实际统计，否则用 review 计数字段）
    """
    score = 100.0
    if findings:
        for f in findings:
            score -= SEVERITY_PENALTY.get(f.severity, 1.0)
    else:
        score -= review.critical_count * SEVERITY_PENALTY["critical"]
        score -= review.warning_count * SEVERITY_PENALTY["warning"]
        score -= review.suggestion_count * SEVERITY_PENALTY["suggestion"]
        score -= review.nitpick_count * SEVERITY_PENALTY["nitpick"]

    return max(0.0, min(100.0, round(score, 1)))


def health_score_color(score: float) -> str:
    """健康度对应的颜色等级（供前端参考）"""
    if score >= 80:
        return "green"
    if score >= 60:
        return "orange"
    if score >= 40:
        return "gold"
    return "red"
