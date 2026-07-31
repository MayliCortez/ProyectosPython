// Tipos del contrato con la API. Reflejan los esquemas de `interfaces/http/schemas.py`.

export type ProjectStatus =
  | 'draft'
  | 'gathering_requirements'
  | 'specified'
  | 'building'
  | 'built'
  | 'deploying'
  | 'deployed'
  | 'failed'
  | 'archived';

export interface Project {
  id: string;
  name: string;
  slug: string;
  status: ProjectStatus;
  business_domain: string;
  prompt: string;
  modules: string[];
  tech_stack: Record<string, string>;
  live_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface ClarifyingQuestion {
  id: string;
  text: string;
  rationale: string;
  options: string[];
  required: boolean;
}

export interface Conversation {
  id: string;
  project_id: string;
  messages: Message[];
  pending_questions: ClarifyingQuestion[];
  answers: Record<string, string>;
}

export type StageStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

export interface BuildStage {
  name: string;
  agent: string;
  status: StageStatus;
  error: string | null;
  duration_seconds: number | null;
  logs: string[];
}

export interface Build {
  id: string;
  project_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progress: number;
  stages: BuildStage[];
  artifact_count: number;
  total_bytes: number;
  bundle_key: string | null;
  error: string | null;
  created_at: string;
}

export interface Deployment {
  id: string;
  project_id: string;
  build_id: string;
  provider: string;
  status: 'pending' | 'pushing' | 'starting' | 'running' | 'failed' | 'stopped';
  url: string | null;
  error: string | null;
  logs: string[];
  created_at: string;
}

export interface ModuleSummary {
  key: string;
  name: string;
  description: string;
  category: string;
  version: string;
  depends_on: string[];
  conflicts_with: string[];
  tables: string[];
  endpoints: number;
  pages: { route: string; title: string; icon: string }[];
  permissions: string[];
  env_vars: string[];
  removable: boolean;
}

export interface ModuleInstallation {
  module_key: string;
  version: string;
  state: string;
  config: Record<string, unknown>;
}

export interface ModuleOperation {
  installed: ModuleInstallation[];
  added: string[];
  removed: string[];
  warnings: string[];
}

export interface Requirements {
  id: string;
  project_id: string;
  summary: string;
  business_domain: string;
  markdown: string;
  suggested_modules: string[];
}

export interface Specification {
  id: string;
  project_id: string;
  version: number;
  tech_stack: Record<string, string>;
  entities: {
    name: string;
    table: string;
    description: string;
    fields: { name: string; type: string; required: boolean; unique: boolean }[];
  }[];
  endpoints: { method: string; path: string; summary: string }[];
  modules: string[];
  pages: string[];
}

export interface Session {
  access_token: string;
  expires_in: number;
  user_id: string;
  organization_id: string;
  role: string;
  email: string;
}

export interface ProgressEvent {
  event: string;
  project_id?: string;
  occurred_at?: string;
  payload: Record<string, unknown>;
}
