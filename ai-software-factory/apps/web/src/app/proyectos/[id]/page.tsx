'use client';

// Editor de proyecto: chat, construcción, módulos, especificación y despliegues.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { ApiError, api } from '@/lib/api';
import { useProjectEvents } from '@/lib/use-project-events';
import type {
  Build,
  Conversation,
  Deployment,
  ModuleInstallation,
  ModuleSummary,
  Project,
  Specification,
} from '@/lib/types';
import { BuildPanel } from '@/components/build-panel';
import { ChatPanel } from '@/components/chat-panel';
import { DeploymentsPanel } from '@/components/deployments-panel';
import { ModulesPanel } from '@/components/modules-panel';
import { ErrorNote, StatusBadge } from '@/components/ui';

const TABS = [
  { key: 'chat', label: 'Chat' },
  { key: 'build', label: 'Construcción' },
  { key: 'modules', label: 'Módulos' },
  { key: 'spec', label: 'Especificación' },
  { key: 'deploy', label: 'Despliegues' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

//: Eventos tras los cuales conviene releer el estado del servidor.
const REFRESH_ON = new Set([
  'build.succeeded',
  'build.failed',
  'build.stage_completed',
  'deployment.succeeded',
  'deployment.failed',
]);

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [tab, setTab] = useState<TabKey>('chat');
  const [project, setProject] = useState<Project | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [build, setBuild] = useState<Build | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [catalog, setCatalog] = useState<ModuleSummary[]>([]);
  const [installed, setInstalled] = useState<ModuleInstallation[]>([]);
  const [specification, setSpecification] = useState<Specification | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { events, connected, last } = useProjectEvents(projectId);

  const load = useCallback(async () => {
    try {
      const [projectData, conversationData, builds, deploymentsData, installedData] =
        await Promise.all([
          api.projects.get(projectId),
          api.conversation.get(projectId).catch(() => null),
          api.builds.list(projectId).catch(() => []),
          api.deployments.list(projectId).catch(() => []),
          api.modules.installed(projectId).catch(() => []),
        ]);
      setProject(projectData);
      setConversation(conversationData);
      setBuild(builds[0] ?? null);
      setDeployments(deploymentsData);
      setInstalled(installedData);
      // La especificación solo existe tras una construcción correcta.
      setSpecification(await api.projects.specification(projectId).catch(() => null));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido cargar el proyecto');
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api.modules.catalog().then(setCatalog).catch(() => setCatalog([]));
  }, []);

  useEffect(() => {
    if (last && REFRESH_ON.has(last.event)) void load();
  }, [last, load]);

  const canDeploy = useMemo(
    () => build?.status === 'succeeded' && Boolean(build.bundle_key),
    [build],
  );
  const editable = Boolean(
    project && !['building', 'deploying', 'archived'].includes(project.status),
  );

  if (error) return <ErrorNote message={error} />;
  if (!project) return <p className="text-sm text-muted">Cargando proyecto…</p>;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {project.business_domain} · {project.modules.length} módulo(s)
          </p>
          {project.live_url ? (
            <a
              href={project.live_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-sm text-accent underline"
            >
              {project.live_url}
            </a>
          ) : null}
        </div>
        <StatusBadge status={project.status} />
      </header>

      <nav className="flex flex-wrap gap-2 border-b border-line pb-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`rounded-lg px-3 py-1.5 text-sm transition ${
              tab === item.key ? 'bg-accent/10 text-accent' : 'text-muted hover:bg-line/40'
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === 'chat' ? (
        <ChatPanel
          projectId={projectId}
          conversation={conversation}
          onUpdate={(updated) => {
            setConversation(updated);
            void load();
          }}
        />
      ) : null}

      {tab === 'build' ? (
        <BuildPanel
          projectId={projectId}
          build={build}
          events={events}
          connected={connected}
          onStarted={(started) => {
            setBuild(started);
            void load();
          }}
        />
      ) : null}

      {tab === 'modules' ? (
        <ModulesPanel
          projectId={projectId}
          catalog={catalog}
          installed={installed}
          editable={editable}
          onChange={(updated) => {
            setInstalled(updated);
            void load();
          }}
        />
      ) : null}

      {tab === 'spec' ? <SpecificationView specification={specification} /> : null}

      {tab === 'deploy' ? (
        <DeploymentsPanel
          projectId={projectId}
          deployments={deployments}
          canDeploy={canDeploy}
          onChange={(updated) => {
            setDeployments(updated);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function SpecificationView({ specification }: { specification: Specification | null }) {
  if (!specification) {
    return (
      <p className="text-sm text-muted">
        La especificación técnica aparece cuando termina la primera construcción.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="card">
        <p className="text-sm font-medium">Pila tecnológica (v{specification.version})</p>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          {Object.entries(specification.tech_stack).map(([layer, value]) => (
            <div key={layer}>
              <dt className="text-xs text-muted">{layer}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Entidades ({specification.entities.length})</h2>
        {specification.entities.map((entity) => (
          <div key={entity.name} className="card">
            <p className="font-medium">
              {entity.name} <span className="text-xs text-muted">{entity.table}</span>
            </p>
            {entity.description ? (
              <p className="text-sm text-muted">{entity.description}</p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-1">
              {entity.fields.map((field) => (
                <span
                  key={field.name}
                  className="rounded bg-line/60 px-2 py-0.5 text-xs text-muted"
                >
                  {field.name}: {field.type}
                  {field.required ? '' : '?'}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Endpoints ({specification.endpoints.length})</h2>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-line/30 text-left">
              <tr>
                <th className="px-3 py-2 font-medium">Método</th>
                <th className="px-3 py-2 font-medium">Ruta</th>
                <th className="px-3 py-2 font-medium">Descripción</th>
              </tr>
            </thead>
            <tbody>
              {specification.endpoints.map((endpoint) => (
                <tr key={`${endpoint.method}-${endpoint.path}`} className="border-t border-line">
                  <td className="px-3 py-2 font-mono text-xs">{endpoint.method}</td>
                  <td className="px-3 py-2 font-mono text-xs">{endpoint.path}</td>
                  <td className="px-3 py-2 text-muted">{endpoint.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
