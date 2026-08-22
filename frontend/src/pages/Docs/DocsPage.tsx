import { useState, useEffect } from 'react';
import { Card, Menu, Spin, Typography, Empty, Breadcrumb } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import api from '@/api/index';

interface DocMeta {
  id: string;
  title: string;
  category: string;
  category_label: string;
  description: string;
  icon: string;
}

interface DocContent {
  id: string;
  title: string;
  category: string;
  html: string;
}

export default function DocsPage() {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [docsLoading, setDocsLoading] = useState(true);

  useEffect(() => {
    api.get('/docs').then((res) => {
      setDocs(res as unknown as DocMeta[]);
      setDocsLoading(false);
    }).catch(() => setDocsLoading(false));
  }, []);

  const handleSelectDoc = async (doc: DocMeta) => {
    setLoading(true);
    try {
      const res = await api.get(`/docs/${doc.category}/${doc.id}`) as unknown as DocContent;
      setSelectedDoc(res);
    } catch {
      setSelectedDoc(null);
    } finally {
      setLoading(false);
    }
  };

  // 按分类分组
  const categories = docs.reduce<Record<string, DocMeta[]>>((acc, doc) => {
    if (!acc[doc.category_label]) acc[doc.category_label] = [];
    acc[doc.category_label].push(doc);
    return acc;
  }, {});

  const menuItems = Object.entries(categories).map(([label, items]) => ({
    key: label,
    label,
    type: 'group' as const,
    children: items.map(doc => ({
      key: doc.id,
      label: <span>{doc.icon} {doc.title}</span>,
      title: doc.description,
    })),
  }));

  if (docsLoading) {
    return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;
  }

  return (
    <div>
      <h1><BookOutlined /> 系统文档</h1>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 24 }}>
        系统架构设计、Agent 知识点、使用指南等技术文档。
      </Typography.Paragraph>

      <div style={{ display: 'flex', gap: 24 }}>
        {/* 左侧导航 */}
        <Card size="small" style={{ width: 240, flexShrink: 0 }}>
          <Menu
            mode="inline"
            items={menuItems}
            onClick={({ key }) => {
              const doc = docs.find(d => d.id === key);
              if (doc) handleSelectDoc(doc);
            }}
            style={{ border: 'none' }}
          />
        </Card>

        {/* 右侧内容 */}
        <Card style={{ flex: 1, minHeight: 500 }}>
          {loading ? (
            <Spin style={{ display: 'block', marginTop: 100 }} />
          ) : selectedDoc ? (
            <div>
              <Breadcrumb
                style={{ marginBottom: 16 }}
                items={[
                  { title: '系统文档' },
                  { title: selectedDoc.category },
                  { title: selectedDoc.title },
                ]}
              />
              <div dangerouslySetInnerHTML={{ __html: selectedDoc.html }} />
            </div>
          ) : (
            <Empty description="← 点击左侧菜单查看文档" style={{ marginTop: 150 }} />
          )}
        </Card>
      </div>
    </div>
  );
}
