'use client';

// Despliegues del proyecto: lanzar, seguir y detener.

import { useState } from 'react';

import { ApiError, api } from '@/lib/api';
import type { Deployment } from '@/lib/types';
import { EmptyState, ErrorNote, StatusBadge } from '@/components/ui';

const PROVIDERS = [
  { value: 'docker_local', label: 'Docker local' },
  { value: 'vps_ssh', label: 'VPS por SSH' },
  { value: 'container_registry', label: 'Registro de contenedores' },
];

interface Props {
  projectId: string;
  deployments: Deployment[];
  canDeploy: boolean;
  onChange: (deployments: Deployment[]) => void;
}

export function DeploymentsPanel({ projectId, deployments, canDeploy, onChange }: Props) {
  const [provider, setProvider] = useState(PROVIDERS[0]!.value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => onChange(await api.deployments.list(projectId));

  const deploy = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deployments.create(projectId, { provider });
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido iniciar el despliegue');
    } finally {
      setBusy(false);
    }
  };

  const stop = async (deploymentId: string) => {
    setError(null);
    try {
      await api.deployments.stop(projectId, deploymentId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido detener el despliegue');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="field max-w-56"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          aria-label="Proveedor de despliegue"
        >
          {PROVIDERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button type="button" className="btn-primary" onClick={deploy} disabled={busy || !canDeploy}>
          {busy ? 'Desplegando…' : 'Desplegar'}
        </button>
        {!canDeploy ? (
          <span className="text-xs text-muted">
            Necesitas una construcción completada con éxito.
          </span>
        ) : null}
      </div>

      {error ? <ErrorNote message={error} /> : null}

      {deployments.length === 0 ? (
        <EmptyState title="Sin despliegues" hint="Al desplegar obtendrás una URL funcional." />
      ) : (
        <ul className="space-y-3">
          {deployments.map((deployment) => (
            <li key={deployment.id} className="card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">{deployment.provider}</p>
                  <p className="text-xs text-muted">
                    {new Date(deployment.created_at).toLocaleString('es-ES')}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={deployment.status} />
                  {deployment.status === 'running' ? (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => stop(deployment.id)}
                    >
                      Detener
                    </button>
                  ) : null}
                </div>
              </div>

              {deployment.url ? (
                <a
                  href={deployment.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-block text-sm text-accent underline"
                >
                  {deployment.url}
                </a>
              ) : null}

              {deployment.error ? <ErrorNote message={deployment.error} /> : null}

              {deployment.logs.length ? (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-muted">
                    Registro ({deployment.logs.length} líneas)
                  </summary>
                  <ul className="mt-2 space-y-0.5 text-xs text-muted">
                    {deployment.logs.slice(-15).map((line, index) => (
                      <li key={`${deployment.id}-${index}`}>{line}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
