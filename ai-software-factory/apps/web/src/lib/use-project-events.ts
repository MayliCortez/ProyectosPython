'use client';

// Suscripción al WebSocket de progreso de un proyecto, con reconexión.

import { useEffect, useRef, useState } from 'react';

import { WS_URL, loadSession } from './api';
import type { ProgressEvent } from './types';

const MAX_EVENTS = 200;
const RECONNECT_MS = 3000;

export interface ProjectEventsState {
  events: ProgressEvent[];
  connected: boolean;
  last: ProgressEvent | null;
}

/**
 * Escucha los eventos del proyecto. Devuelve el histórico reciente y el estado de
 * la conexión; ante un corte reintenta hasta que el componente se desmonta.
 */
export function useProjectEvents(projectId: string | null): ProjectEventsState {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!projectId) return;
    const session = loadSession();
    if (!session) return;

    let closedByUs = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const socket = new WebSocket(
        `${WS_URL}/ws/projects/${projectId}?token=${encodeURIComponent(session.access_token)}`,
      );
      socketRef.current = socket;

      socket.onopen = () => setConnected(true);
      socket.onmessage = (raw) => {
        try {
          const event = JSON.parse(raw.data as string) as ProgressEvent;
          if (event.event === 'heartbeat') return;
          setEvents((current) => [...current, event].slice(-MAX_EVENTS));
        } catch {
          // Un mensaje ilegible no debe romper el flujo de los demás.
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closedByUs) retry = setTimeout(connect, RECONNECT_MS);
      };
      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      closedByUs = true;
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [projectId]);

  return { events, connected, last: events.at(-1) ?? null };
}
