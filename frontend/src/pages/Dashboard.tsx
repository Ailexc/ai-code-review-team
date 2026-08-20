import { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic } from 'antd';
import {
  ProjectOutlined,
  BugOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { projectApi } from '@/api/projectApi';

export default function Dashboard() {
  const [stats, setStats] = useState({ total: 0, active: 0 });

  useEffect(() => {
    projectApi.list({ page: 1, page_size: 1 }).then(res => {
      setStats(prev => ({ ...prev, total: res.total }));
    });
  }, []);

  return (
    <div>
      <h1>仪表盘</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="项目总数" value={stats.total} prefix={<ProjectOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="审查任务" value={0} prefix={<FileSearchOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="发现问题" value={0} prefix={<BugOutlined />} valueStyle={{ color: '#ff4d4f' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="已解决" value={0} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
