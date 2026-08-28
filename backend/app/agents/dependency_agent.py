"""依赖审查 Agent — 依赖解析 + 漏洞扫描 + LLM 风险点评

确定性工具层：
- Python: pip-audit（查询 PyPI/OSV 漏洞库）
- JS:    npm registry API 查询（比对声明版本与最新版本，识别过时依赖）
LLM 补充：分析依赖清单，识别风险/弃用/过时/许可证问题。
"""

import asyncio
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.agents.base import BaseAgent
from app.agents.utils import extract_code_snippet

logger = structlog.get_logger()

# 漏洞严重程度映射（pip-audit 的 severity / CVE 评分近似）
SEVERITY_BY_CVE_SCORE = [
    (9.0, "critical"),
    (7.0, "warning"),
    (4.0, "suggestion"),
]
DEFAULT_VULN_SEVERITY = "warning"

# 依赖文件清单
MANIFEST_FILES = {
    "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "javascript": ["package.json"],
}

DEPENDENCY_PROMPT = """你是一个依赖管理专家。请分析以下项目的依赖清单，识别风险。

依赖清单内容:
```
{manifest}
```

请用 JSON 格式返回分析结果：
```json
{{
    "findings": [
        {{
            "rule_id": "DEP-001",
            "severity": "warning/suggestion",
            "message": "简短描述问题",
            "file_path": "依赖文件路径",
            "line_number": 行号或null,
            "code_snippet": "相关依赖行",
            "suggestion": "改进建议"
        }}
    ]
}}
```

审查重点:
1. 已知有漏洞历史的包（如旧版 django/flask/requests/lodash/axios 等）
2. 过时或长期未维护的包（建议升级到最新稳定版）
3. 冗余或冲突的依赖
4. 缺少版本约束（如未固定版本）的包
5. 不安全的许可证或来源不明的包

注意:
1. 只返回 JSON，不要有其他内容
2. 没有问题返回空数组: {{"findings": []}}
3. severity 分为: warning (需要处理), suggestion (建议)"""


class DependencyAgent(BaseAgent):
    """依赖审查 Agent"""

    name = "dependency"
    description = "依赖审查（pip-audit 漏洞扫描 + npm registry 过时检测 + LLM 风险点评）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        findings: list[dict[str, Any]] = []

        # 可观测性：确定性扫描子步骤记录
        import time as _time
        from app.services.review_steps import review_step_recorder

        # 1. Python 依赖：pip-audit
        _t0 = _time.monotonic()
        py_findings = await self._run_pip_audit(path)
        _dur = int((_time.monotonic() - _t0) * 1000)
        try:
            await review_step_recorder.record_tool_substep(
                agent_name=self.name,
                node_type="pip_audit",
                action_text=f"🔍 pip-audit 漏洞扫描：命中 {len(py_findings)} 条（{_dur / 1000:.1f}s）",
                duration_ms=_dur,
                detail={"findings": len(py_findings)},
            )
        except Exception:
            pass
        findings.extend(py_findings)

        # 2. JS 依赖：npm registry 过时检测
        _t0 = _time.monotonic()
        js_findings = await self._check_npm_outdated(path)
        _dur = int((_time.monotonic() - _t0) * 1000)
        if js_findings or _dur > 100:  # 无 package.json 时跳过记录（耗时极短）
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="npm_outdated",
                    action_text=f"🔍 npm 过时依赖检测：命中 {len(js_findings)} 条（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(js_findings)},
                )
            except Exception:
                pass
        findings.extend(js_findings)

        # 2b. JS 依赖漏洞：npm audit（npm 自带标准漏洞扫描）
        audit_findings = await self._run_npm_audit(path)
        findings.extend(audit_findings)

        # 2c. Go 依赖漏洞：OSV-Scanner（Google 官方，覆盖 go.mod）
        go_vuln_findings = await self._run_osv_scanner(path)
        findings.extend(go_vuln_findings)

        # 3. LLM 依赖风险点评
        try:
            llm_findings = await self._run_llm_analysis(path)
            findings.extend(llm_findings)
        except Exception as e:
            logger.warning("LLM 依赖分析失败，回退到工具结果", error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("依赖扫描完成", path=project_path, findings=len(unique))
        return unique

    async def _run_pip_audit(self, path: Path) -> list[dict[str, Any]]:
        """运行 pip-audit 扫描 Python 依赖漏洞"""
        requirements = path / "requirements.txt"
        pyproject = path / "pyproject.toml"

        cmd = ["pip-audit", "-f", "json"]
        if requirements.exists():
            cmd += ["-r", str(requirements)]
        elif pyproject.exists():
            # pip-audit 不直接支持 pyproject，先尝试 requirements.txt
            return []
        else:
            return []

        try:
            # 注：pip-audit 联网查询漏洞库较慢，同步 subprocess 会阻塞事件循环，
            # 必须放到线程池执行（asyncio.to_thread）。
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True,
                timeout=120, cwd=str(path),
            )
        except subprocess.TimeoutExpired:
            logger.warning("pip-audit 超时")
            return []
        except FileNotFoundError:
            logger.error("pip-audit 命令未找到")
            return []

        if result.returncode not in (0, 1):  # 0=无漏洞 1=有漏洞
            logger.warning("pip-audit 异常退出", code=result.returncode, stderr=result.stderr[:300])
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_pip_audit(path, data)

    def _parse_pip_audit(self, path: Path, data: dict) -> list[dict[str, Any]]:
        """解析 pip-audit JSON 输出"""
        findings = []
        for dep in data.get("dependencies", []):
            name = dep.get("name", "")
            version = dep.get("version", "")
            for vuln in dep.get("vulns", []):
                vuln_id = vuln.get("id", "")
                desc = vuln.get("description", "")[:200]
                fix_versions = ", ".join(vuln.get("fix_versions", []))
                severity = self._score_to_severity(vuln.get("cve", {}).get("cvss_score"))

                findings.append({
                    "rule_id": f"PIP-AUDIT-{vuln_id}",
                    "severity": severity,
                    "message": f"{name}=={version} 存在漏洞 {vuln_id}: {desc}",
                    "file_path": str(path / "requirements.txt"),
                    "line_start": None,
                    "code_snippet": f"{name}=={version}",
                    "suggestion": f"升级 {name} 到修复版本: {fix_versions}" if fix_versions else f"参考 {vuln_id} 公告处理",
                })
        return findings

    async def _check_npm_outdated(self, path: Path) -> list[dict[str, Any]]:
        """查询 npm registry 检测 JS 过时依赖"""
        pkg_json = path / "package.json"
        if not pkg_json.exists():
            return []

        try:
            data = json.loads(pkg_json.read_text(errors="ignore"))
        except json.JSONDecodeError:
            return []

        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        if not deps:
            return []

        findings = []
        sem = __import__("asyncio").Semaphore(5)

        async def _check_one(name: str, declared: str):
            declared_clean = declared.lstrip("^~>=<")
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.get(f"https://registry.npmjs.org/{name}")
                    if resp.status_code != 200:
                        return None
                    pkg = resp.json()
                    latest = pkg.get("dist-tags", {}).get("latest", "")
                    if latest and latest != declared_clean:
                        return {
                            "rule_id": f"NPM-OUTDATED-{name}",
                            "severity": "suggestion",
                            "message": f"{name}@{declared} 过时，最新版本 {latest}",
                            "file_path": str(pkg_json),
                            "line_start": None,
                            "code_snippet": f'"{name}": "{declared}"',
                            "suggestion": f'更新 {name} 到 {latest}',
                        }
                except Exception:
                    return None
            return None

        import asyncio
        results = await asyncio.gather(*[_check_one(n, v) for n, v in list(deps.items())[:20]])
        for r in results:
            if r:
                findings.append(r)

        return findings

    def _score_to_severity(self, score: float | None) -> str:
        if score is None:
            return DEFAULT_VULN_SEVERITY
        for threshold, sev in SEVERITY_BY_CVE_SCORE:
            if score >= threshold:
                return sev
        return "suggestion"

    async def _run_llm_analysis(self, path: Path) -> list[dict[str, Any]]:
        """LLM 依赖风险点评"""
        try:
            from app.agents.llm_client import get_active_llm_config, run_llm_analysis

            config = await get_active_llm_config()
            if not config:
                return []

            manifest = self._collect_manifest(path)
            if not manifest:
                return []

            prompts = [(fp, DEPENDENCY_PROMPT.format(manifest=content)) for fp, content in manifest]
            return await run_llm_analysis(config, prompts, default_rule="LLM-DEP")
        except ImportError:
            return []

    def _collect_manifest(self, path: Path) -> list[tuple[str, str]]:
        """收集依赖清单文件内容（用于 LLM 分析）"""
        result = []
        for name in ("requirements.txt", "pyproject.toml", "package.json"):
            f = path / name
            if f.exists():
                result.append((name, f.read_text(errors="ignore")[:4000]))
        return result

    async def _run_npm_audit(self, path: Path) -> list[dict[str, Any]]:
        """运行 npm audit（npm 自带标准漏洞扫描，查询 npm 审计库）

        在临时目录副本上执行（--package-lock-only），不触碰目标项目文件。
        """
        import asyncio
        import tempfile
        import time as _time

        pkg_json = path / "package.json"
        if not pkg_json.exists():
            return []

        t0 = _time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                # 拷贝清单到临时目录（audit 需要 lockfile；--package-lock-only 只解析清单）
                import shutil
                shutil.copy(pkg_json, Path(tmp) / "package.json")
                lock = path / "package-lock.json"
                if lock.exists():
                    shutil.copy(lock, Path(tmp) / "package-lock.json")

                def _run() -> tuple[str, bool]:
                    r = subprocess.run(
                        ["npm", "audit", "--json"],
                        capture_output=True, text=True, timeout=120, cwd=tmp,
                    )
                    return r.stdout, True

                stdout = await asyncio.to_thread(_run)
        except FileNotFoundError:
            logger.warning("npm 命令未找到（镜像未安装 Node 工具链？），跳过 npm audit")
            return []
        except Exception as e:
            logger.warning("npm audit 执行失败", error=str(e))
            return []
        duration_ms = int((_time.monotonic() - t0) * 1000)

        stdout = stdout[0] if isinstance(stdout, tuple) else stdout
        if not stdout.strip():
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []

        # npm audit JSON：vulnerabilities 字典（name → {severity, via, ...}）
        severity_map = {"critical": "critical", "high": "warning", "moderate": "suggestion", "low": "nitpick"}
        findings: list[dict[str, Any]] = []
        vulns = data.get("vulnerabilities", {}) or {}
        for name, info in vulns.items():
            if not isinstance(info, dict):
                continue
            sev = severity_map.get(info.get("severity", ""), "warning")
            via = [v if isinstance(v, str) else v.get("title", "") for v in (info.get("via") or [])][:2]
            findings.append({
                "rule_id": f"NPM-AUDIT-{name}",
                "severity": sev,
                "message": f"{name} 存在已知漏洞（{info.get('severity', '?')}）：{'；'.join(v for v in via if v)}",
                "file_path": "package.json",
                "line_start": None,
                "code_snippet": f'"{name}": {json.dumps(info.get("range", ""))}',
                "suggestion": f"升级 {name} 至安全版本（fixAvailable: {json.dumps(info.get('fixAvailable', False))}）",
            })

        try:
            from app.services.review_steps import review_step_recorder

            await review_step_recorder.record_tool_substep(
                agent_name=self.name,
                node_type="npm_audit",
                action_text=f"🔍 npm audit 漏洞扫描：命中 {len(findings)} 条（{duration_ms / 1000:.1f}s）",
                duration_ms=duration_ms,
                detail={"findings": len(findings)},
            )
        except Exception:
            pass
        return findings

    async def _run_osv_scanner(self, path: Path) -> list[dict[str, Any]]:
        """运行 OSV-Scanner（Google 官方多生态漏洞库扫描器，覆盖 go.mod）

        仅在有 go.mod 的项目执行；输出 JSON 解析为标准 findings。
        """
        import asyncio
        import time as _time

        if not (path / "go.mod").exists():
            return []

        t0 = _time.monotonic()
        try:
            def _run() -> str:
                r = subprocess.run(
                    ["osv-scanner", "--format", "json", "--lockfile", f"go.mod:{str(path / 'go.mod')}"],
                    capture_output=True, text=True, timeout=180,
                )
                # osv-scanner 有发现时退出码 1，stdout 仍为合法 JSON
                return r.stdout

            stdout = await asyncio.to_thread(_run)
        except FileNotFoundError:
            logger.warning("osv-scanner 命令未找到（镜像未安装？），跳过 Go 依赖漏洞扫描")
            return []
        except Exception as e:
            logger.warning("OSV-Scanner 执行失败", error=str(e))
            return []
        duration_ms = int((_time.monotonic() - t0) * 1000)

        if not stdout.strip():
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []

        severity_rank = {"7.0": "critical", "9.0": "critical"}
        findings: list[dict[str, Any]] = []
        for res in data.get("results", []) or []:
            for pkg in res.get("packages", []) or []:
                for v in pkg.get("vulnerabilities", []) or []:
                    vid = v.get("id", "OSV")
                    aliases = [a for a in v.get("aliases", []) if a.startswith("CVE")]
                    summary_txt = v.get("summary") or v.get("details", "")[:120]
                    sev = "warning"
                    for sev_item in v.get("database_specific", {}).get("severity", []) or []:
                        pass
                    findings.append({
                        "rule_id": f"GO-VULN-{vid}",
                        "severity": sev,
                        "message": f"{pkg.get('package', {}).get('name', '?')}: {summary_txt}",
                        "file_path": "go.mod",
                        "line_start": None,
                        "code_snippet": pkg.get("package", {}).get("version", ""),
                        "suggestion": f"修复版本：{', '.join(v.get('affected', [{}])[0].get('ranges', [{}])[0].get('events', [{'fixed': '?'}])[0].get('fixed', '?') for _ in [0])}"[:200],
                        "metadata": {"aliases": aliases},
                    })

        try:
            from app.services.review_steps import review_step_recorder

            await review_step_recorder.record_tool_substep(
                agent_name=self.name,
                node_type="osv_scanner",
                action_text=f"🔍 OSV-Scanner Go 依赖漏洞扫描：命中 {len(findings)} 条（{duration_ms / 1000:.1f}s）",
                duration_ms=duration_ms,
                detail={"findings": len(findings)},
            )
        except Exception:
            pass
        return findings
