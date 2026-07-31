'use client';

// Piezas visuales compartidas por todo el panel.

import type { ReactNode } from 'react';

const STATUS_TONES: Record<string, string> = {
  draft: 'bg-slate-500/15 text-slate-500',
  gathering_requirements: 'bg-amber-500/15 text-amber-600',
  specified: 'bg-sky-500/15 text-sky-600',
  building: 'bg-indigo-500/15 text-indigo-600',
  built: 'bg-emerald-500/15 text-emerald-600',
  deploying: 'bg-indigo-500/15 text-indigo-600',
  deployed: 'bg-emerald-500/15 text-emerald-600',
  failed: 'bg-rose-500/15 text-rose-600',
  archived: 'bg-slate-500/15 text-slate-500',
  queued: 'bg-slate-500/15 text-slate-500',
  running: 'bg-indigo-500/15 text-indigo-600',
  succeeded: 'bg-emerald-500/15 text-emerald-600',
  pending: 'bg-slate-500/15 text-slate-500',
  skipped: 'bg-slate-500/15 text-slate-400',
  stopped: 'bg-slate-500/15 text-slate-500',
};

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  gathering_requirements: 'Recogiendo requisitos',
  specified: 'Especificado',
  building: 'Construyendo',
  built: 'Construido',
  deploying: 'Desplegando',
  deployed: 'Desplegado',
  failed: 'Con errores',
  archived: 'Archivado',
  queued: 'En cola',
  running: 'En curso',
  succeeded: 'Completado',
  pending: 'Pendiente',
  skipped: 'Omitido',
  stopped: 'Detenido',
  cancelled: 'Cancelado',
  pushing: 'Subiendo',
  starting: 'Arrancando',
};

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONES[status] ?? 'bg-slate-500/15 text-slate-500';
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export function ProgressBar({ value }: { value: number }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-line"
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-accent transition-all duration-500"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line p-8 text-center">
      <p className="font-medium">{title}</p>
      {hint ? <p className="mt-1 text-sm text-muted">{hint}</p> : null}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-600" role="alert">
      {message}
    </p>
  );
}

export function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
