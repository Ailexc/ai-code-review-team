import api from './index';

export interface LLMConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  api_key_set: boolean;
  base_url?: string;
  max_tokens: number;
  temperature: number;
  is_default: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface LLMConfigCreate {
  name: string;
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
  max_tokens?: number;
  temperature?: number;
  is_default?: boolean;
  is_enabled?: boolean;
}

export interface LLMTestResult {
  success: boolean;
  message: string;
  model?: string;
  latency_ms?: number;
}

export const llmConfigApi = {
  list: (): Promise<LLMConfig[]> => api.get('/llm-configs'),

  create: (data: LLMConfigCreate): Promise<LLMConfig> =>
    api.post('/llm-configs', data),

  update: (id: string, data: Partial<LLMConfigCreate>): Promise<LLMConfig> =>
    api.put(`/llm-configs/${id}`, data),

  delete: (id: string): Promise<void> =>
    api.delete(`/llm-configs/${id}`),

  test: (id: string): Promise<LLMTestResult> =>
    api.post(`/llm-configs/${id}/test`),
};
