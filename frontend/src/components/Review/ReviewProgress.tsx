import { useEffect, useRef, useState } from 'react';
import { Modal, Steps, Tag, Spin, Alert, Typography, Space, Card, Row, Col, Progress } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  SafetyOutlined,
  CodeOutlined,
  ExperimentOutlined,
  BugOutlined,
  ThunderboltOutlined,
  BranchesOutlined,
  StarFilled,
} from '@ant-design/icons';
import { triggerApi } from '@/api/triggerApi';

interface ProgressEvent {
  event: string;
  review_id: string;
  timestamp: string;
  data: Record<string, unknown>;
}

interface AgentStep {
  agent: string;
  status: 'pending' | 'running' | 'done';
  findings?: number;
  role?: string;
  goal?: string;
}

type FlowNodeStatus = 'pending' | 'running' | 'done';

// 外层 Flow 节点定义（与后端 ReviewFlow 节点对应）
const FLOW_NODES: { node: string; label: string }[] = [
  { node: 'parse_project', label: '① 解析项目' },
  { node: 'crews', label: '② 并行 Crew' },
  { node: 'aggregate', label: '③ 聚合结果' },
  { node: 'generate_report', label: '④ 生成摘要' },
];

const AGENT_LABELS: Record<string, string> = {
  security: '安全审查',
  code_style: '代码规范',
  dependency: '依赖审查',
  test_coverage: '测试覆盖',
  performance: '性能分析',
  git_review: 'Git 审查',
};

const AGENT_ICONS: Record<string, React.ReactNode> = {
  security: <SafetyOutlined />,
  code_style: <CodeOutlined />,
  dependency: <ExperimentOutlined />,
  test_coverage: <BugOutlined />,
  performance: <ThunderboltOutlined />,
  git_review: <BranchesOutlined />,
};

const AGENT_COLORS: Record<string, string> = {
  security: '#ff4d4f',
  code_style: '#faad14',
  dependency: '#1677ff',
  test_coverage: '#52c41a',
  performance: '#722ed1',
  git_review: '#13c2c2',
};

interface ReviewProgressProps {
  projectId: string;
  reviewType: string;
  open: boolean;
  onClose: () => void;
  onCompleted: (reviewId: string, summary: string, healthScore?: number) => void;
  mode?: 'modal' | 'inline';
}

export default function ReviewProgress({
  projectId,
  reviewType,
  open,
  onClose,
  onCompleted,
  mode = 'modal',
}: ReviewProgressProps) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [agents, setAgents] = useState<AgentStep[]>([]);
  const [flowNodes, setFlowNodes] = useState<Record<string, FlowNodeStatus>>({});
  const [completed, setCompleted] = useState(false);
  const [finalSummary, setFinalSummary] = useState('');
  const [healthScore, setHealthScore] = useState<number | undefined>();
  const [error, setError] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const reviewIdRef = useRef<string>('');

  useEffect(() => {
    if (!open || !projectId) return;

    let cancelled = false;
    setEvents([]);
    setAgents([]);
    setFlowNodes({});
    setCompleted(false);
    setFinalSummary('');
    setHealthScore(undefined);
    setError('');

    (async () => {
      try {
        const review = await triggerApi.runReviewAsync(projectId, reviewType);
        if (cancelled) return;
        reviewIdRef.current = review.id;

        const ws = new WebSocket(triggerApi.reviewWsUrl(review.id));
        wsRef.current = ws;

        ws.onopen = () => setConnected(true);
        ws.onmessage = (e) => {
          try {
            const ev: ProgressEvent = JSON.parse(e.data);
            if (ev.event === 'ping') return;
            setEvents((prev) => [...prev, ev]);

            if (ev.event === 'agent_started') {
              const agent = ev.data.agent as string;
              const role = ev.data.role as string | undefined;
              const goal = ev.data.goal as string | undefined;
              setAgents((prev) => {
                const next = [...prev];
                const idx = next.findIndex((s) => s.agent === agent);
                if (idx >= 0) next[idx] = { ...next[idx], status: 'running', role, goal };
                else next.push({ agent, status: 'running', role, goal });
                return next;
              });
            } else if (ev.event === 'agent_completed') {
              const agent = ev.data.agent as string;
              const findings = ev.data.findings as number;
              setAgents((prev) => {
                const next = [...prev];
                const idx = next.findIndex((s) => s.agent === agent);
                if (idx >= 0) {
                  next[idx] = { ...next[idx], status: 'done', findings };
                } else next.push({ agent, status: 'done', findings });
                return next;
              });
            } else if (ev.event === 'flow_node_started') {
              const node = ev.data.node as string;
              setFlowNodes((prev) => ({ ...prev, [node]: 'running' }));
            } else if (ev.event === 'flow_node_completed') {
              const node = ev.data.node as string;
              setFlowNodes((prev) => ({ ...prev, [node]: 'done' }));
            } else if (ev.event === 'review_completed') {
              setCompleted(true);
              setFinalSummary(ev.data.summary as string);
              setHealthScore(ev.data.health_score as number | undefined);
              ws.close();
            } else if (ev.event === 'review_failed') {
              setError(ev.data.error as string);
              ws.close();
            }
          } catch {
            // 忽略解析错误
          }
        };
        ws.onerror = () => setError('WebSocket 连接异常');
        ws.onclose = () => setConnected(false);
      } catch (e) {
        setError(`触发审查失败: ${e instanceof Error ? e.message : String(e)}`);
      }
    })();

    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, [open, projectId, reviewType]);

  const statusIcon = (s: AgentStep['status']) => {
    if (s === 'done') return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    if (s === 'running') return <LoadingOutlined style={{ color: '#1677ff' }} />;
    return <ClockCircleOutlined style={{ color: '#bfbfbf' }} />;
  };

  // 聚合进度
  const doneCount = agents.filter((a) => a.status === 'done').length;
  const totalAgents = reviewType === 'full' ? 6 : 1;
  const aggregatePercent = totalAgents > 0 ? Math.round((doneCount / totalAgents) * 100) : 0;

  // 外层 Flow 节点状态：Crew 节点（②）由 Agent 事件驱动
  const crewsStatus: FlowNodeStatus =
    !flowNodes.aggregate && agents.length > 0 && agents.some((a) => a.status !== 'pending')
      ? 'running'
      : flowNodes.aggregate
        ? 'done'
        : 'pending';

  // Flow 流程图（外层 Flow + 内层 Crew 双层架构可视化）
  const renderFlowDiagram = () => (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
        <Tag color="purple" style={{ marginRight: 4 }}>外层 Flow</Tag>
        确定性编排（CrewAI Flows）
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
        {FLOW_NODES.map((n, i) => {
          const status = n.node === 'crews' ? crewsStatus : flowNodes[n.node] || 'pending';
          const color = status === 'done' ? '#52c41a' : status === 'running' ? '#1677ff' : '#bfbfbf';
          return (
            <div key={n.node} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {i > 0 && <div style={{ width: 14, height: 1, background: color }} />}
              <div style={{
                border: `1px solid ${status === 'pending' ? '#d9d9d9' : color}`,
                borderRadius: 6,
                padding: '2px 8px',
                fontSize: 12,
                background: status === 'done' ? '#f6ffed' : status === 'running' ? '#e6f4ff' : '#fafafa',
                color: status === 'pending' ? '#999' : '#333',
                whiteSpace: 'nowrap',
              }}>
                {status === 'done' ? '✅' : status === 'running' ? '⏳' : '○'} {n.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  // 内联模式：Agent 卡片网格
  const renderAgentGrid = () => (
    <Row gutter={[12, 12]}>
      {agents.map((a) => {
        const color = AGENT_COLORS[a.agent] || '#1677ff';
        const icon = AGENT_ICONS[a.agent] || <BugOutlined />;
        return (
          <Col xs={12} sm={8} md={4} key={a.agent}>
            <div style={{
              border: `1px solid ${a.status === 'done' ? color : '#d9d9d9'}`,
              borderRadius: 8,
              padding: 12,
              textAlign: 'center',
              background: a.status === 'done' ? `${color}0a` : '#fff',
              opacity: a.status === 'pending' ? 0.6 : 1,
            }}>
              <div style={{ fontSize: 22, color: a.status === 'done' ? color : '#999', marginBottom: 6 }}>
                {a.status === 'running' ? <LoadingOutlined /> : icon}
              </div>
              <div style={{ fontWeight: 500, fontSize: 13 }}>{AGENT_LABELS[a.agent] || a.agent}</div>
              {a.role && (
                <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>{a.role}</div>
              )}
              <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                {a.status === 'done'
                  ? <Tag color="green" style={{ margin: 0 }}>{a.findings ?? 0} 个发现</Tag>
                  : a.status === 'running' ? '执行中...' : '等待中'}
              </div>
            </div>
          </Col>
        );
      })}
    </Row>
  );

  // 内联模式渲染
  if (mode === 'inline') {
    return (
      <div style={{ marginBottom: 16 }}>
        {open && (
          <Card
            title={<Space><StarFilled style={{ color: '#f5222d' }} /> 审查执行中</Space>}
            size="small"
          >
            {!connected && !completed && !error && (
              <div style={{ textAlign: 'center', padding: 24 }}>
                <Spin tip="正在触发审查..." />
              </div>
            )}

            {error && <Alert type="error" message="审查失败" description={error} />}

            {(connected || events.length > 0) && !error && (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {renderFlowDiagram()}
                {agents.length > 0 ? (
                  <>
                    <div style={{ fontSize: 12, color: '#666' }}>
                      <Tag color="geekblue" style={{ marginRight: 4 }}>内层 Crew</Tag>
                      专业 Agent 自主协作（CrewAI Crews · 上下文隔离）
                    </div>
                    {renderAgentGrid()}
                    <div>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        聚合进度：{doneCount}/{totalAgents} Agent 完成
                      </Typography.Text>
                      <Progress percent={aggregatePercent} size="small" status={completed ? 'success' : 'active'} />
                    </div>
                  </>
                ) : (
                  <Typography.Text type="secondary">等待 Agent 启动...</Typography.Text>
                )}

                {completed && (
                  <Alert
                    type={healthScore !== undefined && healthScore >= 80 ? 'success' : 'warning'}
                    message={finalSummary || '审查完成'}
                    description={
                      <Space>
                        {healthScore !== undefined && (
                          <Tag color={healthScore >= 80 ? 'green' : healthScore >= 60 ? 'orange' : 'red'}>
                            健康度 {healthScore}
                          </Tag>
                        )}
                        <button className="ant-btn ant-btn-primary ant-btn-sm" onClick={() => onCompleted(reviewIdRef.current, finalSummary, healthScore)}>
                          查看详情
                        </button>
                      </Space>
                    }
                  />
                )}
              </Space>
            )}
          </Card>
        )}
      </div>
    );
  }

  // Modal 模式渲染（保持原样）
  return (
    <Modal
      title="审查进度"
      open={open}
      onCancel={onClose}
      footer={completed ? [
        <button
          key="view"
          className="ant-btn ant-btn-primary"
          onClick={() => onCompleted(reviewIdRef.current, finalSummary, healthScore)}
        >
          查看详情
        </button>,
      ] : undefined}
      width={560}
      closable={completed}
      maskClosable={false}
    >
      {!connected && !completed && !error && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin tip="正在触发审查..." />
        </div>
      )}

      {error && <Alert type="error" message="审查失败" description={error} />}

      {(connected || events.length > 0) && !error && (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {agents.length > 0 ? (
            <Steps direction="vertical" size="small" current={doneCount}
              items={agents.map((a) => ({
                title: <Space>{statusIcon(a.status)} {AGENT_LABELS[a.agent] || a.agent}
                  {a.status === 'done' && a.findings !== undefined && <Tag>{a.findings} 个发现</Tag>}
                </Space>,
                description: a.status === 'running' ? '正在分析...' : a.status === 'done' ? '已完成' : '等待中',
              }))}
            />
          ) : (
            <Typography.Text type="secondary">等待 Agent 启动...</Typography.Text>
          )}

          {completed && (
            <Alert
              type={healthScore !== undefined && healthScore >= 80 ? 'success' : 'warning'}
              message={finalSummary || '审查完成'}
              description={
                <Space>
                  {healthScore !== undefined && (
                    <Tag color={healthScore >= 80 ? 'green' : healthScore >= 60 ? 'orange' : 'red'}>
                      健康度 {healthScore}
                    </Tag>
                  )}
                  <span>点击"查看详情"查看完整报告</span>
                </Space>
              }
            />
          )}
        </Space>
      )}
    </Modal>
  );
}
