import { useState, useEffect } from 'react';
import { Card, Button, Upload, Input, Select, message, List, Space, Typography, Tabs, Radio } from 'antd';
import { UploadOutlined, FolderOpenOutlined, FileTextOutlined, ThunderboltOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { triggerApi, TriggerResult } from '@/api/triggerApi';
import { projectApi, Project } from '@/api/projectApi';

export default function ReviewTrigger() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [result, setResult] = useState<TriggerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string | undefined>();
  const [reviewType, setReviewType] = useState('security');
  const [reviewLoading, setReviewLoading] = useState(false);

  // 粘贴代码
  const [code, setCode] = useState('');
  const [filename, setFilename] = useState('pasted_code.py');

  useEffect(() => {
    projectApi.list({ page: 1, page_size: 100 }).then(res => setProjects(res.items));
  }, []);

  const handleLocalDirectory = async () => {
    const project = projects.find(p => p.id === selectedProject);
    if (!project) {
      message.warning('请先选择一个项目');
      return;
    }
    setLoading(true);
    try {
      const res = await triggerApi.execute({
        trigger_type: 'local_directory',
        path: project.path,
        project_id: project.id,
      });
      setResult(res);
      if (res.success) message.success(`扫描完成，发现 ${res.file_count} 个文件`);
    } catch {
      message.error('扫描失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRunReview = async () => {
    if (!selectedProject) {
      message.warning('请先选择一个项目');
      return;
    }
    setReviewLoading(true);
    try {
      const res = await triggerApi.runReview(selectedProject, reviewType);
      message.success(`审查完成，发现 ${res.total_findings} 个问题`);
      navigate(`/reviews/${res.id}`);
    } catch {
      message.error('审查失败');
    } finally {
      setReviewLoading(false);
    }
  };

  const handlePaste = async () => {
    if (!code.trim()) {
      message.warning('请输入代码');
      return;
    }
    setLoading(true);
    try {
      const res = await triggerApi.execute({
        trigger_type: 'code_paste',
        code,
        filename,
      });
      setResult(res);
      if (res.success) message.success('代码提交成功');
    } catch {
      message.error('提交失败');
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file: File) => {
    setLoading(true);
    try {
      const res = await triggerApi.upload(file);
      setResult(res);
      if (res.success) message.success(`上传成功，发现 ${res.file_count} 个文件`);
    } catch {
      message.error('上传失败');
    } finally {
      setLoading(false);
    }
    return false; // 阻止 antd 默认上传
  };

  const reviewTypeOptions = [
    { label: '综合审查 (full)', value: 'full' },
    { label: '安全审查 (security)', value: 'security' },
    { label: '规范审查 (code_style)', value: 'code_style' },
    { label: '依赖审查 (dependency)', value: 'dependency' },
    { label: '测试覆盖 (test_coverage)', value: 'test_coverage' },
  ];

  const tabItems = [
    {
      key: 'directory',
      label: <span><FolderOpenOutlined /> 本地目录</span>,
      children: (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Select
            placeholder="选择项目"
            style={{ width: '100%' }}
            onChange={(v) => setSelectedProject(v)}
            options={projects.map(p => ({ label: `${p.name} (${p.path})`, value: p.id }))}
          />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={handleLocalDirectory} block>
            扫描项目目录
          </Button>
          {result && result.success && (
            <Card size="small" title={`扫描到 ${result.file_count} 个文件`}>
              <Radio.Group
                value={reviewType}
                onChange={(e) => setReviewType(e.target.value)}
                optionType="button"
                buttonStyle="solid"
                style={{ marginBottom: 12 }}
                options={reviewTypeOptions}
              />
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={reviewLoading}
                onClick={handleRunReview}
                block
              >
                开始审查
              </Button>
            </Card>
          )}
          {result && result.error && <Typography.Text type="danger">{result.error}</Typography.Text>}
        </Space>
      ),
    },
    {
      key: 'paste',
      label: <span><FileTextOutlined /> 代码粘贴</span>,
      children: (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Input addonBefore="文件名" value={filename} onChange={e => setFilename(e.target.value)} />
          <Input.TextArea
            rows={10}
            placeholder="粘贴你的代码..."
            value={code}
            onChange={e => setCode(e.target.value)}
            style={{ fontFamily: 'monospace' }}
          />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={handlePaste} block>
            提交代码审查
          </Button>
        </Space>
      ),
    },
    {
      key: 'upload',
      label: <span><UploadOutlined /> 文件上传</span>,
      children: (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Upload.Dragger
            accept=".py,.js,.ts,.tsx,.jsx,.java,.go,.zip,.tar.gz,.tgz"
            beforeUpload={handleUpload}
            showUploadList={false}
          >
            <p style={{ fontSize: 40, color: '#1677ff' }}><UploadOutlined /></p>
            <p>点击或拖拽文件到此处上传</p>
            <p style={{ color: '#999' }}>支持代码文件和压缩包（.zip, .tar.gz）</p>
          </Upload.Dragger>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <h1>触发代码审查</h1>

      <Card style={{ marginBottom: 24 }}>
        <Tabs items={tabItems} />
      </Card>

      {result && result.files.length > 0 && (
        <Card title="扫描结果文件列表">
          <List
            size="small"
            bordered
            dataSource={result.files.slice(0, 30)}
            renderItem={(file) => <List.Item>{file}</List.Item>}
            style={{ maxHeight: 400, overflow: 'auto' }}
          />
          {result.file_count > 30 && <p style={{ color: '#999' }}>...及其他 {result.file_count - 30} 个文件</p>}
        </Card>
      )}
    </div>
  );
}
