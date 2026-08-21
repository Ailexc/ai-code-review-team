import { useEffect, useRef, useState } from 'react';
import { Modal, Steps, Tag, Spin, Alert, Typography, Space } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
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
}

const AGENT_LABELS: Record<string, string> = {
  security: '安全审查',
  code_style: '代码规范',
  dependency: '依赖审查',
  test_coverage: '测试覆盖',
};

interface ReviewProgressProps {
  projectId: string;
  reviewType: string;
  open: boolean;
  onClose: () => void;
  onCompleted: (reviewId: string, summary: string, healthScore?: number) => void;
}

export default function ReviewProgress({
  projectId,
  reviewType,
  open,
  onClose,
  onCompleted,
}: ReviewProgressProps) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [agents, setAgents] = useState<AgentStep[]>([]);
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
              setAgents((prev) => {
                const next = [...prev];
                const idx = next.findIndex((s) => s.agent === agent);
                if (idx >= 0) next[idx].status = 'running';
                else next.push({ agent, status: 'running' });
                return next;
              });
            } else if (ev.event === 'agent_completed') {
              const agent = ev.data.agent as string;
              const findings = ev.data.findings as number;
              setAgents((prev) => {
                const next = [...prev];
                const idx = next.findIndex((s) => s.agent === agent);
                if (idx >= 0) {
                  next[idx].status = 'done';
                  next[idx].findings = findings;
                } else next.push({ agent, status: 'done', findings });
                return next;
              });
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
            <Steps direction="vertical" size="small" current={agents.filter((a) => a.status === 'done').length}
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
