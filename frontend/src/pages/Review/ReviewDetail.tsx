import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Tag, Button, message, Spin, Space, List, Typography, Alert, Descriptions } from 'antd';
import { ArrowLeftOutlined, ExclamationCircleOutlined, WarningOutlined, InfoCircleOutlined, DownloadOutlined, EyeOutlined } from '@ant-design/icons';
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
          renderItem={(finding) => (
            <List.Item>
              <div style={{ width: '100%' }}>
                <Space style={{ marginBottom: 8 }}>
                  {severityIcon(finding.severity)}
                  <Tag color={severityColor[finding.severity] || 'default'}>{finding.severity}</Tag>
                  {finding.file_path && (
                    <Typography.Text code>
                      {finding.file_path}{finding.line_number ? `:${finding.line_number}` : ''}
                    </Typography.Text>
                  )}
                  <Tag>{finding.agent_name}</Tag>
                </Space>
                <div style={{ marginBottom: 8 }}>{finding.message}</div>
                {finding.code_snippet && (
                  <pre style={{
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 4,
                    overflow: 'auto',
                    fontSize: 13,
                    marginBottom: 8,
                  }}>
                    <code>{finding.code_snippet}</code>
                  </pre>
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
          )}
          locale={{ emptyText: '未发现任何问题' }}
        />
      </Card>
    </div>
  );
}
