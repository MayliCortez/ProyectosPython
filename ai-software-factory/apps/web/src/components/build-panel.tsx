'use client';

// Panel de construcción: lanza el pipeline y muestra el progreso en tiempo real.

import { useState } from 'react';

import { ApiError, api } from '@/lib/api';
import type { Build, ProgressEvent } from '@/lib/types';
import { EmptyState, ErrorNote, ProgressBar, StatusBadge } from '@/components/ui';

interface Props {
  projectId: string;
  build: Build | null;
  events: ProgressEvent[];
  connected: boolean;
  onStarted: (build: Build) => void;
}

export function BuildPanel({ projectId, build, events, connected, onStarted }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      onStarted(await api.builds.start(projectId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido lanzar la construcción');
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    if (!build) return;
    try {
      const { url } = await api.builds.download(projectId, build.id);
      window.open(url, '_blank', 'noopener');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'El paquete todavía no está disponible');
    }
  };

  const messages = events
    .filter((event) => event.event === 'build.progressed')
    .map((event) => String(event.payload.message ?? ''))
    .slice(-12);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary" onClick={start} disabled={busy}>
          {busy ? 'Encolando…' : 'Construir proyecto'}
        </button>
        {build?.status === 'succeeded' ? (
          <button type="button" className="btn-ghost" onClick={download}>
            Descargar paquete
          </button>
        ) : null}
        <span className="text-xs text-muted">
          {connected ? 'Conectado al progreso en vivo' : 'Sin conexión en vivo'}
        </span>
      </div>

      {error ? <ErrorNote message={error} /> : null}

      {!build ? (
        <EmptyState
          title="Sin construcciones todavía"
          hint="Cuando no queden preguntas pendientes, lanza la construcción."
        />
      ) : (
        <div className="card space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">Construcción {build.id.slice(0, 8)}</p>
              <p className="text-xs text-muted">
                {build.artifact_count} fichero(s) · {Math.round(build.total_bytes / 1024)} KB
              </p>
            </div>
            <StatusBadge status={build.status} />
          </div>

          <ProgressBar value={build.progress} />

          <ol className="space-y-1.5">
            {build.stages.map((stage) => (
              <li key={stage.name} className="flex items-center justify-between gap-3 text-sm">
                <span className="flex items-center gap-2">
                  <span aria-hidden>{stageIcon(stage.status)}</span>
                  <span className="capitalize">{stage.name.replace(/_/g, ' ')}</span>
                  <span className="text-xs text-muted">{stage.agent}</span>
                </span>
                <span className="text-xs text-muted">
                  {stage.error
                    ? stage.error
                    : stage.duration_seconds !== null
                      ? `${stage.duration_seconds.toFixed(1)} s`
                      : ''}
                </span>
              </li>
            ))}
          </ol>

          {build.error ? <ErrorNote message={build.error} /> : null}

          {messages.length ? (
            <div className="rounded-lg bg-line/30 p-3">
              <p className="mb-1 text-xs font-medium text-muted">Actividad reciente</p>
              <ul className="space-y-0.5 text-xs text-muted">
                {messages.map((message, index) => (
                  <li key={`${message}-${index}`}>{message}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function stageIcon(status: string): string {
  switch (status) {
    case 'succeeded':
      return '✓';
    case 'running':
      return '◐';
    case 'failed':
      return '✗';
    case 'skipped':
      return '–';
    default:
      return '○';
  }
}
