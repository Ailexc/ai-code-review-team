"""Git diff 解析器测试"""

import pytest

from app.services.diff_parser import parse_unified_diff, DiffResult, ChangedFile


SAMPLE_DIFF = """diff --git a/app/main.py b/app/main.py
index 1234567..abcdefg 100644
--- a/app/main.py
+++ b/app/main.py
@@ -10,5 +10,7 @@
 def old_func():
     return 1

-def changed_line():
-    return 2
+def changed_line():
+    return 2
+    # new comment
+
+def new_func():
+    return 3
diff --git a/app/new_file.py b/app/new_file.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/app/new_file.py
@@ -0,0 +1,2 @@
+def brand_new():
+    return 42
diff --git a/app/deleted.py b/app/deleted.py
deleted file mode 100644
index 1234567..0000000
--- a/app/deleted.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def gone():
-    return 0
"""


def test_parse_diff_extracts_files():
    result = parse_unified_diff(SAMPLE_DIFF)
    assert len(result.files) == 3
    paths = [f.path for f in result.files]
    assert "app/main.py" in paths
    assert "app/new_file.py" in paths
    assert "app/deleted.py" in paths


def test_parse_diff_file_status():
    result = parse_unified_diff(SAMPLE_DIFF)
    by_path = {f.path: f for f in result.files}
    assert by_path["app/new_file.py"].status == "added"
    assert by_path["app/deleted.py"].status == "deleted"
    assert by_path["app/main.py"].status == "modified"


def test_parse_diff_added_lines():
    result = parse_unified_diff(SAMPLE_DIFF)
    main = next(f for f in result.files if f.path == "app/main.py")
    # 新增行：changed_line(12), comment(13), blank(14), new_func def(15), return(16)
    assert len(main.added_lines) >= 4
    # 行号应连续递增
    assert main.added_lines[0] == 12


def test_parse_diff_new_file_lines():
    result = parse_unified_diff(SAMPLE_DIFF)
    new_file = next(f for f in result.files if f.path == "app/new_file.py")
    assert new_file.added_lines == [1, 2]


def test_parse_diff_deleted_no_added():
    result = parse_unified_diff(SAMPLE_DIFF)
    deleted = next(f for f in result.files if f.path == "app/deleted.py")
    assert deleted.status == "deleted"
    assert len(deleted.added_lines) == 0


def test_parse_diff_changed_file_paths_excludes_deleted():
    result = parse_unified_diff(SAMPLE_DIFF)
    assert "app/deleted.py" not in result.changed_file_paths


def test_parse_empty_diff():
    result = parse_unified_diff("")
    assert result.files == []
    assert result.total_added_lines == 0


def test_diff_result_properties():
    result = DiffResult(files=[
        ChangedFile(path="a.py", added_lines=[1, 2]),
        ChangedFile(path="b.py", added_lines=[5]),
    ])
    assert result.changed_file_paths == ["a.py", "b.py"]
    assert result.total_added_lines == 3
