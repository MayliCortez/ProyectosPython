'use client';

// Catálogo global de módulos reutilizables.

import { useEffect, useMemo, useState } from 'react';

import { api } from '@/lib/api';
import type { ModuleSummary } from '@/lib/types';
import { EmptyState } from '@/components/ui';

const CATEGORY_LABELS: Record<string, string> = {
  core: 'Núcleo',
  operations: 'Operaciones',
  commerce: 'Comercio',
  engagement: 'Comunicación',
  intelligence: 'Inteligencia',
  platform: 'Plataforma',
};

export default function CatalogPage() {
  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.modules
      .catalog()
      .then(setModules)
      .finally(() => setLoading(false));
  }, []);

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? modules.filter(
          (module) =>
            module.key.includes(needle) ||
            module.name.toLowerCase().includes(needle) ||
            module.description.toLowerCase().includes(needle),
        )
      : modules;

    return filtered.reduce<Record<string, ModuleSummary[]>>((accumulator, module) => {
      (accumulator[module.category] ??= []).push(module);
      return accumulator;
    }, {});
  }, [modules, query]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Catálogo de módulos</h1>
        <p className="mt-1 text-sm text-muted">
          Piezas reutilizables que se combinan en cada proyecto. Instalar uno arrastra sus
          dependencias; eliminarlo solo es posible si nadie depende de él.
        </p>
      </header>

      <input
        className="field max-w-sm"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Buscar módulo…"
        aria-label="Buscar módulo"
      />

      {loading ? <p className="text-sm text-muted">Cargando…</p> : null}

      {!loading && Object.keys(grouped).length === 0 ? (
        <EmptyState title="Sin resultados" hint="Prueba con otro término de búsqueda." />
      ) : null}

      {Object.entries(grouped).map(([category, items]) => (
        <section key={category} className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
            {CATEGORY_LABELS[category] ?? category}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {items.map((module) => (
              <li key={module.key} className="card">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium">{module.name}</p>
                  <span className="text-xs text-muted">v{module.version}</span>
                </div>
                <p className="mt-1 text-sm text-muted">{module.description}</p>

                <dl className="mt-3 space-y-1 text-xs text-muted">
                  {module.depends_on.length ? (
                    <div>
                      <dt className="inline font-medium">Depende de: </dt>
                      <dd className="inline">{module.depends_on.join(', ')}</dd>
                    </div>
                  ) : null}
                  {module.tables.length ? (
                    <div>
                      <dt className="inline font-medium">Tablas: </dt>
                      <dd className="inline">{module.tables.join(', ')}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt className="inline font-medium">Endpoints: </dt>
                    <dd className="inline">{module.endpoints}</dd>
                  </div>
                  {module.removable ? null : (
                    <div className="text-amber-600">Módulo del núcleo: no se puede eliminar</div>
                  )}
                </dl>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
