"""context_enhancer 并发安全重构的单元测试"""

from app.agents import context_enhancer as ce


class TestEngineCache:
    def setup_method(self):
        ce.clear_engine_cache()

    def test_cache_hit_same_instance(self):
        """同一项目重复获取应返回同一实例（并行 Crew 共享索引）"""
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "pkg"), exist_ok=True)
            with open(os.path.join(d, "pkg", "m.py"), "w") as f:
                f.write("def foo():\n    return 1\n")
            e1 = ce.get_or_build_engine(d)
            e2 = ce.get_or_build_engine(d)
            assert e1 is not None
            assert e1 is e2

    def test_build_failure_returns_none(self):
        """构建抛异常时返回 None（不缓存失败）"""
        from unittest.mock import patch

        with patch("app.agents.context_enhancer.ContextEngine") as MockEngine:
            MockEngine.side_effect = RuntimeError("boom")
            assert ce.get_or_build_engine("/some-path") is None

    def test_cache_distinct_by_file_paths(self):
        """不同 file_paths 视为不同 key"""
        # 用真实存在的目录验证缓存命中（test-projects 下任一）
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "pkg"), exist_ok=True)
            with open(os.path.join(d, "pkg", "m.py"), "w") as f:
                f.write("def foo():\n    return 1\n")
            e1 = ce.get_or_build_engine(d)
            e2 = ce.get_or_build_engine(d)
            assert e1 is not None
            assert e1 is e2
            e3 = ce.get_or_build_engine(d, ["pkg/m.py"])
            assert e3 is not None
            assert e3 is not e1

    def test_enhance_prompt_without_engine_returns_base(self):
        """无引擎上下文时原样返回（优雅降级）"""
        assert ce.enhance_prompt("x.py", "BASE") == "BASE"

    def test_enhance_prompt_with_engine_injects_context(self):
        import tempfile, os
        from app.agents.context_enhancer import set_current_engine, reset_current_engine

        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "pkg"), exist_ok=True)
            with open(os.path.join(d, "pkg", "m.py"), "w") as f:
                f.write("def foo():\n    return 1\n")
            engine = ce.get_or_build_engine(d)
            token = set_current_engine(engine)
            try:
                out = ce.enhance_prompt("pkg/m.py", "BASE")
                assert out != "BASE"
                assert "代码库上下文" in out
                assert out.endswith("BASE")
            finally:
                reset_current_engine(token)
            # reset 后恢复降级行为
            assert ce.enhance_prompt("pkg/m.py", "BASE") == "BASE"

    def test_cache_eviction(self):
        ce.clear_engine_cache()
        import tempfile, os
        for i in range(10):
            d = tempfile.mkdtemp(prefix=f"ce-test-{i}-")
            os.makedirs(os.path.join(d, "p"), exist_ok=True)
            with open(os.path.join(d, "p", "a.py"), "w") as f:
                f.write("x = 1\n")
            ce.get_or_build_engine(d)
        assert len(ce._ENGINE_CACHE) <= ce._ENGINE_CACHE_MAX
