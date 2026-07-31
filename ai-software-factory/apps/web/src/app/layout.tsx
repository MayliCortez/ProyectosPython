import type { Metadata } from 'next';

import './globals.css';
import { Shell } from '@/components/shell';

export const metadata: Metadata = {
  title: 'AI Software Factory',
  description: 'De una conversación a una aplicación desplegada',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
