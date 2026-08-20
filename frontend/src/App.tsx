import { Routes, Route } from 'react-router-dom';
import { Layout } from 'antd';
import MainLayout from './components/Layout/MainLayout';
import Dashboard from './pages/Dashboard';
import ProjectList from './pages/Project/ProjectList';
import ProjectDetail from './pages/Project/ProjectDetail';
import ReviewDetail from './pages/Review/ReviewDetail';
import ReviewTrigger from './pages/Review/ReviewTrigger';
import ReviewList from './pages/Review/ReviewList';
import ModelSettings from './pages/Settings/ModelSettings';

const { Content } = Layout;

function App() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="projects" element={<ProjectList />} />
        <Route path="projects/:id" element={<ProjectDetail />} />
        <Route path="trigger" element={<ReviewTrigger />} />
        <Route path="reviews" element={<ReviewList />} />
        <Route path="reviews/:id" element={<ReviewDetail />} />
        <Route path="settings/models" element={<ModelSettings />} />
      </Route>
    </Routes>
  );
}

export default App;
