import { useState, useEffect } from 'react';
import { Card, Select, Button, message, Space, Tag, Typography, Table, Alert, Spin, Collapse, Empty } from 'antd';
import { DiffOutlined, ReloadOutlined, BulbOutlined, RobotOutlined } from '@ant-design/icons';
import api from '@/api/index';
import { projectApi, Project } from '@/api/projectApi';

interface StructuralChange {
  type: string;
  kind: string;
  name: string;
  file_path: string;
  line: number;
  signature: string;
  old_signature?: string;
  description: string;
}

interface ImpactAnalysis {
  change: StructuralChange;
  impacted_callers: Array<{ file_path: string; lines: number[] }>;
  risk: string;
  message: string;
}

interface DiffResult {
  changed_files: string[];
  structural_changes: StructuralChange[];
  impact_analysis: ImpactAnalysis[];
  summary: { changed_files: number; structural_changes: number; impacted_callers: number };
}

interface IntentResult {
  summary: string;
  intent: string;
  risks: Array<{ risk: string; severity: string; suggestion: string }>;
  missing_changes: Array<{ description: string; reason: string }>;
}

const CHANGE_COLORS: Record<string, string> = {
  added: 'green',
  removed: 'red',
  modified: 'orange',
};

const RISK_COLORS: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'green',
};

export default function SemanticDiffPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | undefined>();
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [intent, setIntent] = useState<IntentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [intentLoading, setIntentLoading] = useState(false);

  useEffect(() => {
    projectApi.list({ page: 1, page_size: 100 }).then(res => setProjects(res.items));
  }, []);

  const handleAnalyze = async () => {
    if (!selectedProject) { message.warning('请先选择项目'); return; }
    setLoading(true);
    setDiff(null);
    setIntent(null);
    try {
      const res = await api.get(`/semantic-diff/${selectedProject}/diff`) as unknown as DiffResult;
      setDiff(res);
      if (res.summary.changed_files === 0) {
        message.info('未检测到变更文件');
      }
    } catch {
      message.error('语义 diff 分析失败');
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyzeIntent = async () => {
    if (!selectedProject) { message.warning('请先选择项目'); return; }
    setIntentLoading(true);
    try {
      const res = await api.get(`/semantic-diff/${selectedProject}/diff/intent`) as { diff: DiffResult; intent: IntentResult };
      setDiff(res.diff);
      setIntent(res.intent);
    } catch {
      message.error('意图分析失败');
    } finally {
      setIntentLoading(false);
    }
  };

  const changeColumns = [
    { title: '变更类型', dataIndex: 'type', key: 'type',
      render: (t: string) => <Tag color={CHANGE_COLORS[t] || 'default'}>{t}</Tag>,
    },
    { title: '类型', dataIndex: 'kind', key: 'kind' },
    { title: '名称', dataIndex: 'name', key: 'name',
      render: (n: string) => <Typography.Text code>{n}</Typography.Text>,
    },
    { title: '文件', dataIndex: 'file_path', key: 'file_path', ellipsis: true },
    { title: '行号', dataIndex: 'line', key: 'line' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  ];

  const impactColumns = [
    { title: '变更', dataIndex: 'change', key: 'change',
      render: (c: StructuralChange) => <Typography.Text code>{c.name}</Typography.Text>,
    },
    { title: '风险', dataIndex: 'risk', key: 'risk',
      render: (r: string) => <Tag color={RISK_COLORS[r] || 'default'}>{r}</Tag>,
    },
    { title: '影响', dataIndex: 'message', key: 'message', ellipsis: true },
    { title: '调用方', dataIndex: 'impacted_callers', key: 'impacted_callers',
      render: (callers: Array<{ file_path: string; lines: number[] }>) => (
        <Space size={4} wrap>
          {callers.slice(0, 3).map((c, i) => (
            <Tag key={i}>{c.file_path}:{c.lines[0]}</Tag>
          ))}
          {callers.length > 3 && <Tag>+{callers.length - 3}</Tag>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <div className="page-header-icon"><DiffOutlined /></div>
        <div className="page-header-body">
          <h1 className="page-header-title">语义 Diff 分析</h1>
          <p className="page-header-subtitle">分析 Git 变更的结构化影响（AST 级 diff + 调用图影响 + LLM 意图分析），理解变更的目的和跨文件影响。</p>
        </div>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <Select
            placeholder="选择项目"
            style={{ width: 300 }}
            value={selectedProject}
            onChange={setSelectedProject}
            options={projects.map(p => ({ label: `${p.name} (${p.path})`, value: p.id }))}
          />
          <Button type="primary" icon={<DiffOutlined />} loading={loading} onClick={handleAnalyze}>
            分析变更
          </Button>
          <Button icon={<BulbOutlined />} loading={intentLoading} onClick={handleAnalyzeIntent}>
            LLM 意图分析
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleAnalyze}>刷新</Button>
        </Space>
      </Card>

      {loading && <Spin size="large" style={{ display: 'block', marginTop: 100 }} />}

      {diff && !loading && (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* 变更摘要 */}
          <Card title="变更摘要" size="small">
            <Space size="large">
              <Tag color="blue">变更文件: {diff.summary.changed_files}</Tag>
              <Tag color="purple">结构化变更: {diff.summary.structural_changes}</Tag>
              <Tag color="orange">受影响调用方: {diff.summary.impacted_callers}</Tag>
            </Space>
            <div style={{ marginTop: 8 }}>
              {diff.changed_files.map(f => <Tag key={f} style={{ margin: 2 }}>{f}</Tag>)}
            </div>
          </Card>

          {/* 结构化变更 */}
          {diff.structural_changes.length > 0 && (
            <Card title={`结构化变更 (${diff.structural_changes.length})`} size="small">
              <Table
                dataSource={diff.structural_changes}
                columns={changeColumns}
                rowKey={(r) => `${r.type}-${r.name}-${r.line}`}
                size="small"
                pagination={false}
              />
            </Card>
          )}

          {/* 影响分析 */}
          {diff.impact_analysis.length > 0 && (
            <Card title={`影响分析 (${diff.impact_analysis.length})`} size="small">
              <Table
                dataSource={diff.impact_analysis}
                columns={impactColumns}
                rowKey={(r) => `${r.change.name}-${r.risk}`}
                size="small"
                pagination={false}
              />
            </Card>
          )}

          {diff.structural_changes.length === 0 && diff.impact_analysis.length === 0 && (
            <Empty description="未检测到结构化变更" />
          )}
        </Space>
      )}

      {/* LLM 意图分析结果 */}
      {intent && (
        <Card title={<Space size={8}><RobotOutlined style={{ color: '#7c3aed' }} />LLM 变更意图分析</Space>} style={{ marginTop: 16 }}>
          <Alert
            type="info"
            message={intent.summary || '变更意图分析'}
            description={intent.intent || ''}
            style={{ marginBottom: 16 }}
          />
          {intent.risks.length > 0 && (
            <Collapse
              style={{ marginBottom: 16 }}
              items={[{
                key: 'risks',
                label: `风险 (${intent.risks.length})`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {intent.risks.map((r, i) => (
                      <Alert
                        key={i}
                        type={r.severity === 'high' ? 'error' : r.severity === 'medium' ? 'warning' : 'info'}
                        message={r.risk}
                        description={r.suggestion}
                      />
                    ))}
                  </Space>
                ),
              }]}
            />
          )}
          {intent.missing_changes.length > 0 && (
            <Collapse
              items={[{
                key: 'missing',
                label: `可能遗漏的配套修改 (${intent.missing_changes.length})`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {intent.missing_changes.map((m, i) => (
                      <Alert
                        key={i}
                        type="warning"
                        message={m.description}
                        description={m.reason}
                      />
                    ))}
                  </Space>
                ),
              }]}
            />
          )}
        </Card>
      )}
    </div>
  );
}