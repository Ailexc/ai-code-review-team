"""规则挖掘服务测试"""

import pytest
from pathlib import Path

from app.services.rule_miner import RuleMiner


def test_extract_pattern_with_rule_id():
    """应从 message 提取规则 ID"""
    miner = RuleMiner()
    assert miner._extract_pattern("[PERF-N+1] 循环内 ORM 调用") == "PERF-N+1"
    assert miner._extract_pattern("[SEC-001] SQL 注入") == "SEC-001"


def test_extract_pattern_no_rule_id():
    """无规则 ID 时应提取前 50 字符"""
    miner = RuleMiner()
    pattern = miner._extract_pattern("这是一个没有规则 ID 的普通消息")
    assert pattern is not None
    assert len(pattern) <= 50


def test_extract_pattern_empty():
    """空消息应返回 None"""
    miner = RuleMiner()
    assert miner._extract_pattern("") is None
    assert miner._extract_pattern(None) is None


@pytest.mark.asyncio
async def test_mine_from_history_empty():
    """无历史数据时应返回空"""
    miner = RuleMiner()
    rules = await miner.mine_from_history(min_occurrences=3)
    assert isinstance(rules, list)


@pytest.mark.asyncio
async def test_get_active_rules_empty():
    """无规则时应返回空列表"""
    miner = RuleMiner()
    rules = await miner.get_active_rules()
    assert isinstance(rules, list)