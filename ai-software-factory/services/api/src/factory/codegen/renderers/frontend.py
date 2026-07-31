"""Genera el frontend Next.js del proyecto: layout, navegación y páginas CRUD."""

from __future__ import annotations

import json

from factory.codegen.blueprint import Blueprint
from factory.codegen.renderers._common import snake, typescript_type
from factory.domain.entities.specification import DataEntity
from factory.domain.value_objects import Artifact


def render_frontend(blueprint: Blueprint) -> list[Artifact]:
    """Aplicación Next.js con App Router, Tailwind y una página por entidad."""
    artifacts = [
        _package_json(blueprint),
        _tsconfig(),
        _next_config(),
        _tailwind_config(),
        _postcss_config(),
        _globals_css(),
        _types(blueprint),
        _api_client(),
        _layout(blueprint),
        _home(blueprint),
        _sidebar(blueprint),
        _data_table(),
    ]
    artifacts.extend(_entity_page(entity) for entity in blueprint.entities)
    return artifacts


def _package_json(blueprint: Blueprint) -> Artifact:
    dependencies = {
        "next": "^15.0.0",
        "react": "^18.3.1",
        "react-dom": "^18.3.1",
    }
    dependencies.update(dict.fromkeys(blueprint.npm_packages, "latest"))
    manifest = {
        "name": blueprint.slug,
        "version": "1.0.0",
        "private": True,
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
            "typecheck": "tsc --noEmit",
        },
        "dependencies": dependencies,
        "devDependencies": {
            "typescript": "^5.6.0",
            "@types/node": "^22.0.0",
            "@types/react": "^18.3.0",
            "tailwindcss": "^3.4.0",
            "postcss": "^8.4.0",
            "autoprefixer": "^10.4.0",
        },
    }
    return Artifact("frontend/package.json", json.dumps(manifest, indent=2) + "\n", "json")


def _tsconfig() -> Artifact:
    config = {
        "compilerOptions": {
            "target": "ES2022",
            "lib": ["dom", "dom.iterable", "esnext"],
            "strict": True,
            "noEmit": True,
            "esModuleInterop": True,
            "module": "esnext",
            "moduleResolution": "bundler",
            "resolveJsonModule": True,
            "jsx": "preserve",
            "incremental": True,
            "plugins": [{"name": "next"}],
            "paths": {"@/*": ["./src/*"]},
        },
        "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
        "exclude": ["node_modules"],
    }
    return Artifact("frontend/tsconfig.json", json.dumps(config, indent=2) + "\n", "json")


def _next_config() -> Artifact:
    body = """/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
};

export default nextConfig;
"""
    return Artifact("frontend/next.config.mjs", body, "javascript")


def _tailwind_config() -> Artifact:
    body = """import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
};

export default config;
"""
    return Artifact("frontend/tailwind.config.ts", body, "typescript")


def _postcss_config() -> Artifact:
    body = """export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
"""
    return Artifact("frontend/postcss.config.mjs", body, "javascript")


def _globals_css() -> Artifact:
    body = """@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: light dark;
}

body {
  @apply bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100;
}
"""
    return Artifact("frontend/src/app/globals.css", body, "css")


def _types(blueprint: Blueprint) -> Artifact:
    blocks: list[str] = []
    for entity in blueprint.entities:
        fields = "\n".join(
            f"  {f.name}: {typescript_type(f)};" for f in entity.fields if f.name != "id"
        )
        blocks.append(
            f"export interface {entity.name} {{\n  id: number;\n{fields}\n  created_at: string;\n}}"
        )
    body = "// Tipos generados a partir de la especificación.\n\n" + "\n\n".join(blocks) + "\n"
    return Artifact("frontend/src/lib/types.ts", body, "typescript")


def _api_client() -> Artifact:
    body = """// Cliente HTTP tipado contra la API generada.

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const PREFIX = '/api/v1';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${PREFIX}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    cache: 'no-store',
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || response.statusText, response.status);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  list: <T>(resource: string) => request<T[]>(`/${resource}`),
  get: <T>(resource: string, id: number) => request<T>(`/${resource}/${id}`),
  create: <T>(resource: string, payload: unknown) =>
    request<T>(`/${resource}`, { method: 'POST', body: JSON.stringify(payload) }),
  update: <T>(resource: string, id: number, payload: unknown) =>
    request<T>(`/${resource}/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  remove: (resource: string, id: number) =>
    request<void>(`/${resource}/${id}`, { method: 'DELETE' }),
};
"""
    return Artifact("frontend/src/lib/api.ts", body, "typescript")


def _sidebar(blueprint: Blueprint) -> Artifact:
    links = [("/", "Inicio")] + [
        (f"/{entity.table_name}", entity.name) for entity in blueprint.entities
    ]
    for route, title, _ in blueprint.pages:
        if all(route != existing for existing, _ in links):
            links.append((route, title))
    items = ",\n".join(f"  {{ href: '{href}', label: '{label}' }}" for href, label in links)
    body = f"""import Link from 'next/link';

const links = [
{items}
];

export function Sidebar() {{
  return (
    <aside className="w-60 shrink-0 border-r border-slate-200 p-4 dark:border-slate-800">
      <p className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {blueprint.name}
      </p>
      <nav className="flex flex-col gap-1">
        {{links.map((link) => (
          <Link
            key={{link.href}}
            href={{link.href}}
            className="rounded px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            {{link.label}}
          </Link>
        ))}}
      </nav>
    </aside>
  );
}}
"""
    return Artifact("frontend/src/components/sidebar.tsx", body, "typescript")


def _layout(blueprint: Blueprint) -> Artifact:
    body = f"""import type {{ Metadata }} from 'next';
import './globals.css';
import {{ Sidebar }} from '@/components/sidebar';

export const metadata: Metadata = {{
  title: '{blueprint.name}',
  description: 'Generado con AI Software Factory',
}};

export default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{
  return (
    <html lang="es">
      <body>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 p-8">{{children}}</main>
        </div>
      </body>
    </html>
  );
}}
"""
    return Artifact("frontend/src/app/layout.tsx", body, "typescript")


def _home(blueprint: Blueprint) -> Artifact:
    cards = "\n".join(
        f"""        <a
          key="{entity.table_name}"
          href="/{entity.table_name}"
          className="rounded-lg border border-slate-200 p-4
            hover:border-slate-400 dark:border-slate-800"
        >
          <h2 className="font-medium">{entity.name}</h2>
          <p className="text-sm text-slate-500">{entity.description or "Gestión de registros"}</p>
        </a>"""
        for entity in blueprint.entities
    )
    body = f"""export default function HomePage() {{
  return (
    <div>
      <h1 className="text-2xl font-semibold">{blueprint.name}</h1>
      <p className="mt-1 text-slate-500">Panel de administración</p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
{cards}
      </div>
    </div>
  );
}}
"""
    return Artifact("frontend/src/app/page.tsx", body, "typescript")


def _data_table() -> Artifact:
    body = """'use client';

interface DataTableProps<T extends Record<string, unknown>> {
  rows: T[];
  columns: { key: keyof T & string; label: string }[];
}

export function DataTable<T extends Record<string, unknown>>({
  rows,
  columns,
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500">Todavía no hay registros.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-100 text-left dark:bg-slate-900">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="px-4 py-2 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-slate-200 dark:border-slate-800">
              {columns.map((column) => (
                <td key={column.key} className="px-4 py-2">
                  {String(row[column.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
"""
    return Artifact("frontend/src/components/data-table.tsx", body, "typescript")


def _entity_page(entity: DataEntity) -> Artifact:
    columns = ",\n".join(
        f"  {{ key: '{f.name}', label: '{f.name.replace('_', ' ').title()}' }}"
        for f in entity.fields[:6]
    )
    body = f"""import {{ api }} from '@/lib/api';
import type {{ {entity.name} }} from '@/lib/types';
import {{ DataTable }} from '@/components/data-table';

const columns = [
  {{ key: 'id', label: 'ID' }},
{columns}
] as const;

export default async function {entity.name}Page() {{
  const rows = await api.list<{entity.name}>('{entity.table_name}');

  return (
    <div>
      <h1 className="text-xl font-semibold">{entity.name}</h1>
      <p className="mb-4 text-sm text-slate-500">
        {entity.description or f"Registros de {entity.name}"}
      </p>
      <DataTable rows={{rows as unknown as Record<string, unknown>[]}} columns={{[...columns]}} />
    </div>
  );
}}
"""
    return Artifact(f"frontend/src/app/{snake(entity.table_name)}/page.tsx", body, "typescript")
