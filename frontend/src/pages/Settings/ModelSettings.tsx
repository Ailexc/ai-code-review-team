import { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Switch, Tag, Space, message, Popconfirm, Tooltip } from 'antd';
import { PlusOutlined, ReloadOutlined, ApiOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { llmConfigApi, LLMConfig, LLMConfigCreate, LLMTestResult } from '@/api/llmConfigApi';
import dayjs from 'dayjs';

const PROVIDERS = [
  { label: 'OpenAI', value: 'openai', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { label: 'DeepSeek', value: 'deepseek', models: ['deepseek-chat', 'deepseek-coder', 'deepseek-reasoner'] },
  { label: 'Ollama (本地)', value: 'ollama', models: ['llama3', 'codellama', 'qwen2.5', 'deepseek-r1'] },
  { label: '自定义', value: 'custom', models: [] },
];

const BASE_URLS: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  deepseek: 'https://api.deepseek.com/v1',
  ollama: 'http://localhost:11434/v1',
};

export default function ModelSettings() {
  const [configs, setConfigs] = useState<LLMConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<LLMConfig | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null);
  const [form] = Form.useForm();

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      setConfigs(await llmConfigApi.list());
    } catch {
      message.error('获取模型配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchConfigs(); }, []);

  const handleSave = async (values: LLMConfigCreate & { is_default?: boolean }) => {
    try {
      if (editing) {
        await llmConfigApi.update(editing.id, values);
        message.success('更新成功');
      } else {
        await llmConfigApi.create(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      form.resetFields();
      fetchConfigs();
    } catch (e: unknown) {
      const err = e as { message?: string };
      message.error(err?.message || '操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await llmConfigApi.delete(id);
      message.success('已删除');
      fetchConfigs();
    } catch {
      message.error('删除失败');
    }
  };

  const handleTest = async (id: string) => {
    setTesting(id);
    setTestResult(null);
    try {
      const result = await llmConfigApi.test(id);
      setTestResult(result);
      if (result.success) {
        message.success(`测试通过 (${result.latency_ms}ms)`);
      } else {
        message.warning(result.message);
      }
    } catch {
      message.error('测试请求失败');
    } finally {
      setTesting(null);
    }
  };

  const openEdit = (config: LLMConfig) => {
    setEditing(config);
    form.setFieldsValue({
      name: config.name,
      provider: config.provider,
      model: config.model,
      base_url: config.base_url,
      max_tokens: config.max_tokens,
      temperature: config.temperature,
      is_default: config.is_default,
      is_enabled: config.is_enabled,
    });
    setModalOpen(true);
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, r: LLMConfig) => (
        <Space>
          {name}
          {r.is_default && <Tag color="blue">默认</Tag>}
        </Space>
      ),
    },
    { title: '提供商', dataIndex: 'provider', key: 'provider',
      render: (p: string) => <Tag>{p}</Tag>,
    },
    { title: '模型', dataIndex: 'model', key: 'model' },
    { title: 'API Key', dataIndex: 'api_key_set', key: 'api_key_set',
      render: (set: boolean) => set
        ? <Tag icon={<CheckCircleOutlined />} color="success">已设置</Tag>
        : <Tag icon={<CloseCircleOutlined />} color="default">未设置</Tag>,
    },
    { title: '状态', dataIndex: 'is_enabled', key: 'is_enabled',
      render: (enabled: boolean) => enabled
        ? <Tag color="green">启用</Tag>
        : <Tag color="default">禁用</Tag>,
    },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at',
      render: (t: string) => dayjs(t).format('MM-DD HH:mm'),
    },
    { title: '操作', key: 'action',
      render: (_: unknown, r: LLMConfig) => (
        <Space>
          <Tooltip title="测试连接">
            <Button
              type="link"
              icon={<ApiOutlined />}
              loading={testing === r.id}
              onClick={() => handleTest(r.id)}
            >测试</Button>
          </Tooltip>
          <Button type="link" size="small" onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const provider = Form.useWatch('provider', form);
  const selectedProvider = PROVIDERS.find(p => p.value === provider);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1>模型配置</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchConfigs}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            setEditing(null);
            form.resetFields();
            setModalOpen(true);
          }}>添加模型</Button>
        </Space>
      </div>

      <p style={{ color: '#666', marginBottom: 16 }}>
        配置 LLM 模型用于代码审查的智能分析。支持 OpenAI、DeepSeek、Ollama 等。
      </p>

      <Table
        dataSource={configs}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无模型配置，点击"添加模型"开始配置。' }}
      />

      {testResult && (
        <Modal
          title="测试结果"
          open={!!testResult}
          onCancel={() => setTestResult(null)}
          footer={<Button onClick={() => setTestResult(null)}>关闭</Button>}
        >
          <p><strong>状态：</strong>{testResult.success ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>}</p>
          <p><strong>消息：</strong>{testResult.message}</p>
          {testResult.latency_ms && <p><strong>延迟：</strong>{testResult.latency_ms}ms</p>}
        </Modal>
      )}

      <Modal
        title={editing ? '编辑模型配置' : '添加模型配置'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 gpt-4o、deepseek-chat" />
          </Form.Item>

          <Form.Item name="provider" label="提供商" rules={[{ required: true }]}>
            <Select
              options={PROVIDERS.map(p => ({ label: p.label, value: p.value }))}
              onChange={(val) => {
                form.setFieldsValue({
                  model: undefined,
                  base_url: BASE_URLS[val] || '',
                });
              }}
            />
          </Form.Item>

          <Form.Item name="model" label="模型" rules={[{ required: true, message: '请选择或输入模型' }]}>
            {selectedProvider && selectedProvider.models.length > 0 ? (
              <Select
                showSearch
                allowClear
                options={selectedProvider.models.map(m => ({ label: m, value: m }))}
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div style={{ padding: '8px', borderTop: '1px solid #f0f0f0' }}>
                      <Input
                        placeholder="或输入自定义模型名"
                        onPressEnter={(e) => {
                          const val = (e.target as HTMLInputElement).value;
                          if (val) form.setFieldsValue({ model: val });
                        }}
                      />
                    </div>
                  </>
                )}
              />
            ) : (
              <Input placeholder="模型名称" />
            )}
          </Form.Item>

          <Form.Item name="api_key" label="API Key" extra={editing?.api_key_set ? '已设置，留空则不修改' : ''}>
            <Input.Password placeholder="sk-..." />
          </Form.Item>

          <Form.Item name="base_url" label="API 地址" extra="大多数情况自动填充，无需修改">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>

          <Space size="large">
            <Form.Item name="max_tokens" label="最大 Token" initialValue={4096}>
              <Input type="number" style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="temperature" label="Temperature" initialValue={0.1}>
              <Input type="number" step={0.1} min={0} max={2} style={{ width: 120 }} />
            </Form.Item>
          </Space>

          <Space size="large">
            <Form.Item name="is_default" label="默认模型" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_enabled" label="启用" valuePropName="checked" initialValue={true}>
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
