import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Tag, Button, message, Spin, Space, List, Typography, Alert, Descriptions, Dropdown, Modal } from 'antd';
import {
  ArrowLeftOutlined, ExclamationCircleOutlined, WarningOutlined, InfoCircleOutlined,
  DownloadOutlined, EyeOutlined, MoreOutlined, CheckCircleOutlined, UndoOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import api from '@/api/index';
import dayjs from 'dayjs';

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

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [review, setReview] = useState<Review | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [autofixOpen, setAutofixOpen] = useState(false);
  const [autofixResult, setAutofixResult] = useState<Record<string, unknown> | null>(null);
  const [autofixLoading, setAutofixLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      api.get(`/reviews/${id}`),
      api.get(`/findings?review_id=${id}`),
    ])
      .then(([reviewData, findingsData]) => {
        setReview(reviewData as unknown as Review);
        setFindings(findingsData as unknown as Finding[]);
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
