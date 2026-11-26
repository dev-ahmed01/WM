'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ClipboardCopy, Languages, Loader2, ThumbsDown, ThumbsUp, UserRoundPlus, Volume2, VolumeX } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import type { CopilotResponse, SopSuggestion } from '@/lib/api-client';
import { presentCopilotMessage } from '@/lib/copilot-presentation';
import { synthesize, translateToHindi, VoiceApiError } from '@/lib/voice';
import type { Language } from '@/lib/language';
import type { useAudioPlayer } from '@/hooks/useAudioPlayer';
import { cn } from '@/lib/utils';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  copilotData?: CopilotResponse;
  language?: string;
  /** Voice-originated questions are answered aloud when the employee has that switched on. */
  speakWhenReady?: boolean;
}

type Player = ReturnType<typeof useAudioPlayer>;

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  language: Language;
  player: Player;
  conversationId?: string;
  onSelectSop: (suggestion: SopSuggestion, language: string, originalQuery: string) => void;
}

const isNumbered = (line: string) => /^\s*\d+[.)]\s+/.test(line);

/** Plain paragraphs and real numbered lists: steps are scannable, nothing is decorated. */
function AnswerText({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(<ol key={`ol-${blocks.length}`} className="my-2 list-decimal space-y-1.5 pl-5">{list.map((l, i) => <li key={i}>{l.replace(/^\s*\d+[.)]\s+/, '')}</li>)}</ol>);
      list = [];
    }
  };
  text.split('\n').forEach((line) => {
    if (isNumbered(line)) { list.push(line); return; }
    flush();
    if (line.trim()) blocks.push(<p key={`p-${blocks.length}`} className="whitespace-pre-wrap break-words">{line}</p>);
  });
  flush();
  return <div className="space-y-2">{blocks}</div>;
}

function Action({ label, onClick, active, disabled, children }: { label: string; onClick: () => void; active?: boolean; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label} aria-pressed={active}
      className={cn('grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40',
        active && 'bg-accent text-accent-foreground')}>
      {children}
    </button>
  );
}

function AssistantMessage({ message, previousQuestion, language, player, conversationId, busy, onSelectSop }: {
  message: ChatMessage; previousQuestion: string; language: Language; player: Player; conversationId?: string; busy: boolean;
  onSelectSop: Props['onSelectSop'];
}) {
  const data = message.copilotData;
  const presentation = presentCopilotMessage(message.content, { spokenAnswer: data?.spoken_answer, sopDetails: data?.sop_details });
  const isAnswer = Boolean(data?.message_id) && !data?.sop_suggestions?.length;
  const [hindi, setHindi] = useState<{ state: 'idle' | 'loading' | 'ready' | 'error'; text?: string; error?: string }>({ state: 'idle' });
  const [rating, setRating] = useState<'helpful' | 'not_helpful' | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [askNote, setAskNote] = useState('');
  const [ask, setAsk] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const autoSpoke = useRef(false);
  const autoTranslated = useRef(false);

  const loadHindi = async () => {
    if (hindi.text) return hindi.text;
    setHindi({ state: 'loading' });
    try {
      const text = await translateToHindi(presentation.displayText);
      setHindi({ state: 'ready', text });
      return text;
    } catch (cause) {
      setHindi({ state: 'error', error: cause instanceof VoiceApiError ? cause.message : 'Hindi is unavailable right now.' });
      return null;
    }
  };

  const listen = () => {
    if (player.activeId === message.id && player.state !== 'idle') { player.stop(); return; }
    void player.play(message.id, async () => {
      if (language === 'hi') {
        const text = await loadHindi();
        if (!text) throw new Error('Hindi is unavailable right now. The English answer is still correct.');
        return synthesize(text, 'hi');
      }
      return synthesize(presentation.displayText, 'en');
    });
  };

  // With Hindi selected, a new answer is translated in the background (the English answer is already on screen).
  useEffect(() => {
    if (language === 'hi' && isAnswer && !autoTranslated.current && data && message.id !== 'welcome') {
      autoTranslated.current = true;
      void loadHindi();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, isAnswer]);

  useEffect(() => {
    if (message.speakWhenReady && isAnswer && !autoSpoke.current) {
      autoSpoke.current = true;
      listen();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message.speakWhenReady, isAnswer]);

  const copy = async () => {
    try { await navigator.clipboard.writeText(presentation.displayText); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setNote('Copying is blocked by your browser.'); }
  };

  const rate = async (value: 'helpful' | 'not_helpful') => {
    if (!data?.message_id) return;
    setRating(value);
    setNote(null);
    try {
      const result = await apiClient<{ case_id: string | null }>('/copilot/feedback', { method: 'POST', body: JSON.stringify({ message_id: data.message_id, rating: value }) });
      setNote(value === 'helpful' ? 'Thanks — glad that helped.' : result.case_id ? 'Thanks. Your supervisor will review this answer.' : 'Thanks for letting us know.');
    } catch {
      setRating(null);
      setNote('Could not save your feedback. Please try again.');
    }
  };

  const sendAsk = async () => {
    if (!conversationId || !data?.message_id) return;
    setAsk('sending');
    try {
      await apiClient('/copilot/escalate', { method: 'POST', body: JSON.stringify({ conversation_id: conversationId, note: askNote.trim(), message_ids: [data.message_id] }) });
      setAsk('sent');
    } catch {
      setAsk('error');
    }
  };

  const listening = player.activeId === message.id && player.state !== 'idle';

  return (
    <article className="max-w-[min(42rem,100%)]">
      <div className="text-[15px] leading-7 text-foreground">
        <AnswerText text={presentation.displayText} />
        {hindi.state === 'ready' && hindi.text ? (
          <div lang="hi" className="mt-3 rounded-xl border border-border bg-muted/50 px-4 py-3">
            <AnswerText text={hindi.text} />
            <p lang="en" className="mt-2 text-[11px] text-muted-foreground">Machine-translated to Hindi. If anything differs, the English answer above is the approved wording.</p>
          </div>
        ) : null}
        {hindi.state === 'loading' ? <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />Translating to Hindi…</p> : null}
        {hindi.state === 'error' ? <p className="mt-2 text-xs text-muted-foreground">{hindi.error}</p> : null}
      </div>

      {data?.sop_suggestions?.length ? (
        <div className="mt-3 flex flex-wrap gap-2" aria-label="Closest procedures">
          {data.sop_suggestions.map((s) => (
            <button key={s.workflow_code} type="button" disabled={busy}
              onClick={() => onSelectSop(s, message.language || 'en', previousQuestion)}
              className="rounded-xl border border-border bg-card px-3.5 py-2.5 text-left text-sm transition hover:border-primary hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50">
              <span className="block font-medium">{s.title}</span>
              {s.description ? <span className="mt-0.5 block text-xs text-muted-foreground">{s.description}</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      {data?.citations?.length ? (
        <details className="group mt-3">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
            Sources ({data.citations.length})<ChevronDown className="h-3.5 w-3.5 transition group-open:rotate-180" />
          </summary>
          <ul className="mt-2 space-y-2">
            {data.citations.map((c) => (
              <li key={c.chunk_id} className="rounded-lg border border-border px-3 py-2 text-xs">
                <span className="font-medium text-foreground">{c.document_title}</span>
                {c.version_number != null && c.source_type !== 'reference' ? <span className="text-muted-foreground"> · version {c.version_number}</span> : null}
                {c.excerpt ? <p className="mt-1 line-clamp-3 text-muted-foreground">{c.excerpt}</p> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {isAnswer ? (
        <>
          <div className="mt-2 flex flex-wrap items-center gap-0.5 -ml-2">
            <Action label={copied ? 'Copied' : 'Copy answer'} onClick={copy}><ClipboardCopy className="h-4 w-4" /></Action>
            <Action label={listening ? 'Stop listening' : `Listen in ${language === 'hi' ? 'Hindi' : 'English'}`} onClick={listen} active={listening}>
              {player.activeId === message.id && player.state === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : listening ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </Action>
            {language === 'en' && hindi.state === 'idle' ? <Action label="Show in Hindi" onClick={() => void loadHindi()}><Languages className="h-4 w-4" /></Action> : null}
            <Action label="Helpful" onClick={() => void rate('helpful')} active={rating === 'helpful'}><ThumbsUp className="h-4 w-4" /></Action>
            <Action label="Not helpful" onClick={() => void rate('not_helpful')} active={rating === 'not_helpful'}><ThumbsDown className="h-4 w-4" /></Action>
            <Action label="Ask a person" onClick={() => setAskOpen((o) => !o)} active={askOpen}><UserRoundPlus className="h-4 w-4" /></Action>
            {copied ? <span role="status" className="ml-1 text-xs text-muted-foreground">Copied</span> : null}
            {note ? <span role="status" className="ml-2 text-xs text-muted-foreground">{note}</span> : null}
          </div>
          {player.activeId === message.id && player.error ? <p role="alert" className="text-xs text-red-700">{player.error}</p> : null}

          {askOpen ? (
            <div className="mt-2 rounded-xl border border-border bg-muted/40 p-3">
              {ask === 'sent' ? (
                <p role="status" className="text-sm">Request sent. You can follow it under <Link className="font-medium text-primary underline" href="/escalations">Escalations</Link>.</p>
              ) : (
                <>
                  <p className="text-sm font-medium">Ask a person to help</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">Your supervisor will see your question and this answer. Nothing else from the conversation is shared.</p>
                  <textarea value={askNote} onChange={(e) => setAskNote(e.target.value)} rows={2} maxLength={600} aria-label="Add details (optional)"
                    placeholder="Add details (optional)" className="mt-2 w-full resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
                  {ask === 'error' ? <p role="alert" className="mt-1 text-xs text-red-700">Could not send the request. Please try again.</p> : null}
                  <div className="mt-2 flex gap-2">
                    <button type="button" onClick={() => void sendAsk()} disabled={ask === 'sending'}
                      className="rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">{ask === 'sending' ? 'Sending…' : 'Send request'}</button>
                    <button type="button" onClick={() => setAskOpen(false)} className="rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted">Cancel</button>
                  </div>
                </>
              )}
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

export function Messages({ messages, busy, language, player, conversationId, onSelectSop }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: 'smooth' }); }, [messages, busy]);

  return (
    <div ref={ref} className="h-full overflow-y-auto" role="log" aria-live="polite" aria-busy={busy}>
      <div className="mx-auto flex max-w-3xl flex-col gap-7 px-4 py-6 sm:px-6">
        {messages.map((m, i) => m.sender === 'user' ? (
          <div key={m.id} className="flex justify-end">
            <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[15px] leading-6 text-primary-foreground">{m.content}</p>
          </div>
        ) : (
          <AssistantMessage key={m.id} message={m} language={language} player={player} conversationId={conversationId} busy={busy} onSelectSop={onSelectSop}
            previousQuestion={[...messages.slice(0, i)].reverse().find((c) => c.sender === 'user')?.content || ''} />
        ))}
        {busy ? (
          <div className="flex items-center gap-1.5 text-muted-foreground" aria-label="WorkMate is preparing an answer">
            {[0, 1, 2].map((d) => <span key={d} className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary/60" style={{ animationDelay: `${d * 160}ms` }} />)}
            <span className="ml-2 text-sm">Checking your procedures…</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
