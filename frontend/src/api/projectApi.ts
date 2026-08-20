import api from './index';

export interface Project {
  id: string;
  name: string;
  path: string;
  description?: string;
  language?: string;
  framework?: string;
  git_remote?: string;
  health_score: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  path: string;
  description?: string;
  language?: string;
  framework?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  language?: string;
  framework?: string;
  is_active?: boolean;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
}

export const projectApi = {
  list: (params?: { page?: number; page_size?: number; language?: string; search?: string }): Promise<ProjectListResponse> =>
    api.get('/projects', { params }),

  get: (id: string): Promise<Project> =>
    api.get(`/projects/${id}`),

  create: (data: ProjectCreate): Promise<Project> =>
    api.post('/projects', data),

  update: (id: string, data: Partial<ProjectUpdate>): Promise<Project> =>
    api.put(`/projects/${id}`, data),

  delete: (id: string): Promise<void> =>
    api.delete(`/projects/${id}`),
};
