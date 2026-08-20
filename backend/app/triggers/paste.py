"""代码粘贴触发器 — 接收用户粘贴的代码内容"""

import tempfile
from pathlib import Path

import structlog

from app.triggers.base import BaseTrigger, TriggerResult
from app.triggers.registry import trigger_registry

logger = structlog.get_logger()


@trigger_registry.register
class CodePasteTrigger(BaseTrigger):
    """接收用户粘贴的代码片段，保存为临时文件后返回审查列表"""

    name = "code_paste"
    description = "粘贴代码片段进行审查"

    async def execute(
        self,
        *,
        code: str,
        filename: str = "pasted_code.py",
        **kwargs,
    ) -> TriggerResult:
        """
        Args:
            code: 用户粘贴的代码内容
            filename: 文件名（用于推断语言和报告展示）
        """
        if not code or not code.strip():
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error="代码内容不能为空",
            )

        # 保存到临时文件
        tmp_dir = Path(tempfile.mkdtemp(prefix="review_paste_"))
        file_path = tmp_dir / filename
        file_path.write_text(code, encoding="utf-8")

        logger.info("代码粘贴触发器", filename=filename, size=len(code))

        return TriggerResult(
            success=True,
            trigger_type=self.name,
            files=[filename],
            metadata={
                "temp_dir": str(tmp_dir),
                "filename": filename,
                "size_bytes": len(code.encode("utf-8")),
            },
        )
