import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#4f46e5',
          colorInfo: '#3b82f6',
          colorSuccess: '#10b981',
          colorWarning: '#f59e0b',
          colorError: '#ef4444',
          colorText: '#1e293b',
          colorTextSecondary: '#55627a',
          colorTextTertiary: '#94a3b8',
          colorBorder: '#e2e8f0',
          colorBorderSecondary: '#eef2f7',
          colorBgLayout: '#f5f7fb',
          colorBgContainer: '#ffffff',
          borderRadius: 10,
          borderRadiusLG: 16,
          fontSize: 14,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', 'Microsoft YaHei', sans-serif",
          boxShadowSecondary: '0 4px 12px -2px rgba(15, 23, 42, 0.08)',
        },
        components: {
          Layout: {
            siderBg: '#ffffff',
            headerBg: 'rgba(255,255,255,0.82)',
            bodyBg: '#f5f7fb',
          },
          Menu: {
            itemSelectedBg: 'rgba(79,70,229,0.12)',
            itemSelectedColor: '#4f46e5',
            itemHoverBg: 'rgba(79,70,229,0.08)',
            itemHoverColor: '#4f46e5',
            itemColor: '#55627a',
            itemHeight: 44,
            itemBorderRadius: 10,
          },
          Card: {
            borderRadiusLG: 16,
            headerBg: '#ffffff',
          },
          Table: {
            headerBg: '#f8fafc',
            headerColor: '#55627a',
            rowHoverBg: 'rgba(79,70,229,0.03)',
          },
          Modal: {
            borderRadiusLG: 16,
          },
          Button: {
            borderRadius: 10,
            controlHeight: 36,
          },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
);
