import api from './index';

export interface TriggerTypeInfo {
  name: string;
  description: string;
}

export interface TriggerResult {
  success: boolean;
  trigger_type: string;
  files: string[];
  file_count: number;
  metadata: Record<string, unknown>;
  error?: string;
}

export interface ReviewResult {
  id: string;
  project_id: string;
  trigger_type: string;
  status: string;
  review_type: string;
  total_findings: number;
  critical_count: number;
  warning_count: number;
  suggestion_count: number;
  nitpick_count: number;
  summary: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export const triggerApi = {
  listTypes: (): Promise<{ triggers: TriggerTypeInfo[] }> =>
    api.get('/triggers/types'),

  execute: (data: {
    trigger_type: string;
    path?: string;
    code?: string;
    filename?: string;
    project_id?: string;
  }): Promise<TriggerResult> =>
    api.post('/triggers', data),

  upload: async (file: File): Promise<TriggerResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch('/api/v1/triggers/upload', {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) throw new Error('上传失败');
    return response.json();
  },

  runReview: (projectId: string, reviewType: string = 'full'): Promise<ReviewResult> =>
    api.post(`/reviews/run?project_id=${projectId}&review_type=${reviewType}`),

  runIncremental: (projectId: string, reviewType: string = 'full', base: string = 'HEAD~1'): Promise<ReviewResult> =>
    api.post(`/reviews/run-incremental?project_id=${projectId}&review_type=${reviewType}&base=${base}`),

  runReviewAsync: async (projectId: string, reviewType: string = 'full'): Promise<ReviewResult> => {
    // 异步触发，立即返回 running 状态
    const resp = await fetch(
      `/api/v1/reviews/run-async?project_id=${projectId}&review_type=${reviewType}`,
      { method: 'POST' },
    );
    if (!resp.ok) throw new Error('触发审查失败');
    return resp.json();
  },

  reviewWsUrl: (reviewId: string): string =>
    `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/reviews/ws/${reviewId}`,
};
