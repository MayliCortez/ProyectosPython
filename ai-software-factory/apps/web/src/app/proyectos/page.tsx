'use client';

// Dashboard: listado de proyectos y creación desde una descripción en lenguaje natural.

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ApiError, api } from '@/lib/api';
import type { Project } from '@/lib/types';
import { EmptyState, ErrorNote, Section, StatusBadge } from '@/components/ui';

const EXAMPLES = [
  'Necesito un sistema para un gimnasio',
  'Quiero una tienda online con carrito y pagos',
  'Gestión de reservas para un restaurante',
];

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setProjects(await api.projects.list());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se han podido cargar los proyectos');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { project } = await api.projects.create({ name, prompt });
      router.push(`/proyectos/${project.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido crear el proyecto');
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Proyectos</h1>
        <p className="mt-1 text-sm text-muted">
          Describe lo que necesitas; la plataforma pregunta lo que falte y construye el software.
        </p>
      </header>

      <Section title="Nuevo proyecto">
        <form onSubmit={create} className="card space-y-4">
          <div>
            <label className="label" htmlFor="name">
              Nombre
            </label>
            <input
              id="name"
              className="field"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Gimnasio Titán"
              required
              minLength={2}
            />
          </div>

          <div>
            <label className="label" htmlFor="prompt">
              ¿Qué software necesitas?
            </label>
            <textarea
              id="prompt"
              className="field min-h-28 resize-y"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Necesito un sistema para un gimnasio con socios, cuotas y reserva de clases."
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setPrompt(example)}
                  className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-accent hover:text-accent"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>

          {error ? <ErrorNote message={error} /> : null}

          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Creando…' : 'Crear proyecto'}
          </button>
        </form>
      </Section>

      <Section title={`Tus proyectos${projects.length ? ` (${projects.length})` : ''}`}>
        {loading ? (
          <p className="text-sm text-muted">Cargando…</p>
        ) : projects.length === 0 ? (
          <EmptyState
            title="Todavía no hay proyectos"
            hint="Crea el primero describiendo lo que necesitas."
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {projects.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/proyectos/${project.id}`}
                  className="card block transition hover:border-accent"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{project.name}</p>
                      <p className="text-xs text-muted">{project.slug}</p>
                    </div>
                    <StatusBadge status={project.status} />
                  </div>
                  {project.prompt ? (
                    <p className="mt-3 line-clamp-2 text-sm text-muted">{project.prompt}</p>
                  ) : null}
                  <div className="mt-3 flex flex-wrap gap-1">
                    {project.modules.slice(0, 5).map((module) => (
                      <span
                        key={module}
                        className="rounded bg-line/60 px-2 py-0.5 text-xs text-muted"
                      >
                        {module}
                      </span>
                    ))}
                    {project.modules.length > 5 ? (
                      <span className="text-xs text-muted">+{project.modules.length - 5}</span>
                    ) : null}
                  </div>
                  {project.live_url ? (
                    <p className="mt-3 text-xs text-emerald-600">{project.live_url}</p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
