"""本地目录触发器 — 扫描本地目录中的代码文件"""

from pathlib import Path

import structlog

from app.triggers.base import BaseTrigger, TriggerResult
from app.triggers.registry import trigger_registry

logger = structlog.get_logger()


@trigger_registry.register
class LocalDirectoryTrigger(BaseTrigger):
    """扫描本地目录，收集代码文件列表用于审查"""

    name = "local_directory"
    description = "扫描本地目录中的代码文件"

    async def execute(self, *, path: str, **kwargs) -> TriggerResult:
        """
        Args:
            path: 本地目录的绝对路径
        """
        directory = Path(path)

        if not directory.exists():
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error=f"路径不存在: {path}",
            )

        if not directory.is_dir():
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error=f"路径不是目录: {path}",
            )

        try:
            files = self._collect_code_files(directory)
        except PermissionError:
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error=f"无权访问目录: {path}",
            )

        if not files:
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error=f"目录中未找到代码文件: {path}",
            )

        return TriggerResult(
            success=True,
            trigger_type=self.name,
            files=files,
            metadata={"directory": str(directory.resolve()), "file_count": len(files)},
        )
