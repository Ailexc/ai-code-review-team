"""CLI 触发器 — 从命令行接收文件列表"""

import structlog

from app.triggers.base import BaseTrigger, TriggerResult
from app.triggers.registry import trigger_registry

logger = structlog.get_logger()


@trigger_registry.register
class CLITrigger(BaseTrigger):
    """CLI 触发器 — 接收直接传入的文件列表"""

    name = "cli"
    description = "从命令行直接传入文件列表"

    async def execute(self, *, files: list[str], **kwargs) -> TriggerResult:
        """
        Args:
            files: 文件路径列表
        """
        if not files:
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error="文件列表不能为空",
            )

        logger.info("CLI 触发器", file_count=len(files))

        return TriggerResult(
            success=True,
            trigger_type=self.name,
            files=files,
            metadata={"file_count": len(files)},
        )
