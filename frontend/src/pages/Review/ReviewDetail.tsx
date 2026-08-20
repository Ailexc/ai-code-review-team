import { useParams } from 'react-router-dom';
import { Card } from 'antd';

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div>
      <h1>审查详情</h1>
      <Card>
        <p>审查 ID: {id}</p>
        <p style={{ color: '#999' }}>审查详情功能将在后续阶段实现。</p>
      </Card>
    </div>
  );
}
