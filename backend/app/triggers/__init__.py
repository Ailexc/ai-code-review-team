"""触发器模块"""

from app.triggers.base import BaseTrigger, TriggerResult
from app.triggers.registry import trigger_registry

__all__ = ["BaseTrigger", "TriggerResult", "trigger_registry"]
