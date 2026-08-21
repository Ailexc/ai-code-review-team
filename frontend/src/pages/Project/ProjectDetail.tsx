import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Descriptions, Card, Tag, Button, message, Spin, Modal, Form, Input, Select, Space, List, Typography, Alert } from 'antd';
import { EditOutlined, ThunderboltOutlined, ArrowLeftOutlined, SafetyOutlined } from '@ant-design/icons';
import { projectApi, Project } from '@/api/projectApi';
import { triggerApi, TriggerResult, ReviewResult } from '@/api/triggerApi';
import ReviewProgress from '@/components/Review/ReviewProgress';
import dayjs from 'dayjs';

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [triggerResult, setTriggerResult] = useState<TriggerResult | null>(null);
  const [reviewResult, setReviewResult] = useState<ReviewResult | null>(null);
  const [reviewType, setReviewType] = useState('full');
  const [progressOpen, setProgressOpen] = useState(false);
  const [form] = Form.useForm();

  const fetchProject = () => {
    if (!id) return;
    setLoading(true);
    projectApi.get(id)
      .then(setProject)
      .catch(() => message.error('获取项目详情失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchProject(); }, [id]);

  const handleEdit = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await projectApi.update(id, values);
      message.success('更新成功');
      setEditOpen(false);
      fetchProject();
    } catch {
      message.error('更新失败');
    }
  };

  const handleTrigger = async () => {
    if (!project) return;
    setTriggerLoading(true);
    setTriggerResult(null);
    try {
      const result = await triggerApi.execute({
        trigger_type: 'local_directory',
        path: project.path,
        project_id: project.id,
      });
      setTriggerResult(result);
      if (result.success) {
        message.success(`触发成功，发现 ${result.file_count} 个文件`);
      } else {
        message.warning(result.error || '触发失败');
      }
    } catch {
      message.error('触发审查失败');
    } finally {
      setTriggerLoading(false);
    }
  };

  const handleRunReview = () => {
    if (!project) return;
    setReviewResult(null);
    setProgressOpen(true);
  };

  const handleProgressCompleted = (_reviewId: string, summary: string, _health?: number) => {
    setProgressOpen(false);
    const typeLabels: Record<string, string> = {
      full: '综合', security: '安全', code_style: '规范',
      dependency: '依赖', test_coverage: '测试覆盖',
    };
    message.success(`${typeLabels[reviewType] || reviewType}审查完成：${summary}`);
    fetchProject();
    navigate('/reviews');
  };

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;
  if (!project) return <div>项目不存在</div>;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>返回列表</Button>
      </Space>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>{project.name}</h1>
        <Space>
          <Button icon={<EditOutlined />} onClick={() => {
            form.setFieldsValue({
              name: project.name,
              description: project.description,
              language: project.language,
              framework: project.framework,
              is_active: project.is_active,
            });
            setEditOpen(true);
          }}>编辑</Button>
          <Button icon={<ThunderboltOutlined />} onClick={() => setTriggerOpen(true)}>扫描文件</Button>
          <Select
            value={reviewType}
            onChange={setReviewType}
            style={{ width: 150 }}
            options={[
              { label: '综合审查', value: 'full' },
              { label: '安全审查', value: 'security' },
              { label: '规范审查', value: 'code_style' },
              { label: '依赖审查', value: 'dependency' },
              { label: '测试覆盖', value: 'test_coverage' },
            ]}
          />
          <Button type="primary" icon={<SafetyOutlined />} onClick={handleRunReview}>开始审查</Button>
        </Space>
      </div>

      <Descriptions bordered column={1} style={{ marginBottom: 24 }}>
        <Descriptions.Item label="项目路径">{project.path}</Descriptions.Item>
        <Descriptions.Item label="描述">{project.description || '-'}</Descriptions.Item>
        <Descriptions.Item label="语言">{project.language ? <Tag color="blue">{project.language}</Tag> : '-'}</Descriptions.Item>
        <Descriptions.Item label="框架">{project.framework || '-'}</Descriptions.Item>
        <Descriptions.Item label="Git远程">{project.git_remote || '-'}</Descriptions.Item>
        <Descriptions.Item label="健康度">
          <Tag color={project.health_score >= 80 ? 'green' : project.health_score >= 60 ? 'orange' : 'red'}>
            {project.health_score}%
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          {project.is_active ? <Tag color="green">活跃</Tag> : <Tag color="default">停用</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">{dayjs(project.created_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{dayjs(project.updated_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
      </Descriptions>

      <Card title="审查历史" style={{ marginBottom: 24 }}>
        {reviewResult ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              type={reviewResult.critical_count > 0 ? 'error' : reviewResult.warning_count > 0 ? 'warning' : 'success'}
              message={reviewResult.summary || '审查完成'}
              description={
                <Space>
                  {reviewResult.critical_count > 0 && <Tag color="red">{reviewResult.critical_count} 严重</Tag>}
                  {reviewResult.warning_count > 0 && <Tag color="orange">{reviewResult.warning_count} 警告</Tag>}
                  {reviewResult.suggestion_count > 0 && <Tag color="blue">{reviewResult.suggestion_count} 建议</Tag>}
                  {reviewResult.duration_seconds && <span>耗时 {reviewResult.duration_seconds}s</span>}
                </Space>
              }
            />
            <Button onClick={() => navigate('/reviews')}>查看全部审查记录</Button>
          </Space>
        ) : (
          <p style={{ color: '#999' }}>暂无审查记录，点击"安全审查"开始代码审查。</p>
        )}
      </Card>

      {/* 编辑 Modal */}
      <Modal title="编辑项目" open={editOpen} onCancel={() => setEditOpen(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="language" label="语言">
            <Select allowClear options={[
              { label: 'Python', value: 'python' },
              { label: 'TypeScript', value: 'typescript' },
              { label: 'JavaScript', value: 'javascript' },
              { label: 'Java', value: 'java' },
              { label: 'Go', value: 'go' },
            ]} />
          </Form.Item>
          <Form.Item name="framework" label="框架">
            <Input />
          </Form.Item>
          <Form.Item name="is_active" label="状态">
            <Select options={[
              { label: '活跃', value: true },
              { label: '停用', value: false },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 触发审查 Modal */}
      <Modal
        title="触发代码审查"
        open={triggerOpen}
        onCancel={() => { setTriggerOpen(false); setTriggerResult(null); }}
        footer={triggerResult ? [
          <Button key="close" onClick={() => { setTriggerOpen(false); setTriggerResult(null); }}>关闭</Button>,
        ] : undefined}
        width={600}
      >
        {!triggerResult ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <p>将扫描项目目录 <Typography.Text code>{project.path}</Typography.Text> 中的代码文件</p>
            <Button type="primary" loading={triggerLoading} onClick={handleTrigger} size="large">
              开始扫描
            </Button>
          </div>
        ) : (
          <div>
            <p><strong>扫描结果：</strong>发现 {triggerResult.file_count} 个代码文件</p>
            <List
              size="small"
              bordered
              dataSource={triggerResult.files.slice(0, 20)}
              renderItem={(file) => <List.Item>{file}</List.Item>}
              style={{ maxHeight: 300, overflow: 'auto' }}
            />
            {triggerResult.file_count > 20 && <p style={{ color: '#999', marginTop: 8 }}>...及其他 {triggerResult.file_count - 20} 个文件</p>}
          </div>
        )}
      </Modal>

      {/* 实时审查进度 */}
      <ReviewProgress
        projectId={project.id}
        reviewType={reviewType}
        open={progressOpen}
        onClose={() => setProgressOpen(false)}
        onCompleted={handleProgressCompleted}
      />
    </div>
  );
}
