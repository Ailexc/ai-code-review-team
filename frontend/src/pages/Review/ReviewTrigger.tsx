import { useState, useEffect } from 'react';
import { Card, Button, Upload, Input, Select, message, List, Tag, Space, Typography, Tabs } from 'antd';
import { UploadOutlined, FolderOpenOutlined, FileTextOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { triggerApi, TriggerResult, TriggerTypeInfo } from '@/api/triggerApi';
import { projectApi, Project } from '@/api/projectApi';

export default function ReviewTrigger() {
  const [triggerTypes, setTriggerTypes] = useState<TriggerTypeInfo[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [result, setResult] = useState<TriggerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string | undefined>();

  // 粘贴代码
  const [code, setCode] = useState('');
  const [filename, setFilename] = useState('pasted_code.py');

  useEffect(() => {
    triggerApi.listTypes().then(res => setTriggerTypes(res.triggers));
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

  const tabItems = [
    {
      key: 'directory',
      label: <span><FolderOpenOutlined /> 本地目录</span>,
      children: (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Select
            placeholder="选择项目"
            style={{ width: '100%' }}
            onChange={setSelectedProject}
            options={projects.map(p => ({ label: `${p.name} (${p.path})`, value: p.id }))}
          />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={handleLocalDirectory} block>
            扫描项目目录
          </Button>
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

      {result && (
        <Card title="扫描结果">
          <Space direction="vertical" style={{ width: '100%' }}>
            <p>
              <strong>触发器：</strong>
              <Tag color="blue">{result.trigger_type}</Tag>
              <strong>状态：</strong>
              {result.success ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>}
              <strong>文件数：</strong>{result.file_count}
            </p>
            {result.error && <Typography.Text type="danger">{result.error}</Typography.Text>}
            {result.files.length > 0 && (
              <List
                size="small"
                bordered
                dataSource={result.files.slice(0, 30)}
                renderItem={(file) => <List.Item>{file}</List.Item>}
                style={{ maxHeight: 400, overflow: 'auto' }}
              />
            )}
            {result.file_count > 30 && <p style={{ color: '#999' }}>...及其他 {result.file_count - 30} 个文件</p>}
          </Space>
        </Card>
      )}
    </div>
  );
}
