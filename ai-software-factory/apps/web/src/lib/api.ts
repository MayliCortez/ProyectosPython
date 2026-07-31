// Cliente HTTP de la plataforma: un único punto de entrada tipado a la API.

import type {
  Build,
  Conversation,
  Deployment,
  ModuleInstallation,
  ModuleOperation,
  ModuleSummary,
  Project,
  Requirements,
  Session,
  Specification,
} from './types';

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000';

const PREFIX = '/api/v1';
const STORAGE_KEY = 'factory.session';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function loadSession(): Session | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveSession(session: Session): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = loadSession();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (session) headers.Authorization = `Bearer ${session.access_token}`;

  const response = await fetch(`${API_URL}${PREFIX}${path}`, {
    ...init,
    headers,
    cache: 'no-store',
  });

  if (!response.ok) {
    // El backend responde siempre con {code, message, details} en los errores.
    const body = (await response.json().catch(() => null)) as
      | { code?: string; message?: string }
      | null;
    throw new ApiError(
      body?.message ?? response.statusText,
      response.status,
      body?.code ?? 'error',
    );
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  auth: {
    register: (payload: {
      email: string;
      password: string;
      organization_name: string;
      full_name?: string;
    }) => post<Session>('/auth/register', payload),
    login: (payload: { email: string; password: string }) =>
      post<Session>('/auth/login', payload),
    me: () => request<Record<string, string>>('/auth/me'),
  },

  projects: {
    list: () => request<Project[]>('/projects'),
    get: (id: string) => request<Project>(`/projects/${id}`),
    create: (payload: { name: string; prompt: string }) =>
      post<{ project: Project; conversation_id: string }>('/projects', payload),
    archive: (id: string) => post<Project>(`/projects/${id}/archive`),
    remove: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
    requirements: (id: string) => request<Requirements>(`/projects/${id}/requirements`),
    specification: (id: string) => request<Specification>(`/projects/${id}/specification`),
  },

  conversation: {
    get: (projectId: string) => request<Conversation>(`/projects/${projectId}/conversation`),
    send: (projectId: string, content: string) =>
      post<Conversation>(`/projects/${projectId}/conversation/messages`, { content }),
    answer: (projectId: string, questionId: string, answer: string) =>
      post<Conversation>(`/projects/${projectId}/conversation/answers`, {
        question_id: questionId,
        answer,
      }),
  },

  builds: {
    list: (projectId: string) => request<Build[]>(`/projects/${projectId}/builds`),
    get: (projectId: string, buildId: string) =>
      request<Build>(`/projects/${projectId}/builds/${buildId}`),
    start: (projectId: string) => post<Build>(`/projects/${projectId}/builds`),
    download: (projectId: string, buildId: string) =>
      request<{ url: string }>(`/projects/${projectId}/builds/${buildId}/download`),
  },

  deployments: {
    list: (projectId: string) => request<Deployment[]>(`/projects/${projectId}/deployments`),
    create: (projectId: string, payload: { build_id?: string; provider?: string } = {}) =>
      post<Deployment>(`/projects/${projectId}/deployments`, payload),
    stop: (projectId: string, deploymentId: string) =>
      post<Deployment>(`/projects/${projectId}/deployments/${deploymentId}/stop`),
  },

  modules: {
    catalog: (query = '') =>
      request<ModuleSummary[]>(`/modules${query ? `?q=${encodeURIComponent(query)}` : ''}`),
    installed: (projectId: string) =>
      request<ModuleInstallation[]>(`/projects/${projectId}/modules`),
    install: (projectId: string, modules: string[]) =>
      post<ModuleOperation>(`/projects/${projectId}/modules`, { modules }),
    remove: (projectId: string, modules: string[], cascade = false) =>
      post<ModuleOperation>(`/projects/${projectId}/modules/remove`, { modules, cascade }),
  },
};
