/**
 * 知识卡片 — 按步骤类型解释"为什么会这样"（学习层）
 *
 * 每张卡片回答：这一步是谁决定的？框架机制还是项目代码？涉及什么知识点？
 * refs 指向项目源码位置（相对 backend/ 或 frontend/），供对照学习。
 */

export interface SourceRef {
  file: string;
  line?: number;
  desc: string;
}

export interface KnowledgeCard {
  text: string;
  refs?: SourceRef[];
}

export const KNOWLEDGE_CARDS: Record<string, KnowledgeCard> = {
  parse_project: {
    text: '外层 Flow 是确定性编排：@start 装饰器标记起点，@listen(parse_project) 表示"解析完成后执行"。这里只做路径校验、文件清点和 LLM 配置预检，不做任何审查。',
    refs: [
      { file: 'app/flows/review_flow.py', desc: 'parse_project 节点' },
      { file: 'app/agents/base.py', desc: 'Agent 基类定义' },
    ],
  },
  skip_agent: {
    text: 'review_type 过滤是外层 Flow 的路由决策：类型不匹配的 Agent 直接跳过，省掉无效的模型调用。这是纯项目代码逻辑（_resolve_agents），与框架无关。',
    refs: [{ file: 'app/flows/review_flow.py', desc: '_resolve_agents / _run_crew_node' }],
  },
  llm_call: {
    text: '这是 ReAct 模式的"思考"环节：CrewAI 把 role/goal/backstory + 任务描述拼成提示词发给模型，由模型自主决定下一步动作（调工具还是直接回答）。这个决策是模型做的，不是代码写死的——点击「查看全文」可以看到模型实际收到的完整提示词。',
    refs: [
      { file: 'app/services/crew_event_bridge.py', desc: '事件桥接器捕获此调用' },
      { file: 'app/flows/crew_factory.py', desc: 'AGENT_PROFILES 角色定义' },
    ],
  },
  tool_call: {
    text: '工具由项目代码封装（_make_scan_tool）：通过闭包绑定项目路径，Agent 无需传参即可调用。是否调用工具由模型决定；工具内部做什么由代码决定——这正是"框架自主性 + 确定性工具"的分工。',
    refs: [{ file: 'app/flows/crew_factory.py', desc: '_make_scan_tool 工具封装' }],
  },
  semgrep_ruleset: {
    text: 'Semgrep 是基于规则的静态扫描：快、确定、离线，但只能匹配已知模式。多个规则集并行执行（asyncio.gather），复杂语义漏洞交给后续 LLM 补充——规则引擎与 LLM 互补。',
    refs: [
      { file: 'app/agents/security_agent.py', desc: 'SEMGREP_RULESETS 规则集清单' },
      { file: 'app/data/semgrep-rules/', desc: '本地化规则库' },
    ],
  },
  ruff_check: {
    text: 'Ruff 是 Python 生态最快的 linter：纯规则匹配（命名/复杂度/import 等），结果确定可复现。RULE_SEVERITY 映射表把 Ruff 规则码翻译为审查严重度。',
    refs: [{ file: 'app/agents/code_style_agent.py', desc: '_run_ruff / RULE_SEVERITY' }],
  },
  pip_audit: {
    text: 'pip-audit 查询 PyPI/OSV 漏洞库识别已知 CVE（需联网）。这是供应链安全的标准做法：漏洞发现靠数据库比对，不靠模型猜。',
    refs: [{ file: 'app/agents/dependency_agent.py', desc: '_run_pip_audit' }],
  },
  npm_outdated: {
    text: '对比 package.json 声明版本与 npm registry 最新版本，识别过时依赖。纯 API 查询 + 版本比较逻辑。',
    refs: [{ file: 'app/agents/dependency_agent.py', desc: '_check_npm_outdated' }],
  },
  ast_coverage: {
    text: '用 Python AST 解析源码提取全部函数定义，再扫描测试文件对函数名的引用，差集即"未测试函数"。AST 分析是确定性白盒手段，比让模型数函数可靠得多。',
    refs: [{ file: 'app/agents/test_coverage_agent.py', desc: '_analyze_coverage' }],
  },
  ast_performance: {
    text: '遍历 AST 找性能反模式：循环内 ORM 调用（N+1）、async 函数里的同步阻塞调用等。模式清单硬编码在 ORM_CALL_METHODS / BLOCKING_CALLS 中。',
    refs: [{ file: 'app/agents/performance_agent.py', desc: '_run_ast_analysis / ORM_CALL_METHODS' }],
  },
  git_commit_check: {
    text: '读取 git log 检查提交信息是否符合 Conventional Commits 规范（feat/fix/docs...）。纯 git 命令 + 正则判断。',
    refs: [{ file: 'app/agents/git_review_agent.py', desc: '_check_commit_conventions' }],
  },
  git_branch_check: {
    text: '分析分支命名与生命周期策略。纯 git 命令输出解析。',
    refs: [{ file: 'app/agents/git_review_agent.py', desc: '_check_branch_strategy' }],
  },
  llm_file_analysis: {
    text: '逐文件语义分析弥补规则引擎漏报：每个文件独立调用一次模型（并发 3），提示词中注入了代码库上下文增强审查质量。注意：这些调用走项目自己的 HTTP 客户端（不经 CrewAI），所以由 llm_client 直接埋点记录。',
    refs: [
      { file: 'app/agents/llm_client.py', desc: 'run_llm_analysis 并发调度' },
      { file: 'app/agents/context_enhancer.py', desc: '上下文增强' },
    ],
  },
};

/** 内层 Crew 主步骤的卡片 */
export const INNER_CREW_CARD: KnowledgeCard = {
  text: '内层 Crew = 单 Agent 独立 Crew（Process.sequential）。执行顺序由 CrewAI 的 ReAct 循环定义：模型先读任务 → 决定调工具 → 工具返回结果直接作为最终答案（result_as_answer=True，省一次收尾调用）。6 个这样的 Crew 由外层 Flow 的多 @listen 机制并行驱动。',
  refs: [
    { file: 'app/flows/review_flow.py', desc: '_run_crew_node' },
    { file: 'app/flows/crew_factory.py', desc: 'build_review_crew' },
  ],
};

export const AGGREGATE_CARD: KnowledgeCard = {
  text: '去重键 = (rule_id, file_path, line_start)，纯项目代码逻辑，与框架无关。多个 Agent 报同一问题时只保留一条。',
  refs: [{ file: 'app/flows/review_flow.py', desc: 'aggregate 节点' }],
};

export const GENERATE_REPORT_CARD: KnowledgeCard = {
  text: 'Flow 只产出摘要状态；完整报告由 API 层 ReportGenerator 按需生成（Markdown/HTML），职责分离。',
  refs: [{ file: 'app/services/report_generator.py', desc: 'ReportGenerator' }],
};
