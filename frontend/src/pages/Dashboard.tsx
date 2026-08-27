import { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Tag, Empty, Typography, Progress, Table, Space } from 'antd';
import {
  ProjectOutlined,
  BugOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
  ThunderboltOutlined,
  SafetyOutlined,
  CodeOutlined,
  ExperimentOutlined,
  BranchesOutlined,
  ClockCircleOutlined,
  RobotOutlined,
  ApartmentOutlined,
  OrderedListOutlined,
  FileDoneOutlined,
  DashboardOutlined,
  LineChartOutlined,
  PieChartOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend, CartesianGrid } from 'recharts';
import api from '@/api/index';
import dayjs from 'dayjs';

interface TrendPoint {
  date: string;
  health_score: number;
  total_findings: number;
  critical_count: number;
  warning_count: number;
}

interface Project {
  id: string;
  name: string;
  path: string;
  language?: string;
  health_score: number;
  is_active: boolean;
}

interface Stats {
  projects_total: number;
  reviews_total: number;
  findings_total: number;
  findings_critical: number;
  findings_warning: number;
  findings_suggestion: number;
  findings_fixed: number;
  findings_acknowledged: number;
  findings_status_distribution: { open: number; acknowledged: number; fixed: number };
  review_trends: TrendPoint[];
  recent_reviews: Array<{
    id: string;
    project_id: string;
    review_type: string;
    status: string;
    total_findings: number;
    critical_count: number;
    warning_count: number;
    suggestion_count: number;
    health_score_snapshot: number | null;
    duration_seconds: number | null;
    created_at: string;
  }>;
}

interface MetricsSnapshot {
  reviews: {
    total: number;
    completed: number;
    failed: number;
    running: number;
    by_type: Record<string, number>;
    avg_duration_s: Record<string, number>;
  };
  findings: {
    total: number;
    by_severity: Record<string, number>;
    by_agent: Record<string, number>;
  };
  llm: {
    calls_total: number;
    calls_success: number;
    calls_failed: number;
    success_rate: number;
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    avg_latency_ms: number;
    tokens_by_model: Record<string, number>;
  };
}

const PIE_COLORS = ['#ff4d4f', '#faad14', '#1677ff', '#d9d9d9'];
const STATUS_COLORS: Record<string, string> = { open: '#1677ff', acknowledged: '#faad14', fixed: '#52c41a' };

// Agent 中文名映射
const AGENT_LABELS: Record<string, string> = {
  security: '安全审查',
  code_style: '代码规范',
  dependency: '依赖审查',
  test_coverage: '测试覆盖',
  performance: '性能分析',
  git_review: 'Git 审查',
};

// 审查类型中文名映射
const TYPE_LABELS: Record<string, string> = {
  full: '综合审查',
  security: '安全审查',
  code_style: '代码规范',
  dependency: '依赖审查',
  test_coverage: '测试覆盖',
  performance: '性能分析',
  git_review: 'Git 审查',
};

// 状态中文名映射
const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

// 健康度颜色
const healthColor = (score: number | null | undefined) => {
  if (score === null || score === undefined) return 'default';
  if (score >= 80) return 'green';
  if (score >= 60) return 'orange';
  return 'red';
};

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<Stats | null>(null);
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    api.get('/system/stats').then((res) => setStats(res as unknown as Stats));
    api.get('/system/metrics').then((res) => setMetrics(res as unknown as MetricsSnapshot));
    api.get('/projects?page=1&page_size=100').then((res) => {
      const data = res as { items?: Project[] };
      setProjects(data.items || []);
    });
  }, []);

  const statusColor: Record<string, string> = {
    pending: 'default',
    running: 'processing',
    completed: 'success',
    failed: 'error',
  };

  const severityPieData = [
    { name: '严重', value: stats?.findings_critical ?? 0 },
    { name: '警告', value: stats?.findings_warning ?? 0 },
    { name: '建议', value: stats?.findings_suggestion ?? 0 },
  ].filter((d) => d.value > 0);

  const statusPieData = stats?.findings_status_distribution
    ? [
        { name: '待处理', value: stats.findings_status_distribution.open },
        { name: '已确认', value: stats.findings_status_distribution.acknowledged },
        { name: '已解决', value: stats.findings_status_distribution.fixed },
      ].filter((d) => d.value > 0)
    : [];

  // 按项目健康度（柱状图数据）
  const projectHealthData = projects
    .filter(p => p.health_score > 0)
    .map(p => ({
      name: p.name.length > 12 ? p.name.slice(0, 12) + '...' : p.name,
      fullName: p.name,
      健康度: p.health_score,
    }))
    .sort((a, b) => b.健康度 - a.健康度);

  // Agent 分布数据
  const agentData = Object.entries(metrics?.findings.by_agent || {})
    .map(([agent, count]) => ({ agent, label: AGENT_LABELS[agent] || agent, count }))
    .sort((a, b) => b.count - a.count);
  const maxAgentCount = agentData.length ? agentData[0].count : 1;

  // 审查类型分布数据
  const typeData = Object.entries(metrics?.reviews.by_type || {})
    .map(([type, count]) => ({ type, label: TYPE_LABELS[type] || type, count }))
    .sort((a, b) => b.count - a.count);

  // 平均耗时数据
  const durationData = Object.entries(metrics?.reviews.avg_duration_s || {})
    .map(([type, dur]) => ({ type, label: TYPE_LABELS[type] || type, dur }))
    .sort((a, b) => b.dur - a.dur);

  // 最近审查表格列
  const reviewColumns = [
    {
      title: '审查类型',
      dataIndex: 'review_type',
      key: 'review_type',
      render: (t: string) => <Tag color="blue">{TYPE_LABELS[t] || t}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={statusColor[s] || 'default'}>{STATUS_LABELS[s] || s}</Tag>,
    },
    {
      title: '问题数',
      dataIndex: 'total_findings',
      key: 'total_findings',
      render: (n: number, r: Stats['recent_reviews'][0]) => (
        <span>
          <Tag color={r.critical_count > 0 ? 'red' : 'default'}>{r.critical_count} 严重</Tag>
          <Tag color={r.warning_count > 0 ? 'orange' : 'default'}>{r.warning_count} 警告</Tag>
          <span style={{ color: '#666' }}>共 {n}</span>
        </span>
      ),
    },
    {
      title: '健康度',
      dataIndex: 'health_score_snapshot',
      key: 'health_score_snapshot',
      render: (h: number | null) => (
        h !== null && h !== undefined
          ? <Tag color={healthColor(h)}>{h}分</Tag>
          : '-'
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      render: (d: number | null) => d ? `${d}s` : '-',
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => dayjs(t).format('MM-DD HH:mm'),
    },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-icon"><DashboardOutlined /></div>
        <div className="page-header-body">
          <h1 className="page-header-title">仪表盘</h1>
          <p className="page-header-subtitle">多 Agent 协作代码审查系统 — 系统概览与运行状态</p>
        </div>
      </div>

      {/* 1. 系统能力概览 */}
      <Card title={<Space size={8}><ApartmentOutlined style={{ color: '#4f46e5' }} />系统能力概览</Space>} style={{ marginBottom: 24 }} size="small">
        <Row gutter={[16, 16]}>
          {[
            { name: '安全审查', icon: <SafetyOutlined />, color: '#f43f5e', tool: 'Semgrep + LLM' },
            { name: '规范审查', icon: <CodeOutlined />, color: '#f59e0b', tool: 'Ruff + LLM' },
            { name: '依赖审查', icon: <ExperimentOutlined />, color: '#3b82f6', tool: 'pip-audit' },
            { name: '测试覆盖', icon: <BugOutlined />, color: '#10b981', tool: 'AST + LLM' },
            { name: '性能分析', icon: <ThunderboltOutlined />, color: '#8b5cf6', tool: 'AST + LLM' },
            { name: 'Git 审查', icon: <BranchesOutlined />, color: '#14b8a6', tool: 'GitPython + LLM' },
          ].map(a => (
            <Col xs={12} sm={8} md={4} key={a.name}>
              <div className="cap-card">
                <div className="cap-card-icon" style={{ background: `${a.color}14`, color: a.color }}>{a.icon}</div>
                <div className="cap-card-name">{a.name}</div>
                <div className="cap-card-tool">{a.tool}</div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 2. 统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="项目总数"
              value={stats?.projects_total ?? 0}
              prefix={<ProjectOutlined style={{ color: '#1677ff' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="审查任务"
              value={stats?.reviews_total ?? 0}
              prefix={<FileSearchOutlined style={{ color: '#722ed1' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="发现问题"
              value={stats?.findings_total ?? 0}
              prefix={<BugOutlined style={{ color: '#ff4d4f' }} />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="已解决"
              value={stats?.findings_fixed ?? 0}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 3. 项目健康度（按项目柱状图，占一行） */}
      <Card title={<Space size={8}><LineChartOutlined style={{ color: '#10b981' }} />项目健康度</Space>} size="small" style={{ marginTop: 24 }}>
        {projectHealthData.length ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={projectHealthData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value) => [`${value} 分`, '健康度']} labelFormatter={(label) => `项目: ${label}`} />
              <Bar dataKey="健康度" radius={[4, 4, 0, 0]}>
                {projectHealthData.map((entry) => (
                  <Cell key={entry.name} fill={entry.健康度 >= 80 ? '#52c41a' : entry.健康度 >= 60 ? '#faad14' : '#ff4d4f'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <Empty description="暂无项目健康度数据（需先对项目执行审查）" />
        )}
      </Card>

      {/* 4. 两个饼图占一行 */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} md={12}>
          <Card title={<Space size={8}><PieChartOutlined style={{ color: '#f43f5e' }} />严重程度分布</Space>} size="small">
            {severityPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={severityPieData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name} ${value}`}>
                    {severityPieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title={<Space size={8}><OrderedListOutlined style={{ color: '#3b82f6' }} />处理状态分布</Space>} size="small">
            {statusPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={statusPieData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name} ${value}`}>
                    {statusPieData.map((entry) => (
                      <Cell key={entry.name} fill={STATUS_COLORS[entry.name === '待处理' ? 'open' : entry.name === '已确认' ? 'acknowledged' : 'fixed']} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* 5. 运行时指标（占一行，用好看的卡片） */}
      <Card title={<Space size={8}><ThunderboltOutlined style={{ color: '#8b5cf6' }} />运行时指标</Space>} size="small" style={{ marginTop: 24 }}>
        {metrics ? (
          <Row gutter={[24, 24]}>
            {/* 审查类型分布 */}
            <Col xs={24} md={8}>
              <Typography.Text strong style={{ fontSize: 13 }}>审查类型分布</Typography.Text>
              <div style={{ marginTop: 12 }}>
                {typeData.map(({ type, label, count }) => (
                  <div key={type} style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <span>{label}</span>
                      <span style={{ color: '#666' }}>{count} 次</span>
                    </div>
                    <Progress percent={Math.round((count / (metrics.reviews.total || 1)) * 100)} size="small" strokeColor="#1677ff" />
                  </div>
                ))}
              </div>
            </Col>

            {/* 平均审查耗时 */}
            <Col xs={24} md={8}>
              <Typography.Text strong style={{ fontSize: 13 }}>平均审查耗时</Typography.Text>
              <div style={{ marginTop: 12 }}>
                {durationData.map(({ type, label, dur }) => (
                  <div key={type} style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <span>{label}</span>
                      <span style={{ color: '#666' }}>{dur}s</span>
                    </div>
                    <Progress percent={Math.min(100, Math.round((dur / 180) * 100))} size="small" strokeColor="#722ed1" />
                  </div>
                ))}
              </div>
            </Col>

            {/* Agent 发现分布 */}
            <Col xs={24} md={8}>
              <Typography.Text strong style={{ fontSize: 13 }}>Agent 发现分布</Typography.Text>
              <div style={{ marginTop: 12 }}>
                {agentData.map(({ agent, label, count }) => (
                  <div key={agent} style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <span>{label}</span>
                      <span style={{ color: '#666' }}>{count} 个</span>
                    </div>
                    <Progress percent={Math.round((count / maxAgentCount) * 100)} size="small" strokeColor="#13c2c2" />
                  </div>
                ))}
              </div>
            </Col>

            {/* LLM 调用统计 */}
            <Col xs={24}>
              <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
                <Typography.Text strong style={{ fontSize: 13 }}>LLM 调用统计</Typography.Text>
                <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
                  <Col xs={12} sm={6}>
                    <Statistic title="调用次数" value={metrics.llm.calls_total} prefix={<RobotOutlined />} />
                  </Col>
                  <Col xs={12} sm={6}>
                    <Statistic title="成功率" value={((metrics.llm.success_rate || 0) * 100).toFixed(0)} suffix="%" />
                  </Col>
                  <Col xs={12} sm={6}>
                    <Statistic title="总 Token" value={(metrics.llm.total_tokens || 0).toLocaleString()} />
                  </Col>
                  <Col xs={12} sm={6}>
                    <Statistic title="平均延迟" value={metrics.llm.avg_latency_ms || 0} suffix="ms" prefix={<ClockCircleOutlined />} />
                  </Col>
                </Row>
              </div>
            </Col>
          </Row>
        ) : (
          <Empty description="加载中..." />
        )}
      </Card>

      {/* 6. 最近审查记录（表格展示，占一行） */}
      <Card title={<Space size={8}><FileDoneOutlined style={{ color: '#4f46e5' }} />最近审查记录</Space>} size="small" style={{ marginTop: 24 }}>
        <Table
          dataSource={stats?.recent_reviews || []}
          columns={reviewColumns}
          rowKey="id"
          size="small"
          pagination={false}
          onRow={(record) => ({
            onClick: () => navigate(`/reviews/${record.id}`),
            style: { cursor: 'pointer' },
          })}
          locale={{ emptyText: '暂无审查记录' }}
        />
      </Card>
    </div>
  );
}
