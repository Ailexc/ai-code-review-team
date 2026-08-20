"""审查 Agent 基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentFinding:
    """Agent 发现的问题"""
    rule_id: str = ""
    severity: str = "warning"  # critical / warning / suggestion / nitpick
    message: str = ""
    file_path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    code_snippet: str = ""
    suggestion: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """审查 Agent 基类"""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """分析代码，返回发现列表"""
        ...
