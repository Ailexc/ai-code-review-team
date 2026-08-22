import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Spin, Typography, Empty, Row, Col, Tag, Input, Button, Affix } from 'antd';
import { BookOutlined, SearchOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
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

// 分类颜色映射
const CATEGORY_COLORS: Record<string, string> = {
  '架构设计': '#1677ff',
  'Agent 能力': '#722ed1',
  '使用指南': '#52c41a',
};

export default function DocsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [docsLoading, setDocsLoading] = useState(true);
  const [searchText, setSearchText] = useState('');
  const [activeTocId, setActiveTocId] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);
  const tocRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get('/docs').then((res) => {
      setDocs(res as unknown as DocMeta[]);
      setDocsLoading(false);
    }).catch(() => setDocsLoading(false));
  }, []);

  // 支持 URL 参数直接打开文档
  useEffect(() => {
    const docId = searchParams.get('doc');
    const category = searchParams.get('category');
    if (docId && category && docs.length > 0) {
      const doc = docs.find(d => d.id === docId && d.category === category);
      if (doc) handleSelectDoc(doc);
    }
  }, [searchParams, docs]);

  const handleSelectDoc = async (doc: DocMeta) => {
    setLoading(true);
    try {
      const res = await api.get(`/docs/${doc.category}/${doc.id}`) as unknown as DocContent;
      setSelectedDoc(res);
      setSearchParams({ doc: doc.id, category: doc.category });
      // 滚动到顶部
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch {
      setSelectedDoc(null);
    } finally {
      setLoading(false);
    }
  };

  const handleBackToList = () => {
    setSelectedDoc(null);
    setSearchParams({});
    setActiveTocId('');
  };

  // 解析 HTML 中的目录（nav 标签）
  const extractToc = useCallback((html: string): { id: string; text: string }[] => {
    const toc: { id: string; text: string }[] = [];
    const navMatch = html.match(/<nav[^>]*>([\s\S]*?)<\/nav>/);
    if (navMatch) {
      const linkMatches = navMatch[1].matchAll(/<a[^>]*href="#([^"]+)"[^>]*>([^<]+)<\/a>/g);
      for (const match of linkMatches) {
        toc.push({ id: match[1], text: match[2] });
      }
    }
    return toc;
  }, []);

  // 监听滚动，高亮当前目录项
  useEffect(() => {
    if (!selectedDoc) return;
    const handleScroll = () => {
      const headings = contentRef.current?.querySelectorAll('[id]');
      if (!headings) return;
      let currentId = '';
      headings.forEach((heading) => {
        const rect = heading.getBoundingClientRect();
        if (rect.top <= 120) {
          currentId = heading.id;
        }
      });
      if (currentId && currentId !== activeTocId) {
        setActiveTocId(currentId);
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [selectedDoc, activeTocId]);

  // 点击目录跳转
  const handleTocClick = (id: string) => {
    const element = contentRef.current?.querySelector(`#${CSS.escape(id)}`);
    if (element) {
      const top = element.getBoundingClientRect().top + window.scrollY - 100;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  };

  // 按分类分组
  const categories = docs.reduce<Record<string, DocMeta[]>>((acc, doc) => {
    if (!acc[doc.category_label]) acc[doc.category_label] = [];
    acc[doc.category_label].push(doc);
    return acc;
  }, {});

  // 搜索过滤
  const filteredCategories = Object.entries(categories).reduce<Record<string, DocMeta[]>>((acc, [label, items]) => {
    const filtered = items.filter(doc =>
      doc.title.toLowerCase().includes(searchText.toLowerCase()) ||
      doc.description.toLowerCase().includes(searchText.toLowerCase())
    );
    if (filtered.length > 0) acc[label] = filtered;
    return acc;
  }, {});

  const toc = selectedDoc ? extractToc(selectedDoc.html) : [];

  if (docsLoading) {
    return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;
  }

  // 详情页模式
  if (selectedDoc) {
    return (
      <div style={{ display: 'flex', gap: 24 }}>
        {/* 左侧目录 */}
        {toc.length > 0 && (
          <Affix offsetTop={80} style={{ alignSelf: 'flex-start' }}>
            <Card
              size="small"
              title="📑 目录"
              style={{ width: 200, flexShrink: 0 }}
              styles={{ body: { padding: '8px 12px' } }}
            >
              <div ref={tocRef}>
                {toc.map(item => (
                  <div
                    key={item.id}
                    onClick={() => handleTocClick(item.id)}
                    style={{
                      padding: '4px 8px',
                      cursor: 'pointer',
                      borderRadius: 4,
                      fontSize: 13,
                      color: activeTocId === item.id ? '#1677ff' : '#666',
                      background: activeTocId === item.id ? '#e6f7ff' : 'transparent',
                      fontWeight: activeTocId === item.id ? 500 : 400,
                      marginBottom: 2,
                      transition: 'all 0.2s',
                    }}
                  >
                    {item.text}
                  </div>
                ))}
              </div>
            </Card>
          </Affix>
        )}

        {/* 右侧内容 */}
        <div style={{ flex: 1 }}>
          <Button
            type="link"
            icon={<ArrowLeftOutlined />}
            onClick={handleBackToList}
            style={{ marginBottom: 12, padding: 0 }}
          >
            返回文档列表
          </Button>
          <Card>
            {loading ? (
              <Spin style={{ display: 'block', marginTop: 100 }} />
            ) : (
              <div ref={contentRef} dangerouslySetInnerHTML={{ __html: selectedDoc.html }} />
            )}
          </Card>
        </div>
      </div>
    );
  }

  // 列表页模式（卡片式）
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}><BookOutlined /> 系统文档</h1>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            系统架构设计、Agent 知识点、使用指南等技术文档。
          </Typography.Paragraph>
        </div>
        <Input
          placeholder="搜索文档..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          style={{ width: 260 }}
          allowClear
        />
      </div>

      {Object.entries(filteredCategories).map(([label, items]) => (
        <div key={label} style={{ marginBottom: 32 }}>
          <Typography.Title level={4} style={{ marginBottom: 16 }}>
            <Tag color={CATEGORY_COLORS[label] || '#666'} style={{ fontSize: 13 }}>{label}</Tag>
          </Typography.Title>
          <Row gutter={[16, 16]}>
            {items.map(doc => (
              <Col xs={24} sm={12} lg={8} key={doc.id}>
                <Card
                  hoverable
                  onClick={() => handleSelectDoc(doc)}
                  styles={{
                    body: { padding: 20 },
                  }}
                  style={{ height: '100%' }}
                >
                  <div style={{ fontSize: 32, marginBottom: 12 }}>{doc.icon}</div>
                  <Typography.Title level={5} style={{ marginBottom: 8 }}>{doc.title}</Typography.Title>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 13 }}>
                    {doc.description}
                  </Typography.Paragraph>
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      ))}

      {Object.keys(filteredCategories).length === 0 && (
        <Empty description="未找到匹配的文档" style={{ marginTop: 80 }} />
      )}
    </div>
  );
}
