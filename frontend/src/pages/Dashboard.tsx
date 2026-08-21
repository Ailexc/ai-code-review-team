import { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, List, Tag, Empty } from 'antd';
import {
  ProjectOutlined,
  BugOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '@/api/index';
import dayjs from 'dayjs';

interface Stats {
  projects_total: number;
  reviews_total: number;
  findings_total: number;
  findings_critical: number;
  findings_warning: number;
  findings_suggestion: number;
  findings_fixed: number;
  recent_reviews: Array<{
    id: string;
    project_id: string;
    review_type: string;
    status: string;
    total_findings: number;
    critical_count: number;
    warning_count: number;
    created_at: string;
  }>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.get('/system/stats').then((res) => setStats(res as Stats));
  }, []);

  const statusColor: Record<string, string> = {
    pending: 'default',
    running: 'processing',
    completed: 'success',
    failed: 'error',
  };

  return (
    <div>
      <h1>仪表盘</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="项目总数" value={stats?.projects_total ?? 0} prefix={<ProjectOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="审查任务" value={stats?.reviews_total ?? 0} prefix={<FileSearchOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="发现问题"
              value={stats?.findings_total ?? 0}
              prefix={<BugOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="已解决"
              value={stats?.findings_fixed ?? 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={8}>
          <Card title="严重程度分布">
            <Row gutter={[8, 8]}>
              <Col span={8}>
                <Statistic title="严重" value={stats?.findings_critical ?? 0} valueStyle={{ color: '#ff4d4f' }} prefix={<ExclamationCircleOutlined />} />
              </Col>
              <Col span={8}>
                <Statistic title="警告" value={stats?.findings_warning ?? 0} valueStyle={{ color: '#faad14' }} prefix={<WarningOutlined />} />
              </Col>
              <Col span={8}>
                <Statistic title="建议" value={stats?.findings_suggestion ?? 0} valueStyle={{ color: '#1677ff' }} prefix={<BugOutlined />} />
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} sm={16}>
          <Card title="最近审查记录">
            {stats?.recent_reviews?.length ? (
              <List
                size="small"
                dataSource={stats.recent_reviews}
                renderItem={(r) => (
                  <List.Item
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/reviews/${r.id}`)}
                  >
                    <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>
                        <Tag color={statusColor[r.status] || 'default'}>{r.status}</Tag>
                        <Tag color="blue">{r.review_type}</Tag>
                        {r.total_findings > 0 && <Tag color={r.critical_count > 0 ? 'red' : 'orange'}>{r.total_findings} 个问题</Tag>}
                      </span>
                      <span style={{ color: '#999' }}>{dayjs(r.created_at).format('MM-DD HH:mm')}</span>
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无审查记录" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
