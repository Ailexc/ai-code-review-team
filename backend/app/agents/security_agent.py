"""安全审查 Agent — 使用 Semgrep 进行静态安全分析"""

import json
import subprocess
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger()

# Semgrep 规则集（按语言）
SEMGREP_RULESETS = {
    "python": [
        "p/python", "p/flask", "p/django", "p/sqlalchemy",
        "p/python_audit", "p/bandit",
    ],
    "javascript": ["p/javascript", "p/nodejs", "p/react", "p/expressjs"],
    "typescript": ["p/typescript", "p/nodejs", "p/react", "p/expressjs"],
    "java": ["p/java", "p/spring"],
    "go": ["p/golang"],
    "default": ["p/security-audit", "p/owasp-top-ten"],
}

# 严重程度映射
SEVERITY_MAP = {
    "ERROR": "critical",
    "WARNING": "warning",
    "INFO": "suggestion",
}


class SecurityAgent(BaseAgent):
    """安全审查 Agent — 使用 Semgrep 扫描代码漏洞"""

    name = "security"
    description = "代码安全审查（Semgrep 静态分析）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行 Semgrep 安全扫描"""
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        # 选择规则集
        language = self._detect_language(path)
        rulesets = SEMGREP_RULESETS.get(language, SEMGREP_RULESETS["default"])

        findings = []
        for ruleset in rulesets:
            try:
                results = self._run_semgrep(path, ruleset, file_paths)
                findings.extend(results)
            except Exception as e:
                logger.warning("Semgrep 规则集执行失败", ruleset=ruleset, error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("安全扫描完成", path=project_path, findings=len(unique))
        return unique

    def _run_semgrep(
        self,
        path: Path,
        config: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行单个 Semgrep 规则集"""
        cmd = [
            "semgrep", "scan",
            "--config", config,
            "--json",
            "--no-git-ignore",
            "--timeout", "30",
            "--max-target-bytes", "1000000",
        ]

        if file_paths:
            for fp in file_paths[:50]:  # 限制数量
                full_path = path / fp
                if full_path.exists():
                    cmd.append(str(full_path))
        else:
            cmd.append(str(path))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(path),
            )
        except subprocess.TimeoutExpired:
            logger.warning("Semgrep 超时", config=config)
            return []
        except FileNotFoundError:
            logger.error("semgrep 命令未找到")
            return []

        if result.returncode not in (0, 1):  # 1 = findings found
            logger.warning("Semgrep 异常退出", code=result.returncode, stderr=result.stderr[:500])
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_results(data)

    def _parse_results(self, data: dict) -> list[dict[str, Any]]:
        """解析 Semgrep JSON 输出"""
        findings = []
        for result in data.get("results", []):
            severity_raw = result.get("extra", {}).get("severity", "WARNING")
            severity = SEVERITY_MAP.get(severity_raw, "warning")

            findings.append({
                "rule_id": result.get("check_id", ""),
                "severity": severity,
                "message": result.get("extra", {}).get("message", ""),
                "file_path": result.get("path", ""),
                "line_start": result.get("start", {}).get("line"),
                "line_end": result.get("end", {}).get("line"),
                "code_snippet": result.get("extra", {}).get("lines", "")[:500],
                "suggestion": result.get("extra", {}).get("fix", "") or result.get("extra", {}).get("metadata", {}).get("fix", ""),
            })
        return findings

    def _detect_language(self, path: Path) -> str:
        """检测项目主要语言"""
        indicators = {
            "python": ["*.py", "pyproject.toml", "setup.py", "requirements.txt"],
            "typescript": ["*.ts", "*.tsx", "tsconfig.json"],
            "javascript": ["*.js", "*.jsx", "package.json"],
            "java": ["*.java", "pom.xml", "build.gradle"],
            "go": ["*.go", "go.mod"],
        }

        scores: dict[str, int] = {}
        for lang, patterns in indicators.items():
            count = 0
            for pattern in patterns:
                if "*" in pattern:
                    count += len(list(path.rglob(pattern))[:100])
                else:
                    count += 1 if (path / pattern).exists() else 0
            scores[lang] = count

        if not scores or max(scores.values()) == 0:
            return "default"
        return max(scores, key=scores.get)
