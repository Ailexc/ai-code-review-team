import { useEffect, useState } from 'react';
import { Table, Tag, Button, message, Space } from 'antd';
import { ReloadOutlined, FileSearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '@/api/index';
import dayjs from 'dayjs';

interface Review {
  id: string;
  project_id: string;
  trigger_type: string;
  status: string;
  review_type: string;
  total_findings: number;
  critical_count: number;
  warning_count: number;
  summary: string | null;
  created_at: string;
  completed_at: string | null;
}

export default function ReviewList() {
  const navigate = useNavigate();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchReviews = async () => {
    setLoading(true);
    try {
      const res = await api.get('/reviews');
      setReviews(Array.isArray(res) ? res : (res as { items?: Review[] })?.items || []);
    } catch {
      message.error('获取审查记录失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchReviews(); }, []);

  const statusColor: Record<string, string> = {
    pending: 'default',
    running: 'processing',
    completed: 'success',
    failed: 'error',
  };

  const columns = [
    { title: '审查ID', dataIndex: 'id', key: 'id', ellipsis: true,
      render: (id: string) => <a onClick={() => navigate(`/reviews/${id}`)}>{id.slice(0, 8)}...</a>,
    },
    { title: '触发方式', dataIndex: 'trigger_type', key: 'trigger_type',
      render: (t: string) => <Tag>{t}</Tag>,
    },
    { title: '审查类型', dataIndex: 'review_type', key: 'review_type' },
    { title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag>,
    },
    { title: '发现数', dataIndex: 'total_findings', key: 'total_findings',
      render: (n: number, r: Review) => (
        <Space size={4}>
          {r.critical_count > 0 && <Tag color="red">{r.critical_count} 严重</Tag>}
          {r.warning_count > 0 && <Tag color="orange">{r.warning_count} 警告</Tag>}
          <span>{n}</span>
        </Space>
      ),
    },
    { title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at',
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm'),
    },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-icon"><FileSearchOutlined /></div>
        <div className="page-header-body">
          <h1 className="page-header-title">审查记录</h1>
          <p className="page-header-subtitle">全部代码审查任务的执行历史与结果汇总。</p>
        </div>
        <div className="page-header-actions">
          <Button icon={<ReloadOutlined />} onClick={fetchReviews}>刷新</Button>
        </div>
      </div>
      <Table
        dataSource={reviews}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: '暂无审查记录，可在项目详情页或"触发审查"页面发起审查。' }}
        onRow={(record) => ({
          onClick: () => navigate(`/reviews/${record.id}`),
          style: { cursor: 'pointer' },
        })}
      />
    </div>
  );
}
