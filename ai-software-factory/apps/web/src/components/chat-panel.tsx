'use client';

// Chat con la IA: mensajes, preguntas de aclaración y respuestas.

import { useEffect, useRef, useState } from 'react';

import { ApiError, api } from '@/lib/api';
import type { Conversation } from '@/lib/types';
import { ErrorNote } from '@/components/ui';

interface Props {
  projectId: string;
  conversation: Conversation | null;
  onUpdate: (conversation: Conversation) => void;
}

export function ChatPanel({ projectId, conversation, onUpdate }: Props) {
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation?.messages.length]);

  const run = async (action: () => Promise<Conversation>) => {
    setBusy(true);
    setError(null);
    try {
      onUpdate(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido enviar el mensaje');
    } finally {
      setBusy(false);
    }
  };

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;
    const content = draft;
    setDraft('');
    await run(() => api.conversation.send(projectId, content));
  };

  const answer = (questionId: string, value: string) =>
    run(() => api.conversation.answer(projectId, questionId, value));

  return (
    <div className="card flex h-[32rem] flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {conversation?.messages.length ? (
          conversation.messages.map((message) => (
            <div
              key={message.id}
              className={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
            >
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${
                  message.role === 'user'
                    ? 'bg-accent text-white'
                    : 'border border-line bg-line/20'
                }`}
              >
                {message.content}
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted">
            Cuéntale a la IA qué necesitas. Te preguntará lo que falte antes de construir.
          </p>
        )}
        <div ref={endRef} />
      </div>

      {conversation?.pending_questions.length ? (
        <div className="mt-3 space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
          <p className="text-sm font-medium text-amber-700">
            Preguntas pendientes ({conversation.pending_questions.length})
          </p>
          {conversation.pending_questions.map((question) => (
            <QuestionRow
              key={question.id}
              text={question.text}
              options={question.options}
              disabled={busy}
              onAnswer={(value) => answer(question.id, value)}
            />
          ))}
        </div>
      ) : null}

      {error ? <div className="mt-3">
        <ErrorNote message={error} />
      </div> : null}

      <form onSubmit={send} className="mt-3 flex gap-2">
        <input
          className="field"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Escribe tu mensaje…"
          disabled={busy}
          aria-label="Mensaje"
        />
        <button type="submit" className="btn-primary" disabled={busy || !draft.trim()}>
          {busy ? '…' : 'Enviar'}
        </button>
      </form>
    </div>
  );
}

function QuestionRow({
  text,
  options,
  disabled,
  onAnswer,
}: {
  text: string;
  options: string[];
  disabled: boolean;
  onAnswer: (value: string) => void;
}) {
  const [value, setValue] = useState('');

  return (
    <div className="space-y-2">
      <p className="text-sm">{text}</p>
      {options.length ? (
        <div className="flex flex-wrap gap-2">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(option)}
              className="rounded-full border border-line px-3 py-1 text-xs hover:border-accent hover:text-accent"
            >
              {option}
            </button>
          ))}
        </div>
      ) : null}
      <div className="flex gap-2">
        <input
          className="field"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Tu respuesta"
          disabled={disabled}
          aria-label={text}
        />
        <button
          type="button"
          className="btn-ghost"
          disabled={disabled || !value.trim()}
          onClick={() => {
            onAnswer(value);
            setValue('');
          }}
        >
          Responder
        </button>
      </div>
    </div>
  );
}
