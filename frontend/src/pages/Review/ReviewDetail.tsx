import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Tag, Button, message, Spin, Space, List, Typography, Alert, Descriptions, Dropdown, Modal, Timeline, Collapse, Tooltip } from 'antd';
import {
  ArrowLeftOutlined, ExclamationCircleOutlined, WarningOutlined, InfoCircleOutlined,
  DownloadOutlined, EyeOutlined, MoreOutlined, CheckCircleOutlined, UndoOutlined,
  ThunderboltOutlined, MinusCircleOutlined, LoadingOutlined,
  RobotOutlined, ToolOutlined, FileTextOutlined, BulbOutlined, RightOutlined,
} from '@ant-design/icons';
import api from '@/api/index';
import dayjs from 'dayjs';
import { KNOWLEDGE_CARDS, INNER_CREW_CARD, AGGREGATE_CARD, GENERATE_REPORT_CARD, KnowledgeCard } from '@/constants/stepKnowledge';

interface Finding {
  id: string;
  review_id: string;
  agent_name: string;
  category: string;
  severity: string;
  status: string;
  file_path: string | null;
  line_number: number | null;
  code_snippet: string | null;
  message: string;
  suggestion: string | null;
  created_at: string;
}

interface Review {
  id: string;
  project_id: string;
  trigger_type: string;
  status: string;
  review_type: string;
  total_findings: number;
  critical_count: number;
  warning_count: number;
  suggestion_count: number;
  summary: string | null;
  created_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
}

// 审查执行步骤（可观测性）
interface ReviewStep {
  id: string;
  review_id: string;
  sequence: number;
  phase: string;
  node_type: string;
  agent_name: string | null;
  status: string;
  action_text: string | null;
  input_summary: string | null;
  output_summary: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  detail: Record<string, unknown> | null;
}

const AGENT_LABELS: Record<string, string> = {
  security: '安全审查',
  code_style: '代码规范',
  dependency: '依赖审查',
  test_coverage: '测试覆盖',
  performance: '性能分析',
  git_review: 'Git 审查',
};

// LLM 调用全文档案
interface LLMLog {
  id: string;
  agent_name: string | null;
  source: string;
  call_type: string | null;
  model: string | null;
  messages: { role: string; content: string }[] | null;
  response: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number | null;
}

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [review, setReview] = useState<Review | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [steps, setSteps] = useState<ReviewStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [autofixOpen, setAutofixOpen] = useState(false);
  const [autofixResult, setAutofixResult] = useState<Record<string, unknown> | null>(null);
  const [autofixLoading, setAutofixLoading] = useState(false);
  const [llmLogOpen, setLlmLogOpen] = useState(false);
  const [llmLog, setLlmLog] = useState<LLMLog | null>(null);
  const [llmLogLoading, setLlmLogLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      api.get(`/reviews/${id}`),
      api.get(`/findings?review_id=${id}`),
      api.get(`/reviews/${id}/steps`),
    ])
      .then(([reviewData, findingsData, stepsData]) => {
        setReview(reviewData as unknown as Review);
        setFindings(findingsData as unknown as Finding[]);
        setSteps(stepsData as unknown as ReviewStep[]);
      })
      .catch(() => message.error('获取审查详情失败'))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDownloadReport = () => {
    if (!id) return;
    window.open(`/api/v1/reviews/${id}/report`, '_blank');
  };

  const handleViewHtmlReport = () => {
    if (!id) return;
    window.open(`/api/v1/reviews/${id}/report/html`, '_blank');
  };

  const handleStatusChange = async (findingId: string, newStatus: string) => {
    try {
      const updated = await api.put(`/findings/${findingId}/status`, { status: newStatus }) as unknown as Finding;
      setFindings((prev) => prev.map((f) => (f.id === findingId ? { ...f, status: updated.status } : f)));
      message.success(`状态已更新为 ${newStatus}`);
    } catch {
      message.error('状态更新失败');
    }
  };

  const handleAutofix = async (apply: boolean) => {
    if (!id) return;
    setAutofixLoading(true);
    try {
      const result = await api.post(`/reviews/${id}/autofix?apply=${apply}`) as Record<string, unknown>;
      setAutofixResult(result);
      if (apply && (result.fixed_files as string[])?.length > 0) {
        message.success(`已修复 ${(result.fixed_files as string[]).length} 个文件`);
      }
    } catch {
      message.error('自动修复失败');
    } finally {
      setAutofixLoading(false);
    }
  };

  const handleViewTranscript = async (transcriptId: string) => {
    if (!id) return;
    setLlmLogLoading(true);
    setLlmLogOpen(true);
    try {
      const log = await api.get(`/reviews/${id}/llm-logs/${transcriptId}`) as unknown as LLMLog;
      setLlmLog(log);
    } catch {
      message.error('获取 LLM 调用全文失败');
      setLlmLogOpen(false);
    } finally {
      setLlmLogLoading(false);
    }
  };

  const statusBadge: Record<string, { color: string; text: string }> = {
    open: { color: 'processing', text: '待处理' },
    acknowledged: { color: 'warning', text: '已确认' },
    fixed: { color: 'success', text: '已解决' },
  };

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;
  if (!review) return <div>审查记录不存在</div>;

  const severityIcon = (severity: string) => {
    switch (severity) {
      case 'critical': return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
      case 'warning': return <WarningOutlined style={{ color: '#faad14' }} />;
      default: return <InfoCircleOutlined style={{ color: '#1677ff' }} />;
    }
  };

  const severityColor: Record<string, string> = {
    critical: 'red',
    warning: 'orange',
    suggestion: 'blue',
    nitpick: 'default',
  };

  // ---- 执行流程时间线辅助 ----
  const stepIcon = (status: string) => {
    if (status === 'completed') return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    if (status === 'skipped') return <MinusCircleOutlined style={{ color: '#bfbfbf' }} />;
    if (status === 'failed') return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
    return <LoadingOutlined />;
  };

  const stepTitle = (s: ReviewStep) => {
    // 内层 Crew 节点：run_<agent>_crew
    if (s.phase === 'inner_crew' && s.agent_name) {
      return AGENT_LABELS[s.agent_name] || s.agent_name;
    }
    const labels: Record<string, string> = {
      parse_project: '① 解析项目',
      aggregate: '③ 聚合结果',
      generate_report: '④ 生成摘要',
      skip_agent: '跳过 Agent',
    };
    return labels[s.node_type] || s.node_type;
  };

  const stepStatusTag = (s: ReviewStep) => {
    if (s.status === 'completed') return <Tag color="green">完成</Tag>;
    if (s.status === 'skipped') return <Tag>跳过</Tag>;
    if (s.status === 'failed') return <Tag color="red">失败</Tag>;
    return <Tag color="processing">进行中</Tag>;
  };

  // ---- 深度可观测性：父子步骤树 + 知识卡片 + 全文档案 ----

  const knowledgeFor = (s: ReviewStep): KnowledgeCard | null => {
    if (s.phase === 'inner_crew') return INNER_CREW_CARD;
    if (s.node_type === 'aggregate') return AGGREGATE_CARD;
    if (s.node_type === 'generate_report') return GENERATE_REPORT_CARD;
    return KNOWLEDGE_CARDS[s.node_type] || null;
  };

  /** 知识卡片（💡 为什么）+ 源码位置 */
  const knowledgePanel = (s: ReviewStep) => {
    const card = knowledgeFor(s);
    if (!card) return null;
    return (
      <div style={{ marginTop: 6, padding: '8px 10px', background: '#f6f8fa', borderRadius: 6, border: '1px solid #e8e8e8' }}>
        <div style={{ fontSize: 13, color: '#444' }}>
          <BulbOutlined style={{ color: '#faad14', marginRight: 6 }} />
          <Typography.Text type="secondary" strong>为什么：</Typography.Text>
          {card.text}
        </div>
        {card.refs && card.refs.length > 0 && (
          <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
            📂 源码：
            {card.refs.map((r, i) => (
              <Tooltip key={i} title={r.desc}>
                <Typography.Text code copyable={false} style={{ marginRight: 8, fontSize: 12 }}>
                  {r.file}{r.line ? `:${r.line}` : ''}
                </Typography.Text>
              </Tooltip>
            ))}
          </div>
        )}
      </div>
    );
  };

  /** detail 字段 → 小标签（tokens / 规则集统计 / 缓存等） */
  const detailChips = (detail: Record<string, unknown> | null) => {
    if (!detail) return null;
    const chips: React.ReactNode[] = [];
    const pt = detail.prompt_tokens as number | undefined;
    const ct = detail.completion_tokens as number | undefined;
    if (pt != null || ct != null) {
      chips.push(<Tag key="tok" color="geekblue">tokens {pt ?? 0}+{ct ?? 0}</Tag>);
    }
    if (detail.model) chips.push(<Tag key="model">{String(detail.model)}</Tag>);
    if (detail.from_cache === true) chips.push(<Tag key="cache" color="orange">命中缓存</Tag>);
    if (typeof detail.findings === 'number') chips.push(<Tag key="f" color="cyan">发现 {detail.findings}</Tag>);
    if (typeof detail.ruleset === 'string') {
      chips.push(<Tag key="rs" title={String(detail.ruleset)}>{String(detail.ruleset).split('/').slice(-2).join('/')}</Tag>);
    }
    if (typeof detail.tool_name === 'string') chips.push(<Tag key="tn" color="purple">{detail.tool_name}</Tag>);
    return chips.length > 0 ? <div style={{ marginTop: 2 }}>{chips}</div> : null;
  };

  /** 子步骤行（tool / llm 粒度） */
  const childStepRow = (c: ReviewStep) => {
    const isLlm = c.phase === 'llm';
    const transcriptId = (c.detail?.transcript_id as string | undefined);
    return (
      <div key={c.id} style={{ display: 'flex', gap: 8, padding: '5px 0', borderBottom: '1px dashed #f0f0f0' }}>
        <span style={{ color: isLlm ? '#722ed1' : '#13c2c2', flexShrink: 0, paddingTop: 1 }}>
          {isLlm ? <RobotOutlined /> : <ToolOutlined />}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div>
            {c.action_text}
            {c.duration_ms != null && (
              <Typography.Text type="secondary" style={{ marginLeft: 6, fontSize: 12 }}>
                {c.duration_ms >= 1000 ? `${(c.duration_ms / 1000).toFixed(1)}s` : `${c.duration_ms}ms`}
              </Typography.Text>
            )}
            {c.status === 'failed' && <Tag color="red" style={{ marginLeft: 6 }}>失败</Tag>}
          </div>
          {detailChips(c.detail)}
          {isLlm && transcriptId && (
            <Button
              type="link"
              size="small"
              icon={<FileTextOutlined />}
              style={{ padding: 0, marginRight: 12 }}
              onClick={() => handleViewTranscript(transcriptId)}
            >
              查看全文（提示词/响应原文）
            </Button>
          )}
          {knowledgePanel(c)}
        </div>
      </div>
    );
  };

  /** 耗时占比条（相对最耗时父步骤） */
  const durationBar = (s: ReviewStep, maxDur: number) => {
    if (!s.duration_ms || maxDur <= 0 || s.status === 'skipped') return null;
    const pct = Math.max(2, Math.round((s.duration_ms / maxDur) * 100));
    return (
      <Tooltip title={`占最耗时步骤的 ${pct}%`}>
        <div style={{ height: 4, background: '#f0f0f0', borderRadius: 2, marginTop: 4, width: '60%' }}>
          <div style={{ height: 4, width: `${pct}%`, background: s.phase === 'inner_crew' ? '#722ed1' : '#1677ff', borderRadius: 2 }} />
        </div>
      </Tooltip>
    );
  };

  // 组装父子树：父 = outer_flow / inner_crew；子 = tool / llm（按 agent_name 归属到内层 Crew）
  const parentSteps = steps.filter((s) => s.phase === 'outer_flow' || s.phase === 'inner_crew');
  const childSteps = steps.filter((s) => s.phase === 'tool' || s.phase === 'llm');
  const childrenByAgent: Record<string, ReviewStep[]> = {};
  for (const c of childSteps) {
    const key = c.agent_name || '_unknown_';
    (childrenByAgent[key] ||= []).push(c);
  }
  const maxParentDur = Math.max(...parentSteps.map((s) => s.duration_ms || 0), 0);

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/reviews')}>返回列表</Button>
      </Space>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1>审查详情</h1>
        <Space>
          <Button icon={<ThunderboltOutlined />} onClick={() => setAutofixOpen(true)}>自动修复</Button>
          <Button icon={<EyeOutlined />} onClick={handleViewHtmlReport}>HTML报告</Button>
          <Button icon={<DownloadOutlined />} onClick={handleDownloadReport}>下载报告</Button>
        </Space>
      </div>

      <Descriptions bordered column={2} style={{ marginBottom: 24 }}>
        <Descriptions.Item label="审查ID">{review.id.slice(0, 8)}...</Descriptions.Item>
        <Descriptions.Item label="项目ID">
          <a onClick={() => navigate(`/projects/${review.project_id}`)}>{review.project_id.slice(0, 8)}...</a>
        </Descriptions.Item>
        <Descriptions.Item label="审查类型"><Tag color="blue">{review.review_type}</Tag></Descriptions.Item>
        <Descriptions.Item label="触发方式"><Tag>{review.trigger_type}</Tag></Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={review.status === 'completed' ? 'green' : review.status === 'failed' ? 'red' : 'processing'}>
            {review.status}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="耗时">{review.duration_seconds ? `${review.duration_seconds}s` : '-'}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{dayjs(review.created_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
        <Descriptions.Item label="完成时间">{review.completed_at ? dayjs(review.completed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
        <Descriptions.Item label="摘要" span={2}>{review.summary || '-'}</Descriptions.Item>
      </Descriptions>

      {review.total_findings > 0 && (
        <Alert
          type={review.critical_count > 0 ? 'error' : review.warning_count > 0 ? 'warning' : 'success'}
          message={`发现 ${review.total_findings} 个问题`}
          description={
            <Space>
              {review.critical_count > 0 && <Tag color="red">{review.critical_count} 严重</Tag>}
              {review.warning_count > 0 && <Tag color="orange">{review.warning_count} 警告</Tag>}
              {review.suggestion_count > 0 && <Tag color="blue">{review.suggestion_count} 建议</Tag>}
            </Space>
          }
          style={{ marginBottom: 24 }}
        />
      )}

      <Card
        title="⚙️ 执行流程（外层 Flow + 内层 Crew，每一步做了什么、为什么）"
        style={{ marginBottom: 24 }}
        extra={<Tag color="purple">可观测性 · 学习模式</Tag>}
      >
        {steps.length === 0 ? (
          <Typography.Text type="secondary">
            暂无执行步骤记录（旧数据或步骤未持久化）。
          </Typography.Text>
        ) : (
          <Timeline
            items={parentSteps.map((s) => {
              const children = s.agent_name ? (childrenByAgent[s.agent_name] || []) : [];
              return {
                dot: stepIcon(s.status),
                children: (
                  <div key={s.id} style={{ marginBottom: 4 }}>
                    <Space style={{ marginBottom: 4 }} wrap>
                      {s.phase === 'inner_crew' ? (
                        <Tag color="purple">内层 Crew</Tag>
                      ) : (
                        <Tag color="blue">外层 Flow</Tag>
                      )}
                      <Typography.Text strong>{stepTitle(s)}</Typography.Text>
                      {stepStatusTag(s)}
                      {s.duration_ms != null && (
                        <Typography.Text type="secondary">
                          {(s.duration_ms / 1000).toFixed(1)}s
                        </Typography.Text>
                      )}
                    </Space>
                    <div style={{ marginBottom: 2 }}>{s.action_text}</div>
                    {s.output_summary && (
                      <div style={{ color: '#666', fontSize: 13 }}>📤 产出：{s.output_summary}</div>
                    )}
                    {s.input_summary && (
                      <div style={{ color: '#999', fontSize: 12 }}>📥 输入：{s.input_summary}</div>
                    )}
                    {durationBar(s, maxParentDur)}
                    {knowledgePanel(s)}

                    {/* 子步骤：默认折叠，展开看模型调用 / 工具内部细节 */}
                    {children.length > 0 && (
                      <Collapse
                        ghost
                        size="small"
                        style={{ marginTop: 4, marginLeft: -12 }}
                        items={[{
                          key: s.id,
                          label: (
                            <span style={{ fontSize: 13, color: '#555' }}>
                              <RightOutlined style={{ fontSize: 10 }} /> 执行细节（{children.length} 条：模型调用 / 工具内部动作）
                            </span>
                          ),
                          children: <div>{children.map(childStepRow)}</div>,
                        }]}
                      />
                    )}
                  </div>
                ),
              };
            })}
          />
        )}
      </Card>

      {/* LLM 调用全文档案 */}
      <Modal
        title={
          llmLog ? (
            <Space>
              <RobotOutlined style={{ color: '#722ed1' }} />
              LLM 调用全文 · {llmLog.model || '?'} · {llmLog.total_tokens} tokens · {llmLog.latency_ms != null ? `${(llmLog.latency_ms / 1000).toFixed(1)}s` : '-'}
            </Space>
          ) : 'LLM 调用全文'
        }
        open={llmLogOpen}
        onCancel={() => setLlmLogOpen(false)}
        footer={null}
        width={860}
      >
        {llmLogLoading || !llmLog ? (
          <Spin style={{ display: 'block', margin: '40px auto' }} />
        ) : (
          <div style={{ maxHeight: '65vh', overflow: 'auto' }}>
            {(llmLog.messages || []).map((m, i) => (
              <div key={i} style={{ marginBottom: 12 }}>
                <Tag color={m.role === 'system' ? 'orange' : m.role === 'user' ? 'blue' : m.role === 'assistant' ? 'green' : 'default'}>
                  {m.role}
                </Tag>
                <pre style={{
                  background: '#1e1e1e', color: '#d4d4d4', padding: 12, borderRadius: 6,
                  fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '6px 0 0',
                }}>
                  {m.content}
                </pre>
              </div>
            ))}
            {llmLog.response && (
              <div style={{ marginBottom: 12 }}>
                <Tag color="green">assistant（响应原文）</Tag>
                <pre style={{
                  background: '#1e1e1e', color: '#d4d4d4', padding: 12, borderRadius: 6,
                  fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '6px 0 0',
                }}>
                  {llmLog.response}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Card title={`发现列表 (${findings.length})`}>
        <List
          dataSource={findings}
          renderItem={(finding) => {
            const isFixed = finding.status === 'fixed';
            const badge = statusBadge[finding.status] || statusBadge.open;
            return (
            <List.Item
              style={isFixed ? { opacity: 0.6 } : undefined}
              actions={[
                <Dropdown
                  key="status"
                  menu={{
                    items: [
                      { key: 'acknowledged', label: '标记已确认', icon: <CheckCircleOutlined /> },
                      { key: 'fixed', label: '标记已解决', icon: <CheckCircleOutlined style={{ color: '#52c41a' }} /> },
                      { key: 'open', label: '重新打开', icon: <UndoOutlined /> },
                    ],
                    onClick: ({ key }) => handleStatusChange(finding.id, key),
                  }}
                  trigger={['click']}
                >
                  <Button type="text" size="small" icon={<MoreOutlined />} />
                </Dropdown>,
              ]}
            >
              <div style={{ width: '100%', textDecoration: isFixed ? 'line-through' : undefined }}>
                <Space style={{ marginBottom: 8 }}>
                  {severityIcon(finding.severity)}
                  <Tag color={severityColor[finding.severity] || 'default'}>{finding.severity}</Tag>
                  <Tag color={badge.color}>{badge.text}</Tag>
                  {finding.file_path && (
                    <Typography.Text code>
                      {finding.file_path}{finding.line_number ? `:${finding.line_number}` : ''}
                    </Typography.Text>
                  )}
                  <Tag>{finding.agent_name}</Tag>
                </Space>
                <div style={{ marginBottom: 8 }}>{finding.message}</div>
                {finding.code_snippet && (
                  <div style={{
                    background: '#1e1e1e',
                    borderRadius: 6,
                    overflow: 'auto',
                    fontSize: 13,
                    marginBottom: 8,
                    border: '1px solid #333',
                  }}>
                    <div style={{ display: 'flex' }}>
                      <div style={{
                        background: '#2d2d2d',
                        padding: '12px 8px',
                        textAlign: 'right',
                        userSelect: 'none',
                        color: '#858585',
                        fontFamily: 'monospace',
                        fontSize: 12,
                        lineHeight: '20px',
                        minWidth: 32,
                        borderRight: '1px solid #404040',
                      }}>
                        {finding.code_snippet.split('\n').map((_, i) => (
                          <div key={i}>{(finding.line_number || 1) + i - 1}</div>
                        ))}
                      </div>
                      <pre style={{
                        margin: 0,
                        padding: 12,
                        fontFamily: 'monospace',
                        fontSize: 13,
                        lineHeight: '20px',
                        color: '#d4d4d4',
                        overflow: 'auto',
                        flex: 1,
                      }}>
                        <code>{finding.code_snippet}</code>
                      </pre>
                    </div>
                  </div>
                )}
                {finding.suggestion && (
                  <Alert
                    type="info"
                    message={<span><strong>修复建议：</strong>{finding.suggestion}</span>}
                    style={{ marginTop: 8 }}
                  />
                )}
              </div>
            </List.Item>
            );
          }}
          locale={{ emptyText: '未发现任何问题' }}
        />
      </Card>

      {/* 自动修复 Modal */}
      <Modal
        title="自动修复"
        open={autofixOpen}
        onCancel={() => { setAutofixOpen(false); setAutofixResult(null); }}
        width={800}
        footer={autofixResult ? [
          <Button key="close" onClick={() => { setAutofixOpen(false); setAutofixResult(null); }}>关闭</Button>,
        ] : [
          <Button key="preview" loading={autofixLoading} onClick={() => handleAutofix(false)}>预览补丁</Button>,
          <Button key="apply" type="primary" loading={autofixLoading} onClick={() => handleAutofix(true)}>应用修复</Button>,
        ]}
      >
        {!autofixResult ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <ThunderboltOutlined style={{ fontSize: 40, color: '#1677ff', marginBottom: 16 }} />
            <p>将自动修复标记为"可自动修复"的发现（如 import 排序、格式化等）</p>
            <p style={{ color: '#999' }}>建议先"预览补丁"确认后再"应用修复"</p>
          </div>
        ) : (
          <div>
            <Alert
              type="info"
              message={autofixResult.summary as string}
              style={{ marginBottom: 16 }}
            />
            {(autofixResult.fixed_files as string[])?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Typography.Text strong>修复的文件：</Typography.Text>
                {(autofixResult.fixed_files as string[]).map((f: string) => (
                  <Tag key={f} color="green" style={{ margin: 2 }}>{f}</Tag>
                ))}
              </div>
            )}
            {(autofixResult.patches as Array<{ diff: string }>)?.length > 0 && (
              <Card title="补丁预览" size="small">
                {(autofixResult.patches as Array<{ diff: string }>).map((p, i) => (
                  <pre key={i} style={{
                    background: '#1e1e1e',
                    color: '#d4d4d4',
                    padding: 12,
                    borderRadius: 4,
                    fontSize: 12,
                    overflow: 'auto',
                    maxHeight: 400,
                    marginBottom: 8,
                  }}>{p.diff}</pre>
                ))}
              </Card>
            )}
            {(autofixResult.skipped as Array<{ file_path: string; reason: string }>)?.length > 0 && (
              <Card title="跳过的发现" size="small" style={{ marginTop: 16 }}>
                <List
                  size="small"
                  dataSource={autofixResult.skipped as Array<{ file_path: string; reason: string }>}
                  renderItem={(item) => (
                    <List.Item>
                      <Typography.Text code>{item.file_path}</Typography.Text> — {item.reason}
                    </List.Item>
                  )}
                />
              </Card>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
