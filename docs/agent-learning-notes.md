# Agent 开发学习笔记

> 本文档记录在开发"多Agent协作代码审查系统"过程中的学习心得、框架对比、关键技术决策。
> 用于面试准备和技术分享，记录"为什么这样设计"而非"怎么实现"。

---

## 1. 框架对比：LangGraph vs CrewAI

> 背景：另一个项目已使用 LangGraph，本项目使用 CrewAI，刻意做框架对比。

### 1.1 心智模型差异

| 维度 | LangGraph | CrewAI |
|------|-----------|--------|
| **核心抽象** | 状态图（Graph + State）| 角色团队（Crew + Flow）|
| **编排方式** | 底层：手写节点和边，状态驱动 | 高层：YAML 配置 + 装饰器 |
| **调试体验** | 白盒（每步状态可见） | Flow 白盒 + Crew 黑盒 |
| **适合场景** | 复杂状态机、HITL、持久化 | 角色协作、快速原型、团队隐喻 |
| **学习曲线** | 陡峭（要理解图概念） | 平缓（角色/任务直觉） |
| **生产就绪** | 高（LangSmith 生态） | 中（需要自己包装） |

### 1.2 "主Agent聚合"场景对比

**LangGraph 写法**：
```python
# 状态图：节点是函数，边是状态转移
graph = StateGraph(ReviewState)
graph.add_node("analyze", analyze_pr)
graph.add_node("dispatch", dispatch_tasks)
graph.add_node("run_agents", run_sub_agents)
graph.add_node("aggregate", aggregate_results)
graph.add_node("report", generate_report)
graph.add_edge("analyze", "dispatch")
graph.add_edge("dispatch", "run_agents")
graph.add_edge("run_agents", "aggregate")
graph.add_edge("aggregate", "report")
graph.add_edge("report", END)
```

**CrewAI Flows + Crews 写法**：
```python
# Flow：装饰器驱动，状态是 Pydantic model
class ReviewFlow(Flow[ReviewState]):
    @start()
    def parse_pr(self): ...
    @listen(parse_pr)
    def analyze_files(self): ...
    @listen(analyze_files)
    def run_reviews(self):
        crew = Crew(agents=[...], tasks=[...])
        result = crew.kickoff()
```

**面试话术**：
> "LangGraph 是从下往上搭（手写图），CrewAI 是从上往下用（角色隐喻）。同一个'多Agent聚合'场景，LangGraph 更灵活但代码量大，CrewAI 更快但定制成本高。我在两个项目中分别用了两个框架，对它们的适用边界有实际体会。"

### 1.3 本项目的选型理由

1. **场景匹配**：代码审查 = 多角色并行 + 结果聚合，天然适合 CrewAI 的角色隐喻
2. **学习互补**：已用过 LangGraph（底层），再学 CrewAI（高层）能覆盖两种范式
3. **开发效率**：CrewAI 的 YAML 配置 + 脚手架，MVP 阶段更快

---

## 2. CrewAI 关键概念（面试考点）

### 2.1 Flows vs Crews

- **Flows**：事件驱动的工作流，用 `@start` / `@listen` / `@router` 装饰器编排，状态用 Pydantic model 管理，适合确定性流程
- **Crews**：角色自主协作，Agent 自己决定如何完成任务，适合需要灵活性的场景
- **结合**：外层 Flow 控制流程，内层 Crew 做自主审查

### 2.2 Agent 设计模式

- **角色（Role）**：Agent 的身份和专长，如"安全审查专家"
- **目标（Goal）**：Agent 要达成什么，如"检测所有安全漏洞"
- **工具（Tools）**：Agent 可以调用的能力，如 Semgrep、Ruff
- **上下文隔离**：每个 Agent 独立上下文，避免互相污染

### 2.3 结构化输出

- CrewAI 的 `output_pydantic` 参数可以约束输出格式
- 但 LLM 结构化输出本身不稳定（格式漂移、行号报错）
- 本项目策略：核心 schema 用 Pydantic 自己写死，CrewAI 只做第一层约束

---

## 3. 关键技术决策记录

### 3.1 为什么摘出架构审查？

- **不可验证**：架构审查的结论是观点而非事实，无法自动验证
- **与增量审查错配**：架构是全局属性，PR diff 是局部变更
- **学习价值低**：AST 解析 + 循环依赖检测是确定性计算，不涉及 Agent 协作

### 3.2 为什么用 Flows + Crews 而不是纯 Crew？

- 纯 Crew 是黑盒（框架隐式决定执行顺序），调试困难
- Flow 是白盒（每一步都是可调试的 Python），状态可追踪
- 代码审查场景：外层要确定性（任务分解/聚合），内层要自主性（各 Agent 独立审查）

### 3.3 为什么简化监控栈？

- 本项目是学习项目，不是生产系统
- Prometheus/Grafana/Loki 全套监控对学习 Agent 开发没有帮助
- Langfuse（LLM 推理链追踪）+ structlog（结构化日志）足够

---

## 4. 面试准备要点

### 4.1 必问问题及回答

**Q: 为什么用多Agent而不是单Agent？**
> 单Agent处理所有审查会导致上下文膨胀、角色混淆、无法并行。多Agent可以：1）上下文隔离避免污染；2）专业分工提高准确性；3）并行执行提高效率。

**Q: Agent之间怎么通信？**
> 本项目是"并行审查 + 结果聚合"模式，Agent之间不直接通信。每个Agent独立完成审查，结果由外层Flow聚合。这是最简单的协作模式，避免了复杂的通信协议。

**Q: 怎么保证审查结果的准确性？**
> 三层保障：1）确定性工具（Semgrep/Ruff）做第一道检查；2）LLM做语义补充；3）Pydantic schema强制校验输出格式。核心是"确定性工具兜底 + LLM补充"，不完全依赖LLM。

**Q: CrewAI和LangGraph怎么选？**
> 看场景：复杂状态机、HITL、持久化选LangGraph；角色协作、快速原型、团队隐喻选CrewAI。我在两个项目中分别用了两个框架，能讲清它们的适用边界。

### 4.2 项目亮点（面试时强调）

1. **双框架经验**：LangGraph（底层）+ CrewAI（高层），覆盖两种范式
2. **工程思维**：确定性工具兜底 + LLM补充，不是纯靠LLM
3. **可验证维度**：只做能验证的审查（安全/规范/依赖/测试），不做主观判断
4. **渐进式设计**：从单Agent到多Agent，从同步到异步，从简单到复杂

---

## 5. 学习资源

- [CrewAI 官方文档](https://docs.crewai.com/)
- [DeepLearning.AI: Multi AI Agent Systems with CrewAI](https://www.deeplearning.ai/short-courses/multi-ai-agent-systems-with-crewai/)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Pydantic AI 官方文档](https://ai.pydantic.dev/)

---

*最后更新：2026-08-20*
