import React from 'react';
import { ArrowUp } from 'lucide-react';

interface ChatComposerProps {
  value: string;
  placeholder: string;
  answerMode: 'workflow' | 'reference';
  onAnswerModeChange: (mode: 'workflow' | 'reference') => void;
  busy: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
}

export function ChatComposer({ value, placeholder, answerMode, onAnswerModeChange, busy, onChange, onSend }: ChatComposerProps) {
  return (
    <footer className="border-t border-border/80 bg-white/95 p-3 backdrop-blur-xl sm:p-4">
      <div className="mx-auto max-w-4xl">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-xl border border-border bg-muted/60 p-1" role="group" aria-label="Copilot answer mode">
            <button
              type="button"
              aria-pressed={answerMode === 'workflow'}
              disabled={busy}
              onClick={() => onAnswerModeChange('workflow')}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${answerMode === 'workflow' ? 'bg-white text-emerald-800 shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >SOP guidance</button>
            <button
              type="button"
              aria-pressed={answerMode === 'reference'}
              disabled={busy}
              onClick={() => onAnswerModeChange('reference')}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${answerMode === 'reference' ? 'bg-white text-emerald-800 shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >Ask documents</button>
          </div>
          <span className="text-[11px] text-muted-foreground">{answerMode === 'reference' ? 'Read-only answers from approved sources' : 'Verified procedural steps and workflow progress'}</span>
        </div>
        <div className="rounded-2xl border border-input bg-white p-2 shadow-[0_12px_34px_rgba(15,23,42,0.08)] transition focus-within:border-emerald-400 focus-within:ring-4 focus-within:ring-emerald-100/70">
          <textarea
            rows={2}
            value={value}
            disabled={busy}
            placeholder={placeholder}
            aria-describedby="composer-help"
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                onSend();
              }
            }}
            className="max-h-36 min-h-[3.25rem] w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60"
          />
          <div className="flex items-center justify-between gap-3 border-t border-border/60 pt-2">
            <span id="composer-help" className="text-[10px] text-muted-foreground">
              {answerMode === 'reference' ? 'Answers quote approved department documents. Switch to SOP guidance to complete steps.' : 'Enter to send · Shift + Enter for a new line'}
            </span>
            <button
              type="button"
              onClick={onSend}
              disabled={busy || !value.trim()}
              aria-label="Send message"
              className="grid h-9 w-9 flex-none place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm transition hover:-translate-y-px hover:bg-emerald-700 disabled:translate-y-0 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </footer>
  );
}
