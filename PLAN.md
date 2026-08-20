# 多Agent协作代码审查系统 - 开发计划

## 1. 项目概述

构建一个多Agent协作的代码审查系统，支持多种触发方式，重点优化本地开发和演示体验。系统将模拟真实Code Review流程，通过多个专业Agent并行审查代码，最后生成结构化审查报告。

## 2. 设计原则

### 2.1 触发机制灵活性
- **多触发模式支持**：GitHub Webhook、本地目录选择、文件上传、代码粘贴、CLI命令行
- **渐进式复杂度**：从简单手动触发开始，逐步支持自动化触发
- **本地友好**：优先保证本地开发和演示的便利性

### 2.2 架构可扩展性
- **模块化设计**：触发器、Agent、分析引擎、报告生成器均可独立扩展
- **插件化Agent**：方便添加新的审查Agent类型
- **配置驱动**：通过配置文件控制Agent行为和触发规则

### 2.3 学习演示优先
- **快速启动**：最小配置即可运行
- **可视化流程**：清晰的进度展示和结果展示
- **示例丰富**：提供多种语言的示例代码和配置

## 3. 系统架构（修订版）

```text
                    ┌─────────────────────────────────┐
                    │         触发层 (Trigger Layer)    │
                    │                                 │
                    │  ┌─────────┐  ┌─────────────┐  │
                    │  │ GitHub  │  │ 本地目录选择 │  │
                    │  │ Webhook │  │   触发器     │  │
                    │  └────┬────┘  └──────┬──────┘  │
                    │       │              │         │
                    │  ┌────┴────┐  ┌──────┴──────┐  │
                    │  │ 文件上传 │  │  代码粘贴   │  │
                    │  │  触发器  │  │   触发器    │  │
                    │  └────┬────┘  └──────┬──────┘  │
                    │       │              │         │
                    │  ┌────┴──────────────┴────┐    │
                    │  │      CLI 命令行        │    │
                    │  └───────────┬────────────┘    │
                    └─────────────┼─────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────────┐
                    │      主Agent (Orchestrator)      │
                    │                                 │
                    │  • 任务分解与调度                │
                    │  • 上下文隔离                    │
                    │  • 结果整合与排序                │
                    └─────────────┬─────────────────┘
                                  │
                    ┌─────────────┼─────────────────┐
                    │             │                 │
                    ▼             ▼                 ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │  安全审查    │ │  性能分析    │ │  代码规范    │
        │    Agent    │ │    Agent    │ │    Agent    │
        └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
               │                │                 │
               └────────────────┼─────────────────┘
                                │
                                ▼
                    ┌─────────────────────────────────┐
                    │       结果输出层 (Output)        │
                    │                                 │
                    │  • Markdown报告生成              │
                    │  • PR评论回写 (GitHub)          │
                    │  • Web界面展示                   │
                    │  • 可观测性 (Langfuse/structlog)│
                    └─────────────────────────────────┘
```

## 4. 触发机制设计

### 4.1 触发器接口设计

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ReviewTask:
    """审查任务数据结构"""
    task_id: str
    source: str  # 触发来源：github, local_dir, file_upload, code_paste, cli
    files: list  # 待审查文件列表
    metadata: Dict[str, Any]  # 元数据：仓库信息、分支、提交等
    created_at: datetime
    priority: int = 0  # 优先级，0为默认

class Trigger(ABC):
    """触发器基类"""
    
    @abstractmethod
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """验证输入数据的有效性"""
        pass
    
    @abstractmethod
    async def create_review_task(self, input_data: Dict[str, Any]) -> ReviewTask:
        """创建审查任务"""
        pass
    
    @abstractmethod
    async def get_supported_languages(self) -> list:
        """获取支持的编程语言列表"""
        pass
```

### 4.2 具体触发器实现

#### 4.2.1 GitHub Webhook 触发器
```python
class GitHubWebhookTrigger(Trigger):
    """GitHub Webhook触发器"""
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        # 验证Webhook签名
        # 验证事件类型（pull_request）
        # 验证PR状态（opened, synchronize）
        pass
    
    async def create_review_task(self, input_data: Dict[str, Any]) -> ReviewTask:
        # 解析PR信息
        # 获取变更文件列表
        # 创建审查任务
        pass
```

#### 4.2.2 本地目录触发器
```python
class LocalDirectoryTrigger(Trigger):
    """本地目录触发器"""
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        # 验证目录路径是否存在
        # 验证是否为Git仓库
        # 验证是否有读取权限
        pass
    
    async def create_review_task(self, input_data: Dict[str, Any]) -> ReviewTask:
        # 扫描目录中的代码文件
        # 分析Git状态（已修改、新增文件等）
        # 创建审查任务
        pass
```

#### 4.2.3 文件上传触发器
```python
class FileUploadTrigger(Trigger):
    """文件上传触发器"""
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        # 验证文件类型（支持压缩包、单个文件）
        # 验证文件大小限制
        # 验证文件内容编码
        pass
    
    async def create_review_task(self, input_data: Dict[str, Any]) -> ReviewTask:
        # 解压文件（如果是压缩包）
        # 识别文件类型
        # 创建审查任务
        pass
```

#### 4.2.4 代码粘贴触发器
```python
class CodePasteTrigger(Trigger):
    """代码粘贴触发器"""
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        # 验证代码内容不为空
        # 验证代码长度限制
        # 尝试识别编程语言
        pass
    
    async def create_review_task(self, input_data: Dict[str, Any]) -> ReviewTask:
        # 创建临时文件保存代码
        # 识别编程语言
        # 创建审查任务
        pass
```

#### 4.2.5 CLI命令行触发器
```python
class CLITrigger(Trigger):
    """CLI命令行触发器"""
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        # 验证命令行参数
        # 验证文件路径
        pass
    
    async def create_review_task(self, input_data: Dict[str, Any]) -> ReviewTask:
        # 解析命令行参数
        # 处理文件路径
        # 创建审查任务
        pass
```

### 4.3 触发器注册与管理

```python
class TriggerManager:
    """触发器管理器"""
    
    def __init__(self):
        self.triggers: Dict[str, Trigger] = {}
    
    def register_trigger(self, name: str, trigger: Trigger):
        """注册触发器"""
        self.triggers[name] = trigger
    
    async def trigger_review(self, trigger_name: str, input_data: Dict[str, Any]) -> ReviewTask:
        """触发审查"""
        if trigger_name not in self.triggers:
            raise ValueError(f"Unknown trigger: {trigger_name}")
        
        trigger = self.triggers[trigger_name]
        
        # 验证输入
        if not await trigger.validate_input(input_data):
            raise ValueError("Invalid input data")
        
        # 创建审查任务
        task = await trigger.create_review_task(input_data)
        
        # 启动审查流程
        await self.start_review_pipeline(task)
        
        return task
```

## 5. 核心模块实现计划

### 5.1 主Agent（Orchestrator）

#### 5.1.1 任务分解器
```python
class TaskDecomposer:
    """任务分解器"""
    
    async def analyze_files(self, files: List[File]) -> AnalysisResult:
        """分析文件，确定需要哪些Agent参与"""
        # 1. 文件类型分析（代码、配置、文档等）
        # 2. 编程语言识别
        # 3. 变更规模评估
        # 4. Agent需求决策
        pass
    
    async def create_subtasks(self, analysis: AnalysisResult) -> List[SubTask]:
        """创建子任务"""
        # 1. 按文件分组
        # 2. 上下文隔离（每个子任务只包含相关文件）
        # 3. 优先级排序
        pass
```

#### 5.1.2 Agent调度器
```python
class AgentDispatcher:
    """Agent调度器"""
    
    async def dispatch_tasks(self, subtasks: List[SubTask]) -> Dict[str, List[SubTask]]:
        """分发任务给对应的Agent"""
        # 1. 根据Agent能力匹配任务
        # 2. 负载均衡
        # 3. 并行执行
        pass
```

### 5.2 专业Agent实现

#### 5.2.1 安全审查Agent
```python
class SecurityReviewAgent(BaseAgent):
    """安全审查Agent"""
    
    def __init__(self):
        self.tools = [
            SemgrepTool(),
            LLMTool(model="gpt-4o")
        ]
    
    async def review(self, file: File) -> List[Finding]:
        """执行安全审查"""
        findings = []
        
        # 1. Semgrep静态扫描
        semgrep_findings = await self.tools[0].scan(file)
        findings.extend(semgrep_findings)
        
        # 2. LLM语义分析（补充Semgrep漏报）
        llm_findings = await self.tools[1].analyze(file, 
            prompt="分析以下代码的安全漏洞，特别关注SQL注入、XSS、硬编码密钥等")
        findings.extend(llm_findings)
        
        return findings
```

#### 5.2.2 性能分析Agent
```python
class PerformanceReviewAgent(BaseAgent):
    """性能分析Agent"""
    
    async def review(self, file: File) -> List[Finding]:
        """执行性能分析"""
        # 1. AST分析识别数据库调用模式
        # 2. LLM推理判断性能反模式
        # 3. 识别N+1查询、全表扫描等问题
        pass
```

#### 5.2.3 代码规范Agent
```python
class CodeStyleReviewAgent(BaseAgent):
    """代码规范Agent"""
    
    async def review(self, file: File) -> List[Finding]:
        """执行代码规范检查"""
        # 1. Ruff/Pylint静态检查
        # 2. LLM判断命名规范、函数复杂度
        # 3. 重复代码检测
        pass
```

#### 5.2.4 测试覆盖Agent
```python
class TestCoverageReviewAgent(BaseAgent):
    """测试覆盖Agent"""
    
    async def review(self, file: File) -> List[Finding]:
        """执行测试覆盖分析"""
        # 1. coverage.py分析
        # 2. AST分析识别未测试函数
        # 3. LLM推理生成测试建议
        pass
```

### 5.3 结果整合与报告生成

#### 5.3.1 结果整合器
```python
class ResultAggregator:
    """结果整合器"""
    
    async def aggregate(self, results: Dict[str, List[Finding]]) -> AggregatedResults:
        """整合所有Agent的审查结果"""
        # 1. 去重（相同问题不同Agent可能重复报告）
        # 2. 合并（相关问题合并为一个问题）
        # 3. 排序（Critical > Warning > Suggestion > Nitpick）
        # 4. 优先级评估
        pass
```

#### 5.3.2 报告生成器
```python
class ReportGenerator:
    """报告生成器"""
    
    async def generate_markdown_report(self, results: AggregatedResults) -> str:
        """生成Markdown格式的审查报告"""
        # 1. 审查摘要
        # 2. 问题统计
        # 3. 详细问题列表
        # 4. 修改建议
        # 5. 代码片段引用
        pass
    
    async def generate_pr_comment(self, results: AggregatedResults, pr_info: PRInfo) -> str:
        """生成PR评论格式的报告"""
        # 适合直接发布到GitHub PR评论
        pass
```

## 6. 开发阶段划分

### 阶段1：MVP（第1周）
**目标**：实现基础手动触发和单Agent审查

#### 6.1.1 核心功能
- [ ] 触发机制：本地目录选择触发器
- [ ] 核心Agent：单Agent LLM直接分析
- [ ] 基础Web界面：FastAPI后端 + 简单前端
- [ ] 报告生成：Markdown格式报告

#### 6.1.2 技术实现
1. **后端API**
   - FastAPI应用框架
   - 文件上传接口
   - 目录扫描接口
   - 审查任务管理

2. **前端界面**
   - 文件/目录选择组件
   - 审查进度展示
   - 报告展示页面

3. **基础Agent**
   - 单Agent使用GPT-4o分析代码
   - 基础提示词工程
   - 结构化输出解析

#### 6.1.3 交付物
- 可运行的Web应用
- 支持本地目录选择审查
- 基础Markdown报告生成
- 简单的用户界面

### 阶段2：V1.0 - 多Agent协作（第2周）
**目标**：实现多Agent并行审查和结果整合

#### 6.2.1 核心功能
- [ ] 多Agent架构：主Agent + 4个专业Agent
- [ ] 并行执行：异步任务并行处理
- [ ] 结果整合：去重、合并、排序
- [ ] 增强报告：更详细的报告格式

#### 6.2.2 技术实现
1. **Agent框架**
   - CrewAI角色定义与工具配置
   - Flows + Crews 双层架构（外层确定性编排 + 内层Agent自主协作）
   - Agent通信协议

2. **任务调度**
   - 任务分解器
   - Agent调度器
   - 并行执行器

3. **结果处理**
   - 结果整合器
   - 优先级排序
   - 冲突解决

#### 6.2.3 交付物
- 完整的多Agent系统
- 并行审查能力
- 结构化审查报告
- 性能基准测试

### 阶段3：V2.0 - 工具集成（第3周）
**目标**：集成静态分析工具和异步任务队列

#### 6.3.1 核心功能
- [ ] 静态分析工具：Semgrep、Ruff、Pylint
- [ ] 异步任务：Redis + Celery
- [ ] 增强Web界面：实时进度、历史记录
- [ ] 配置系统：Agent行为配置

#### 6.3.2 技术实现
1. **工具集成**
   - Semgrep安全扫描
   - Ruff代码规范检查
   - Pylint静态分析
   - coverage.py测试覆盖

2. **异步任务**
   - Redis消息队列
   - Celery任务调度
   - 任务状态管理

3. **配置系统**
   - YAML配置文件
   - Agent行为配置
   - 触发规则配置

#### 6.3.3 交付物
- 集成静态分析工具
- 异步任务处理能力
- 增强的用户界面
- 配置管理系统

### 阶段4：V3.0 - 高级功能（第4周）
**目标**：实现增量审查、历史学习和可观测性

#### 6.4.1 核心功能
- [ ] 增量审查：只审查变更代码
- [ ] 历史学习：学习团队规范偏好
- [ ] 可观测性：Langfuse推理链、structlog结构化日志
- [ ] 多语言支持：JavaScript、Go、Rust

#### 6.4.2 技术实现
1. **增量审查**
   - Git diff解析
   - 变更行识别
   - 上下文关联

2. **历史学习**
   - 审查反馈记录
   - 团队规范学习
   - 个性化建议

3. **可观测性**
   - Langfuse集成
   - 结构化日志（structlog）
   - 审查耗时/调用统计

4. **多语言支持**
   - 语言特定Agent
   - 语言工具链集成
   - 语言规范配置

#### 6.4.3 交付物
- 增量审查能力
- 历史学习功能
- 完整可观测性
- 多语言支持

## 7. 技术栈选择

### 7.1 后端技术
- **Web框架**：FastAPI（异步、高性能、自动文档）
- **任务队列**：Celery + Redis（异步任务处理）
- **数据库**：SQLite（本地开发）/ PostgreSQL（生产）
- **缓存**：Redis（任务状态、配置缓存）

### 7.2 前端技术
- **框架**：React + TypeScript（类型安全、组件化）
- **UI库**：Ant Design / Material-UI（成熟组件库）
- **状态管理**：Redux Toolkit / Zustand
- **构建工具**：Vite（快速开发体验）

### 7.3 AI/ML技术
- **多Agent框架**：CrewAI（Flows事件驱动编排 + Crews角色自主协作 双层架构）
- **LLM**：GPT-4o（主Agent）+ DeepSeek-chat（代码分析）
- **静态分析**：Semgrep、Ruff、Pylint
- **代码解析**：AST、tree-sitter

### 7.4 DevOps工具
- **容器化**：Docker + Docker Compose
- **监控**：Langfuse（推理链）+ structlog（结构化日志）
- **日志**：结构化日志（无需ELK）

## 8. 风险评估与应对

### 8.1 技术风险
| 风险 | 影响 | 应对策略 |
|------|------|----------|
| LLM API调用延迟 | 审查速度慢 | 1. 并行调用<br>2. 结果缓存<br>3. 本地模型备选 |
| 静态分析工具集成复杂 | 开发周期延长 | 1. 分阶段集成<br>2. 优先核心工具<br>3. 社区资源利用 |
| 多Agent协调困难 | 系统稳定性差 | 1. Flows + Crews 双层控制<br>2. 超时机制<br>3. 降级策略 |
| LLM结构化输出不稳定 | 审查结论质量差 | 1. Pydantic schema约束<br>2. 输出校验+自动重试<br>3. 解析兜底 |

### 8.2 业务风险
| 风险 | 影响 | 应对策略 |
|------|------|----------|
| 用户学习曲线陡峭 | 采用率低 | 1. 详细文档<br>2. 示例项目<br>3. 视频教程 |
| 本地演示效果不佳 | 学习体验差 | 1. 预置示例<br>2. 快速启动脚本<br>3. 可视化流程 |

### 8.3 资源风险
| 风险 | 影响 | 应对策略 |
|------|------|----------|
| API调用成本高 | 预算超支 | 1. 本地模型备选<br>2. 调用限制<br>3. 结果缓存 |
| 开发时间不足 | 功能缺失 | 1. 优先级排序<br>2. MVP先行<br>3. 迭代开发 |

## 9. 成功标准

### 9.1 功能性标准
- [ ] 支持至少3种触发方式（本地目录、文件上传、代码粘贴）
- [ ] 实现4个专业Agent：安全(P0)、规范(P0)、测试覆盖(P1)、性能(P2)
- [ ] 生成结构化Markdown审查报告
- [ ] 支持Python、JavaScript、Go语言审查

> **优先级说明**：安全/规范为必做（P0），测试覆盖为推荐（P1），性能分析为可选（P2，视进度）。架构审查/部署审查已摘出。完整分档见 `plans/技术架构设计.md` 8.0 节。

### 9.2 性能标准
- [ ] 单文件审查时间 < 30秒
- [ ] 10文件项目审查时间 < 2分钟
- [ ] 系统启动时间 < 10秒
- [ ] 内存占用 < 2GB

### 9.3 用户体验标准
- [ ] 5分钟内完成首次审查
- [ ] 清晰的错误提示和帮助文档
- [ ] 直观的进度展示和结果展示
- [ ] 响应式设计，支持移动端

### 9.4 学习价值标准
- [ ] 覆盖多Agent协作核心概念
- [ ] 演示任务分解与上下文隔离
- [ ] 展示并行执行与异步处理
- [ ] 体现工具集成与LLM应用

## 10. 后续扩展方向

### 10.1 短期扩展（1-2个月）
- GitHub/GitLab集成
- 自动修复简单问题
- 团队协作功能
- API接口开放

### 10.2 中期扩展（3-6个月）
- 企业级部署方案
- 私有化部署支持
- 高级分析功能
- 机器学习优化

### 10.3 长期扩展（6-12个月）
- 云服务版本
- IDE插件生态
- 代码质量监控
- 团队知识库

---

**计划制定时间**：2026年8月20日  
**计划版本**：v1.0  
**审核状态**：待审核