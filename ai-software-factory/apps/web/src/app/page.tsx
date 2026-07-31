'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { loadSession } from '@/lib/api';

export default function IndexPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(loadSession() ? '/proyectos' : '/acceso');
  }, [router]);

  return <p className="p-10 text-sm text-muted">Redirigiendo…</p>;
}
