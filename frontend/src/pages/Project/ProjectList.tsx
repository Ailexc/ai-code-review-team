import { useEffect, useState, useCallback } from 'react';
import { Table, Button, Space, Tag, Modal, Form, Input, Select, message, Popconfirm, Row, Col } from 'antd';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { projectApi, Project, ProjectCreate } from '@/api/projectApi';
import dayjs from 'dayjs';

export default function ProjectList() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();

  const fetchProjects = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const res = await projectApi.list({
        page: p,
        page_size: 20,
        search: search || undefined,
        language: language || undefined,
      });
      setProjects(res.items);
      setTotal(res.total);
    } catch {
      message.error('获取项目列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, search, language]);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  const handleCreate = async (values: ProjectCreate) => {
    try {
      await projectApi.create(values);
      message.success('项目创建成功');
      setModalOpen(false);
      form.resetFields();
      fetchProjects();
    } catch {
      message.error('创建失败');
    }
  };

  const handleEdit = async (values: Record<string, unknown>) => {
    if (!editingProject) return;
    try {
      await projectApi.update(editingProject.id, values);
      message.success('更新成功');
      setEditModalOpen(false);
      setEditingProject(null);
      editForm.resetFields();
      fetchProjects();
    } catch {
      message.error('更新失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await projectApi.delete(id);
      message.success('删除成功');
      fetchProjects();
    } catch {
      message.error('删除失败');
    }
  };

  const openEdit = (record: Project) => {
    setEditingProject(record);
    editForm.setFieldsValue({
      name: record.name,
      description: record.description,
      language: record.language,
      framework: record.framework,
      is_active: record.is_active,
    });
    setEditModalOpen(true);
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: Project) => (
        <a onClick={() => navigate(`/projects/${record.id}`)}>{text}</a>
      ),
    },
    { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true },
    { title: '语言', dataIndex: 'language', key: 'language',
      render: (lang: string) => lang ? <Tag color="blue">{lang}</Tag> : '-',
    },
    { title: '健康度', dataIndex: 'health_score', key: 'health_score',
      render: (score: number) => (
        <Tag color={score >= 80 ? 'green' : score >= 60 ? 'orange' : 'red'}>{score}%</Tag>
      ),
    },
    { title: '状态', dataIndex: 'is_active', key: 'is_active',
      render: (active: boolean) => active
        ? <Tag color="green">活跃</Tag>
        : <Tag color="default">停用</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at',
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm'),
    },
    { title: '操作', key: 'action',
      render: (_: unknown, record: Project) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除该项目？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1>项目管理</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => fetchProjects()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建项目</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Input.Search
            placeholder="搜索项目名称或描述"
            allowClear
            enterButton={<SearchOutlined />}
            onSearch={(v) => { setSearch(v); setPage(1); }}
          />
        </Col>
        <Col span={6}>
          <Select
            placeholder="筛选语言"
            allowClear
            style={{ width: '100%' }}
            onChange={(v) => { setLanguage(v); setPage(1); }}
            options={[
              { label: 'Python', value: 'python' },
              { label: 'TypeScript', value: 'typescript' },
              { label: 'JavaScript', value: 'javascript' },
              { label: 'Java', value: 'java' },
              { label: 'Go', value: 'go' },
            ]}
          />
        </Col>
      </Row>

      <Table
        dataSource={projects}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: setPage,
          showTotal: (t) => `共 ${t} 个项目`,
        }}
      />

      {/* 新建项目 Modal */}
      <Modal title="新建项目" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="my-project" />
          </Form.Item>
          <Form.Item name="path" label="项目路径" rules={[{ required: true, message: '请输入项目路径' }]}>
            <Input placeholder="/path/to/project" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="项目描述（可选）" />
          </Form.Item>
          <Form.Item name="language" label="语言">
            <Select allowClear placeholder="选择语言" options={[
              { label: 'Python', value: 'python' },
              { label: 'TypeScript', value: 'typescript' },
              { label: 'JavaScript', value: 'javascript' },
              { label: 'Java', value: 'java' },
              { label: 'Go', value: 'go' },
            ]} />
          </Form.Item>
          <Form.Item name="framework" label="框架">
            <Input placeholder="如 FastAPI、React、Vue（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑项目 Modal */}
      <Modal title="编辑项目" open={editModalOpen} onCancel={() => { setEditModalOpen(false); setEditingProject(null); }} onOk={() => editForm.submit()}>
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
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
    </div>
  );
}
