import { useState, useEffect, useRef, useCallback } from 'react';
import { Spin, Empty, Row, Col, Input, Button, Tag } from 'antd';
import {
  BookOutlined,
  SearchOutlined,
  ArrowLeftOutlined,
  DeploymentUnitOutlined,
  TeamOutlined,
  ToolOutlined,
  SafetyOutlined,
  CodeOutlined,
  ExperimentOutlined,
  BugOutlined,
  ThunderboltOutlined,
  BranchesOutlined,
  RocketOutlined,
  FormatPainterOutlined,
  LineChartOutlined,
  DashboardOutlined,
  FundOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import api from '@/api/index';
import './DocsPage.css';

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

// 文档图标映射（emoji → @ant-design/icons）
const DOC_ICONS: Record<string, React.ReactNode> = {
  'architecture-overview': <DeploymentUnitOutlined />,
  'multi-agent-orchestration': <TeamOutlined />,
  'deterministic-plus-llm': <ToolOutlined />,
  'security-agent': <SafetyOutlined />,
  'code-style-agent': <CodeOutlined />,
  'dependency-agent': <ExperimentOutlined />,
  'test-coverage-agent': <BugOutlined />,
  'performance-agent': <ThunderboltOutlined />,
  'git-review-agent': <BranchesOutlined />,
  'quick-start': <RocketOutlined />,
  'autofix-guide': <FormatPainterOutlined />,
  'incremental-review': <LineChartOutlined />,
  'performance-and-observability': <DashboardOutlined />,
  'evaluation-driven-improvements': <FundOutlined />,
};

// 分类强调色（柔和明亮）
const CATEGORY_COLORS: Record<string, { main: string; soft: string }> = {
  '架构设计': { main: '#4f46e5', soft: '#eef2ff' },
  'Agent 能力': { main: '#7c3aed', soft: '#f5f3ff' },
  '使用指南': { main: '#0d9488', soft: '#f0fdfa' },
  '工程实践': { main: '#b45309', soft: '#fffbeb' },
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, docs]);

  const handleSelectDoc = async (doc: DocMeta) => {
    setLoading(true);
    try {
      const res = await api.get(`/docs/${doc.category}/${doc.id}`) as unknown as DocContent;
      setSelectedDoc(res);
      setSearchParams({ doc: doc.id, category: doc.category });
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

  // 统一文档根容器：加 doc-root 类 + 移除内联样式，让前端 CSS 设计令牌统一作用于所有文档
  useEffect(() => {
    if (!selectedDoc || loading || !contentRef.current) return;
    const root = contentRef.current.querySelector(':scope > div');
    if (root && !root.classList.contains('doc-root')) {
      root.classList.add('doc-root');
      root.removeAttribute('style');
    }
  }, [selectedDoc, loading]);

  // 监听滚动，高亮当前目录项
  useEffect(() => {
    if (!selectedDoc || loading || !contentRef.current) return;

    const contentEl = contentRef.current;

    let scrollContainer: Element | null = null;
    let parent: Element | null = contentEl.parentElement;
    while (parent) {
      const style = getComputedStyle(parent);
      if (style.overflow === 'auto' || style.overflow === 'scroll') {
        scrollContainer = parent;
        break;
      }
      parent = parent.parentElement;
    }

    if (!scrollContainer) return;

    const handleScroll = () => {
      const headings = contentEl.querySelectorAll('h2[id], h3[id], h4[id]');
      let currentId = '';
      headings.forEach((heading) => {
        const rect = heading.getBoundingClientRect();
        if (rect.top <= 120) {
          currentId = heading.id;
        }
      });
      if (currentId) {
        setActiveTocId(currentId);
      }
    };

    scrollContainer.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();

    return () => {
      scrollContainer!.removeEventListener('scroll', handleScroll);
    };
  }, [selectedDoc, loading]);

  // 点击目录跳转
  const handleTocClick = (id: string) => {
    const element = contentRef.current?.querySelector(`#${CSS.escape(id)}`);
    if (!element) return;
    let scrollContainer: Element | null = contentRef.current?.parentElement || null;
    while (scrollContainer && getComputedStyle(scrollContainer).overflow !== 'auto' && getComputedStyle(scrollContainer).overflow !== 'scroll') {
      scrollContainer = scrollContainer.parentElement;
    }
    if (scrollContainer) {
      const containerRect = scrollContainer.getBoundingClientRect();
      const elemRect = element.getBoundingClientRect();
      scrollContainer.scrollTo({ top: scrollContainer.scrollTop + elemRect.top - containerRect.top - 80, behavior: 'smooth' });
    } else {
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
      <div className="docs-page">
        <div className="docs-detail">
          {/* 左侧目录 */}
          {toc.length > 0 && (
            <div className="docs-toc">
              <div className="docs-toc-title">目录</div>
              <div ref={tocRef}>
                {toc.map(item => (
                  <div
                    key={item.id}
                    className={`docs-toc-item${activeTocId === item.id ? ' active' : ''}`}
                    onClick={() => handleTocClick(item.id)}
                  >
                    {item.text}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 右侧内容 */}
          <div className="docs-content-wrapper">
            <div className="docs-back-link">
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={handleBackToList}
              >
                返回文档列表
              </Button>
            </div>
            <div className="docs-content">
              {loading ? (
                <Spin style={{ display: 'block', marginTop: 100 }} />
              ) : (
                <div ref={contentRef} dangerouslySetInnerHTML={{ __html: selectedDoc.html }} />
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 列表页模式（卡片式）
  return (
    <div className="docs-page">
      <div className="page-header">
        <div className="page-header-icon"><BookOutlined /></div>
        <div className="page-header-body">
          <h1 className="page-header-title">系统文档</h1>
          <p className="page-header-subtitle">系统架构设计、Agent 知识点、使用指南等技术文档。</p>
        </div>
        <div className="page-header-actions">
          <Input
            className="docs-search"
            placeholder="搜索文档..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            allowClear
          />
        </div>
      </div>

      {Object.entries(filteredCategories).map(([label, items]) => {
        const accent = CATEGORY_COLORS[label] || { main: '#4f46e5', soft: '#eef2ff' };
        return (
          <div key={label} className="docs-category">
            <h2 className="docs-category-title">
              <span className="docs-category-bar" style={{ background: accent.main }} />
              {label}
              <span className="docs-category-count">{items.length} 篇</span>
            </h2>
            <Row gutter={[20, 20]}>
              {items.map(doc => (
                <Col xs={24} sm={12} lg={8} key={doc.id}>
                  <div className="doc-card" onClick={() => handleSelectDoc(doc)}>
                    <div className="doc-card-icon" style={{ color: accent.main, background: accent.soft }}>
                      {DOC_ICONS[doc.id] || <BookOutlined />}
                    </div>
                    <h3 className="doc-card-title">{doc.title}</h3>
                    <p className="doc-card-description">{doc.description}</p>
                    <span className="doc-card-more" style={{ color: accent.main }}>
                      阅读全文 <span className="doc-card-arrow">→</span>
                    </span>
                  </div>
                </Col>
              ))}
            </Row>
          </div>
        );
      })}

      {Object.keys(filteredCategories).length === 0 && (
        <Empty description="未找到匹配的文档" style={{ marginTop: 80 }} />
      )}
    </div>
  );
}
