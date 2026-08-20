"""文件上传触发器 — 接收上传的文件/压缩包"""

import zipfile
import tarfile
import tempfile
from pathlib import Path

import structlog

from app.triggers.base import BaseTrigger, TriggerResult
from app.triggers.registry import trigger_registry

logger = structlog.get_logger()

# 支持的压缩格式
ARCHIVE_SUFFIXES = {'.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2'}


@trigger_registry.register
class FileUploadTrigger(BaseTrigger):
    """接收上传的文件或压缩包，解压后收集代码文件"""

    name = "file_upload"
    description = "上传文件或压缩包进行审查"

    async def execute(
        self,
        *,
        file_path: str,
        **kwargs,
    ) -> TriggerResult:
        """
        Args:
            file_path: 上传文件在服务端的临时路径
        """
        source = Path(file_path)

        if not source.exists():
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error=f"文件不存在: {file_path}",
            )

        # 如果是压缩包，先解压
        extract_dir = Path(tempfile.mkdtemp(prefix="review_upload_"))
        try:
            if source.suffix == '.zip':
                with zipfile.ZipFile(source, 'r') as zf:
                    zf.extractall(extract_dir)
            elif source.suffix in ('.tar', '.tgz') or source.name.endswith(('.tar.gz', '.tar.bz2')):
                with tarfile.open(source, 'r:*') as tf:
                    tf.extractall(extract_dir)
            else:
                # 单文件，复制到临时目录
                dest = extract_dir / source.name
                dest.write_bytes(source.read_bytes())
        except (zipfile.BadZipFile, tarfile.TarError) as e:
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error=f"解压失败: {e}",
            )

        files = self._collect_code_files(extract_dir)
        if not files:
            return TriggerResult(
                success=False,
                trigger_type=self.name,
                error="上传的文件中未找到代码文件",
            )

        logger.info("文件上传触发器", file=source.name, extracted_count=len(files))

        return TriggerResult(
            success=True,
            trigger_type=self.name,
            files=files,
            metadata={
                "original_file": source.name,
                "extract_dir": str(extract_dir),
                "file_count": len(files),
            },
        )
