"""触发器基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class TriggerResult:
    """触发器执行结果"""
    success: bool
    trigger_type: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseTrigger(ABC):
    """触发器基类

    所有触发器必须继承此类并实现 `execute` 方法。
    触发器负责收集待审查的代码文件列表。
    """

    # 子类必须定义
    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, **kwargs) -> TriggerResult:
        """执行触发器，返回待审查的文件列表"""
        ...

    def _collect_code_files(self, directory: Path, extensions: set[str] | None = None) -> list[str]:
        """递归收集目录中的代码文件

        Args:
            directory: 要扫描的目录
            extensions: 文件扩展名过滤，如 {'.py', '.js'}。None 则收集所有文本文件。

        Returns:
            文件路径列表（相对于 directory 的相对路径）
        """
        if extensions is None:
            extensions = {
                '.py', '.js', '.ts', '.tsx', '.jsx',
                '.java', '.go', '.rs', '.c', '.cpp', '.h',
                '.rb', '.php', '.swift', '.kt', '.scala',
                '.yml', '.yaml', '.toml', '.json', '.md',
            }

        skip_dirs = {
            'node_modules', '__pycache__', '.git', '.venv', 'venv',
            'dist', 'build', '.next', '.nuxt', 'target',
            '.tox', '.mypy_cache', '.pytest_cache', '.ruff_cache',
        }

        files = []
        for path in sorted(directory.rglob('*')):
            # 跳过隐藏目录和忽略目录
            parts = path.relative_to(directory).parts
            if any(p.startswith('.') or p in skip_dirs for p in parts):
                continue
            if path.is_file() and path.suffix in extensions:
                files.append(str(path.relative_to(directory)))

        logger.info("收集代码文件", directory=str(directory), count=len(files))
        return files
