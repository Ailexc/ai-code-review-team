"""触发器注册表"""

from typing import Type

import structlog

from app.triggers.base import BaseTrigger

logger = structlog.get_logger()


class TriggerRegistry:
    """触发器注册表 — 管理所有已注册的触发器类型"""

    def __init__(self):
        self._triggers: dict[str, Type[BaseTrigger]] = {}

    def register(self, trigger_cls: Type[BaseTrigger]) -> Type[BaseTrigger]:
        """注册触发器类（可用作装饰器）"""
        name = trigger_cls.name
        if not name:
            raise ValueError(f"{trigger_cls.__name__} 必须定义 name 属性")
        if name in self._triggers:
            raise ValueError(f"触发器 '{name}' 已注册")
        self._triggers[name] = trigger_cls
        logger.info("注册触发器", name=name, cls=trigger_cls.__name__)
        return trigger_cls

    def get(self, name: str) -> Type[BaseTrigger] | None:
        """按名称获取触发器类"""
        return self._triggers.get(name)

    def create(self, name: str, **kwargs) -> BaseTrigger:
        """创建触发器实例"""
        cls = self._triggers.get(name)
        if cls is None:
            raise KeyError(f"未知触发器类型: {name}，可用: {list(self._triggers.keys())}")
        return cls(**kwargs)

    def list_triggers(self) -> list[dict[str, str]]:
        """列出所有已注册的触发器"""
        return [
            {"name": cls.name, "description": cls.description}
            for cls in self._triggers.values()
        ]


# 全局注册表
trigger_registry = TriggerRegistry()
