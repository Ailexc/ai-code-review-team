import { useState, useEffect } from 'react';
import { Card, Button, Upload, Input, message, List, Space, Typography, Row, Col, Tag, Collapse, Segmented, Divider } from 'antd';
import {
  UploadOutlined, FolderOpenOutlined, FileTextOutlined, PlayCircleOutlined,
  SafetyOutlined, CodeOutlined, ExperimentOutlined, BugOutlined,
  ThunderboltOutlined, StarFilled, BranchesOutlined, BookOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { triggerApi, TriggerResult } from '@/api/triggerApi';
import { projectApi, Project } from '@/api/projectApi';
import ReviewProgress from '@/components/Review/ReviewProgress';

// 审查能力定义
const CAPABILITIES = [
  {
    key: 'security', title: '安全审查', icon: <SafetyOutlined />,
    color: '#ff4d4f', gradient: 'linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%)',
    tools: ['Semgrep', 'LLM'],
    description: '扫描代码中的安全漏洞，覆盖 OWASP Top 10 常见风险',
    dimensions: ['SQL 注入', 'XSS', '命令注入', 'eval 使用', '硬编码密码', '不安全反序列化'],
    avgTime: '60-90s',
    output: 'severity 分级的漏洞列表 + 修复建议',
    principle: '使用 Semgrep 加载 200+ 条安全规则（p/python、p/flask、p/django 等）进行静态扫描，再用 LLM 对扫描结果做语义分析，补充静态工具难以发现的逻辑漏洞。',
    docCategory: 'agents', docId: 'security-agent',
  },
  {
    key: 'code_style', title: '规范审查', icon: <CodeOutlined />,
    color: '#faad14', gradient: 'linear-gradient(135deg, #faad14 0%, #ffc53d 100%)',
    tools: ['Ruff', 'LLM'],
    description: '检查代码规范和可维护性，自动识别可修复的问题',
    dimensions: ['命名规范', '函数复杂度', 'import 排序', '类型注解', '重复代码'],
    avgTime: '120-140s',
    output: '规范问题列表 + 自动修复标记',
    principle: '使用 Ruff 静态检查（pyflakes/pycodestyle/复杂度等规则），识别可自动修复项（is_auto_fixable），再用 LLM 对代码做语义点评（命名、复杂度、重复代码）。',
    docCategory: 'agents', docId: 'code-style-agent',
  },
  {
    key: 'dependency', title: '依赖审查', icon: <ExperimentOutlined />,
    color: '#1677ff', gradient: 'linear-gradient(135deg, #1677ff 0%, #4096ff 100%)',
    tools: ['pip-audit', 'npm registry', 'LLM'],
    description: '检测项目依赖中的已知漏洞和过时版本',
    dimensions: ['CVE 漏洞', '过时依赖', '版本风险评估', '依赖锁文件分析'],
    avgTime: '90-120s',
    output: '漏洞列表 + 过时版本列表 + 升级建议',
    principle: '解析 requirements.txt / package.json 等清单文件，用 pip-audit 查询 CVE 漏洞库，用 npm registry 检测过时版本，再用 LLM 评估风险等级和升级建议。',
    docCategory: 'agents', docId: 'dependency-agent',
  },
  {
    key: 'test_coverage', title: '测试覆盖', icon: <BugOutlined />,
    color: '#52c41a', gradient: 'linear-gradient(135deg, #52c41a 0%, #73d13d 100%)',
    tools: ['AST 分析', 'LLM'],
    description: '识别代码中未被测试覆盖的函数和缺失的测试文件',
    dimensions: ['未测试函数', '缺失测试目录', '私有函数过滤', '测试建议生成'],
    avgTime: '60-80s',
    output: '未覆盖函数列表 + 建议的测试用例',
    principle: '用 Python AST 解析源码提取所有函数，与 tests/ 目录中的引用做对比，识别未被测试覆盖的函数（跳过私有函数），再用 LLM 生成测试建议。',
    docCategory: 'agents', docId: 'test-coverage-agent',
  },
  {
    key: 'performance', title: '性能分析', icon: <ThunderboltOutlined />,
    color: '#722ed1', gradient: 'linear-gradient(135deg, #722ed1 0%, #9254de 100%)',
    tools: ['AST 分析', 'LLM'],
    description: '检测 Python 代码中的性能反模式和瓶颈',
    dimensions: ['N+1 查询', '同步阻塞', '字符串拼接', '无限制查询', '内存问题'],
    avgTime: '30-60s',
    output: '性能问题列表 + 优化建议',
    principle: '用 AST 遍历代码检测性能反模式：循环内 ORM 调用（N+1）、async 内同步阻塞、循环内字符串拼接、无 limit 查询。再用 LLM 补充复杂性能场景分析。',
    docCategory: 'agents', docId: 'performance-agent',
  },
  {
    key: 'git_review', title: 'Git 审查', icon: <BranchesOutlined />,
    color: '#13c2c2', gradient: 'linear-gradient(135deg, #13c2c2 0%, #36cfc9 100%)',
    tools: ['GitPython', 'LLM'],
    description: '分析 Git 仓库的提交规范和分支健康度',
    dimensions: ['提交规范', '分支策略', '文件热点', '提交频率', '消息质量'],
    avgTime: '40-60s',
    output: '规范评分 + 改进建议',
    principle: '用 Git 命令分析最近 50 条提交是否符合 Conventional Commits 规范，检查分支命名和告期分支，统计文件热点和提交频率，再用 LLM 点评提交消息质量。',
    docCategory: 'agents', docId: 'git-review-agent',
  },
  {
    key: 'full', title: '综合审查', icon: <StarFilled />,
    color: '#f5222d', gradient: 'linear-gradient(135deg, #f5222d 0%, #ff4d4f 50%, #faad14 100%)',
    tools: ['全部 6 个 Agent'],
    description: '并行运行全部 Agent，一次性发现所有维度的问题',
    dimensions: ['安全 + 规范 + 依赖 + 测试 + 性能 + Git'],
    avgTime: '3-5min',
    output: '全维度问题汇总 + 按严重度排序',
    principle: '采用 CrewAI Flows + Crews 双层架构：外层 Flow 用 @start/@listen 装饰器做确定性编排（解析 → 并行分派 → 聚合 → 报告），内层每个专业 Agent 是独立 Crew（Agent + Task + 工具），并行由 Flow 的多 @listen 节点提供。这是多 Agent 协作的核心演示，也是本项目学习 CrewAI 的主路径。',
    docCategory: 'architecture', docId: 'multi-agent-orchestration',
    recommended: true,
  },
];

export default function ReviewTrigger() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('full');
  const [selectedProject, setSelectedProject] = useState<string | undefined>();
  const [triggerMethod, setTriggerMethod] = useState<'directory' | 'paste' | 'upload'>('directory');
  const [result, setResult] = useState<TriggerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [progressOpen, setProgressOpen] = useState(false);
  const [reviewType, setReviewType] = useState('full');

  const [code, setCode] = useState('');
  const [filename, setFilename] = useState('pasted_code.py');

  useEffect(() => {
    projectApi.list({ page: 1, page_size: 100 }).then(res => setProjects(res.items));
  }, []);

  const handleScan = async () => {
    const project = projects.find(p => p.id === selectedProject);
    if (!project) { message.warning('请先选择项目'); return; }
    setLoading(true);
    try {
      const res = await triggerApi.execute({
        trigger_type: 'local_directory', path: project.path, project_id: project.id,
      });
      setResult(res);
      if (res.success) message.success(`扫描完成，发现 ${res.file_count} 个文件`);
    } catch { message.error('扫描失败'); }
    finally { setLoading(false); }
  };

  const handlePaste = async () => {
    if (!code.trim()) { message.warning('请输入代码'); return; }
    setLoading(true);
    try {
      const res = await triggerApi.execute({ trigger_type: 'code_paste', code, filename });
      setResult(res);
      if (res.success) message.success('代码提交成功');
    } catch { message.error('提交失败'); }
    finally { setLoading(false); }
  };

  const handleUpload = async (file: File) => {
    setLoading(true);
    try {
      const res = await triggerApi.upload(file);
      setResult(res);
      if (res.success) message.success(`上传成功，发现 ${res.file_count} 个文件`);
    } catch { message.error('上传失败'); }
    finally { setLoading(false); }
    return false;
  };

  const handleStartReview = () => {
    if (!selectedProject) { message.warning('请先选择项目'); return; }
    setReviewType(selectedKey);
    setProgressOpen(true);
  };

  const handleProgressCompleted = (reviewId: string, _summary: string) => {
    setProgressOpen(false);
    message.success('审查完成');
    navigate(`/reviews/${reviewId}`);
  };

  const cap = CAPABILITIES.find(c => c.key === selectedKey) || CAPABILITIES[6];

  const openDoc = () => {
    navigate(`/docs?doc=${cap.docId}&category=${cap.docCategory}`);
  };

  return (
    <div>
      <h1>审查能力中心</h1>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 24, fontSize: 15 }}>
        选择一种审查能力，了解它的检测维度和实现原理，然后选择项目和触发方式开始审查。
      </Typography.Paragraph>

      {/* 学习/演示引导：双层架构观察 */}
      <Card size="small" style={{ marginBottom: 16, background: '#f6ffed', borderColor: '#b7eb8f' }}>
        <Space direction="vertical" size={2}>
          <Typography.Text strong>🎓 学习观察（真实执行，非模拟）：</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            选择<strong>单个 Agent</strong>（安全/规范/依赖等）触发，即为<strong>快速演示模式</strong>——用真实 LLM + 真实工具完整跑通
            「外层 Flow（解析 → 并行 Crew → 聚合 → 报告）+ 内层 Crew（Agent 自主调用工具）」双层架构，实时观察每个节点流转。
            选择「综合审查」则 6 个 Crew 并行执行，观察完整双层编排。
          </Typography.Text>
        </Space>
      </Card>

      {/* 顶部选项卡 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Segmented
          value={selectedKey}
          onChange={(v) => setSelectedKey(v as string)}
          options={CAPABILITIES.map(c => ({
            value: c.key,
            label: (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: c.color }}>{c.icon}</span>
                {c.title}
                {c.recommended && <Tag color="red" style={{ margin: 0, fontSize: 10 }}>推荐</Tag>}
              </span>
            ),
          }))}
          style={{ width: '100%', overflowX: 'auto' }}
        />
      </Card>

      {/* 能力介绍折叠块 */}
      <Collapse
        style={{ marginBottom: 16 }}
        items={[{
          key: 'info',
          label: (
            <span>
              <span style={{ color: cap.color, marginRight: 8 }}>{cap.icon}</span>
              {cap.title} — 能力介绍与实现原理
              <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>（点击展开）</Typography.Text>
            </span>
          ),
          children: (
            <div>
              <Row gutter={[24, 16]}>
                <Col xs={24} sm={8}>
                  <Typography.Text type="secondary">工具链</Typography.Text>
                  <div style={{ marginTop: 4 }}>
                    {cap.tools.map(t => <Tag key={t} color={cap.color} style={{ marginBottom: 4 }}>{t}</Tag>)}
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <Typography.Text type="secondary">检测维度</Typography.Text>
                  <div style={{ marginTop: 4 }}>
                    {cap.dimensions.map(d => <Tag key={d} style={{ marginBottom: 4 }}>{d}</Tag>)}
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <Typography.Text type="secondary">输出格式</Typography.Text>
                  <div style={{ marginTop: 4, fontSize: 13 }}>{cap.output}</div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>预计耗时 {cap.avgTime}</Typography.Text>
                </Col>
              </Row>
              <Divider style={{ margin: '16px 0' }} />
              <Typography.Text strong>实现原理</Typography.Text>
              <Typography.Paragraph style={{ marginTop: 8, color: '#555' }}>
                {cap.principle}
              </Typography.Paragraph>
              <Button size="small" icon={<BookOutlined />} onClick={openDoc}>
                查看详细文档
              </Button>
            </div>
          ),
        }]}
      />

      {/* 触发区域 */}
      <Card
        title={<Space><span style={{ color: cap.color }}>{cap.icon}</span>🚀 选择项目并触发 {cap.title}</Space>}
        style={{ marginBottom: 16 }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Typography.Text strong>选择项目</Typography.Text>
            <select
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d9d9d9', marginTop: 4 }}
              value={selectedProject || ''}
              onChange={e => setSelectedProject(e.target.value || undefined)}
            >
              <option value="">-- 请选择项目 --</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.path})</option>)}
            </select>
          </div>
          <div>
            <Typography.Text strong>触发方式</Typography.Text>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              {[
                { key: 'directory' as const, icon: <FolderOpenOutlined />, label: '扫描目录' },
                { key: 'paste' as const, icon: <FileTextOutlined />, label: '粘贴代码' },
                { key: 'upload' as const, icon: <UploadOutlined />, label: '上传文件' },
              ].map(m => (
                <Button key={m.key} type={triggerMethod === m.key ? 'primary' : 'default'} icon={m.icon} onClick={() => setTriggerMethod(m.key)}>
                  {m.label}
                </Button>
              ))}
            </div>
          </div>
          {triggerMethod === 'directory' && (
            <div>
              {result && result.success ? (
                <div>
                  <Tag color="green">扫描到 {result.file_count} 个文件</Tag>
                  <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStartReview} size="large" style={{ marginTop: 8 }}>
                    开始 {cap.title}
                  </Button>
                </div>
              ) : (
                <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={handleScan} block>扫描项目目录</Button>
              )}
            </div>
          )}
          {triggerMethod === 'paste' && (
            <div>
              <Input addonBefore="文件名" value={filename} onChange={e => setFilename(e.target.value)} style={{ marginBottom: 8 }} />
              <Input.TextArea rows={8} placeholder="粘贴你的代码..." value={code} onChange={e => setCode(e.target.value)} style={{ fontFamily: 'monospace', marginBottom: 8 }} />
              <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={handlePaste} block>提交代码</Button>
            </div>
          )}
          {triggerMethod === 'upload' && (
            <Upload.Dragger accept=".py,.js,.ts,.tsx,.jsx,.java,.go,.zip,.tar.gz,.tgz" beforeUpload={handleUpload} showUploadList={false}>
              <p style={{ fontSize: 40, color: '#1677ff' }}><UploadOutlined /></p>
              <p>点击或拖拽文件到此处上传</p>
              <p style={{ color: '#999' }}>支持代码文件和压缩包</p>
            </Upload.Dragger>
          )}
          {result?.error && <Typography.Text type="danger">{result.error}</Typography.Text>}
        </Space>
      </Card>

      {/* 内联执行进度 */}
      <ReviewProgress
        mode="inline"
        projectId={selectedProject || ''}
        reviewType={reviewType}
        open={progressOpen}
        onClose={() => setProgressOpen(false)}
        onCompleted={handleProgressCompleted}
      />

      {/* 扫描结果文件列表 */}
      {result && result.files.length > 0 && (
        <Card title={`扫描结果 — ${result.file_count} 个文件`} style={{ marginBottom: 16 }}>
          <List size="small" bordered dataSource={result.files.slice(0, 30)} renderItem={item => <List.Item>{item}</List.Item>} style={{ maxHeight: 300, overflow: 'auto' }} />
        </Card>
      )}
    </div>
  );
}
