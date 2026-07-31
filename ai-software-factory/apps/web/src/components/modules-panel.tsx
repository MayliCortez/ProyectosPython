'use client';

// Módulos del proyecto: instalar y eliminar respetando las dependencias.

import { useState } from 'react';

import { ApiError, api } from '@/lib/api';
import type { ModuleInstallation, ModuleSummary } from '@/lib/types';
import { ErrorNote } from '@/components/ui';

interface Props {
  projectId: string;
  catalog: ModuleSummary[];
  installed: ModuleInstallation[];
  editable: boolean;
  onChange: (installed: ModuleInstallation[]) => void;
}

export function ModulesPanel({ projectId, catalog, installed, editable, onChange }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const installedKeys = new Set(installed.map((item) => item.module_key));

  const act = async (
    key: string,
    action: () => Promise<{ installed: ModuleInstallation[]; warnings: string[] }>,
  ) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      const result = await action();
      onChange(result.installed);
      if (result.warnings.length) setNotice(result.warnings.join(' · '));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'La operación no se ha podido completar');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      {!editable ? (
        <p className="rounded-lg bg-line/40 px-3 py-2 text-sm text-muted">
          Los módulos no se pueden cambiar mientras el proyecto se construye o se despliega.
        </p>
      ) : null}

      {error ? <ErrorNote message={error} /> : null}
      {notice ? (
        <p className="rounded-lg bg-sky-500/10 px-3 py-2 text-sm text-sky-700">{notice}</p>
      ) : null}

      <ul className="grid gap-3 sm:grid-cols-2">
        {catalog.map((module) => {
          const active = installedKeys.has(module.key);
          return (
            <li key={module.key} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{module.name}</p>
                  <p className="text-xs text-muted">
                    {module.key} · v{module.version}
                  </p>
                </div>
                {active ? (
                  <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-600">
                    Instalado
                  </span>
                ) : null}
              </div>

              <p className="mt-2 text-sm text-muted">{module.description}</p>

              {module.depends_on.length ? (
                <p className="mt-2 text-xs text-muted">
                  Requiere: {module.depends_on.join(', ')}
                </p>
              ) : null}

              <div className="mt-3 flex gap-2">
                {active ? (
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={!editable || !module.removable || busy === module.key}
                    onClick={() =>
                      act(module.key, () => api.modules.remove(projectId, [module.key]))
                    }
                    title={module.removable ? undefined : 'Módulo del núcleo: no se puede eliminar'}
                  >
                    Eliminar
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={!editable || busy === module.key}
                    onClick={() =>
                      act(module.key, () => api.modules.install(projectId, [module.key]))
                    }
                  >
                    Instalar
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
