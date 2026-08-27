import { useState, useEffect } from 'react';
import { Card, Table, Tag, Button, message, Switch, Popconfirm, Collapse } from 'antd';
import { ReloadOutlined, ThunderboltOutlined, SafetyCertificateOutlined, BulbOutlined } from '@ant-design/icons';
import api from '@/api/index';

interface Rule {
  id: string;
  name: string;
  description: string | null;
  rule_type: string;
  agent_name: string;
  severity: string;
  pattern: string | null;
  confidence: number;
  occurrence_count: number;
  weight: number;
  is_enabled: boolean;
  source: string;
  created_at: string;
}

const AGENT_LABELS: Record<string, string> = {
  security: '安全审查',
  code_style: '代码规范',
  dependency: '依赖审查',
  test_coverage: '测试覆盖',
  performance: '性能分析',
  git_review: 'Git 审查',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
  suggestion: 'blue',
  nitpick: 'default',
};

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [mining, setMining] = useState(false);

  const fetchRules = async () => {
    setLoading(true);
    try {
      const res = await api.get('/rules');
      setRules(res as unknown as Rule[]);
    } catch {
      message.error('获取规则失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRules(); }, []);

  const handleMine = async () => {
    setMining(true);
    try {
      const res = await api.post('/rules/mine') as { mined: number; message: string };
      message.success(res.message);
      fetchRules();
    } catch {
      message.error('规则挖掘失败');
    } finally {
      setMining(false);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await api.put(`/rules/${id}/toggle`);
      fetchRules();
    } catch {
      message.error('切换失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/rules/${id}`);
      message.success('规则已删除');
      fetchRules();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: '规则名称', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name',
      render: (a: string) => <Tag color="blue">{AGENT_LABELS[a] || a}</Tag>,
    },
    { title: '类型', dataIndex: 'rule_type', key: 'rule_type',
      render: (t: string) => <Tag>{t}</Tag>,
    },
    { title: '严重度', dataIndex: 'severity', key: 'severity',
      render: (s: string) => <Tag color={SEVERITY_COLORS[s] || 'default'}>{s}</Tag>,
    },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence',
      render: (c: number) => `${Math.round(c * 100)}%`,
    },
    { title: '出现次数', dataIndex: 'occurrence_count', key: 'occurrence_count' },
    { title: '权重', dataIndex: 'weight', key: 'weight',
      render: (w: number) => <Tag color={w >= 2 ? 'red' : w >= 1.5 ? 'orange' : 'default'}>{w.toFixed(1)}</Tag>,
    },
    { title: '来源', dataIndex: 'source', key: 'source',
      render: (s: string) => (
        <Tag color={s === 'auto' ? 'purple' : s === 'feedback' ? 'green' : 'default'}>
          {s === 'auto' ? '自动挖掘' : s === 'feedback' ? '用户反馈' : '手动'}
        </Tag>
      ),
    },
    { title: '启用', dataIndex: 'is_enabled', key: 'is_enabled',
      render: (enabled: boolean, record: Rule) => (
        <Switch checked={enabled} onChange={() => handleToggle(record.id)} />
      ),
    },
    { title: '操作', key: 'action',
      render: (_: unknown, record: Rule) => (
        <Popconfirm title="确定删除此规则？" onConfirm={() => handleDelete(record.id)}>
          <Button type="link" danger size="small">删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-icon"><SafetyCertificateOutlined /></div>
        <div className="page-header-body">
          <h1 className="page-header-title">审查规则</h1>
          <p className="page-header-subtitle">从历史审查记录中自动学习的团队规范，结合用户反馈动态调整权重。</p>
        </div>
        <div className="page-header-actions">
          <Button icon={<ThunderboltOutlined />} loading={mining} onClick={handleMine}>
            从历史挖掘规则
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchRules}>刷新</Button>
        </div>
      </div>

      {/* 知识卡片：审查规则是什么 */}
      <Collapse
        className="knowledge-collapse"
        items={[{
          key: 'about',
          label: (
            <span>
              <BulbOutlined className="knowledge-icon" />
              <span className="knowledge-title">审查规则是什么？</span>
              <span className="knowledge-hint">点击展开了解这个板块的用途</span>
            </span>
          ),
          children: (
            <div className="knowledge-body">
              <p className="knowledge-lead">
                审查规则是系统的「团队规范自动沉淀」——从历史审查记录里自己学习，越用越懂你们团队的代码偏好。
              </p>
              <ul className="knowledge-list">
                <li><strong>自动挖掘：</strong>历史审查中反复出现的问题（≥3 次）会被自动提炼成一条规则。</li>
                <li><strong>置信度与权重：</strong>问题出现次数越多，规则权重越高，代表越需要团队重视。</li>
                <li><strong>持续学习：</strong>你在审查详情里把发现标记为「已确认 / 已解决 / 重新打开」时，会反向调整对应规则的权重——团队总忽略的会降权，总确认的会升权。</li>
                <li><strong>三种来源：</strong>自动挖掘（auto）、用户反馈（feedback）、手动添加。</li>
                <li><strong>可管理：</strong>每条规则都能在这里启用 / 禁用 / 删除，让规范随团队成长。</li>
              </ul>
            </div>
          ),
        }]}
      />

      <Card>
        <Table
          dataSource={rules}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '暂无规则，点击"从历史挖掘规则"从历史审查记录中学习团队规范。' }}
        />
      </Card>
    </div>
  );
}