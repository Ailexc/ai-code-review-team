import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Tag } from 'antd';
import {
  DashboardOutlined,
  ProjectOutlined,
  FileSearchOutlined,
  ThunderboltOutlined,
  SettingOutlined,
  BookOutlined,
  SafetyCertificateOutlined,
  DiffOutlined,
  CodeOutlined,
  ApiOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/projects', icon: <ProjectOutlined />, label: '项目管理' },
  { key: '/trigger', icon: <ThunderboltOutlined />, label: '触发审查' },
  { key: '/reviews', icon: <FileSearchOutlined />, label: '审查记录' },
  { key: '/settings/models', icon: <SettingOutlined />, label: '模型配置' },
  { key: '/rules', icon: <SafetyCertificateOutlined />, label: '审查规则' },
  { key: '/semantic-diff', icon: <DiffOutlined />, label: '语义Diff' },
  { type: 'divider' },
  { key: '/docs', icon: <BookOutlined />, label: '系统文档' },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0" width={232} theme="light" className="app-sider">
        <div className="app-logo">
          <span className="app-logo-mark"><CodeOutlined /></span>
          <span className="app-logo-text">AI Code Review</span>
        </div>
        <Menu
          mode="inline"
          className="app-menu"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout className="app-main" style={{ overflow: 'auto' }}>
        <Header className="app-header">
          <h2 className="app-header-title">
            <ApiOutlined /> 多 Agent 协作代码审查系统
          </h2>
          <div className="app-header-right">
            <Tag color="geekblue" style={{ borderRadius: 999, padding: '1px 12px', margin: 0 }}>
              CrewAI Flows + Crews
            </Tag>
          </div>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
