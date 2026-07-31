'use client';

// Marco del panel: navegación lateral y guardia de sesión.

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { clearSession, loadSession } from '@/lib/api';
import type { Session } from '@/lib/types';

const NAV = [
  { href: '/proyectos', label: 'Proyectos' },
  { href: '/modulos', label: 'Catálogo de módulos' },
];

const PUBLIC_ROUTES = ['/acceso'];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);

  const isPublic = PUBLIC_ROUTES.some((route) => pathname.startsWith(route));

  useEffect(() => {
    const current = loadSession();
    setSession(current);
    setChecked(true);
    if (!current && !isPublic) router.replace('/acceso');
  }, [isPublic, pathname, router]);

  if (!checked) {
    return <div className="p-10 text-sm text-muted">Cargando…</div>;
  }

  if (isPublic || !session) {
    return <main className="min-h-screen">{children}</main>;
  }

  const signOut = () => {
    clearSession();
    router.replace('/acceso');
  };

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 border-r border-line p-5 md:block">
        <Link href="/proyectos" className="block text-sm font-semibold tracking-tight">
          AI Software Factory
        </Link>
        <p className="mt-1 text-xs text-muted">{session.email}</p>

        <nav className="mt-6 flex flex-col gap-1">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-2 text-sm transition ${
                  active ? 'bg-accent/10 text-accent' : 'hover:bg-line/40'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <button type="button" onClick={signOut} className="btn-ghost mt-8 w-full">
          Cerrar sesión
        </button>
      </aside>

      <main className="flex-1 overflow-x-hidden p-6 md:p-10">{children}</main>
    </div>
  );
}
