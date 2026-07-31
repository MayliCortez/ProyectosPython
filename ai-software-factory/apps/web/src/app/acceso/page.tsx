'use client';

// Acceso a la plataforma: iniciar sesión o crear una organización nueva.

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, api, saveSession } from '@/lib/api';
import { ErrorNote } from '@/components/ui';

type Mode = 'login' | 'register';

export default function AccessPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [organization, setOrganization] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session =
        mode === 'login'
          ? await api.auth.login({ email, password })
          : await api.auth.register({
              email,
              password,
              organization_name: organization,
              full_name: fullName,
            });
      saveSession(session);
      router.replace('/proyectos');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido completar la operación');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-6">
      <h1 className="text-2xl font-semibold tracking-tight">AI Software Factory</h1>
      <p className="mt-1 text-sm text-muted">
        Describe el software que necesitas y la plataforma lo construye y lo despliega.
      </p>

      <div className="mt-6 flex gap-2">
        {(['login', 'register'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setMode(option)}
            className={mode === option ? 'btn-primary flex-1' : 'btn-ghost flex-1'}
          >
            {option === 'login' ? 'Iniciar sesión' : 'Crear cuenta'}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="card mt-4 space-y-4">
        {mode === 'register' ? (
          <>
            <div>
              <label className="label" htmlFor="organization">
                Organización
              </label>
              <input
                id="organization"
                className="field"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                required
                minLength={2}
              />
            </div>
            <div>
              <label className="label" htmlFor="fullName">
                Tu nombre
              </label>
              <input
                id="fullName"
                className="field"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
          </>
        ) : null}

        <div>
          <label className="label" htmlFor="email">
            Correo electrónico
          </label>
          <input
            id="email"
            type="email"
            className="field"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="label" htmlFor="password">
            Contraseña
          </label>
          <input
            id="password"
            type="password"
            className="field"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
          {mode === 'register' ? (
            <p className="mt-1 text-xs text-muted">Mínimo 8 caracteres.</p>
          ) : null}
        </div>

        {error ? <ErrorNote message={error} /> : null}

        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? 'Enviando…' : mode === 'login' ? 'Entrar' : 'Crear organización'}
        </button>
      </form>
    </div>
  );
}
