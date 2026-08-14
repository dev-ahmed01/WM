import React, { useEffect, useRef } from 'react';
import { Bot, ChevronDown, CircleAlert, ShieldCheck, Sparkles, Square, UserRound, Volume2 } from 'lucide-react';
import type { CopilotResponse, SopSuggestion } from '@/lib/api-client';
import { presentCopilotMessage } from '@/lib/copilot-presentation';
import { Badge } from '@/components/ui/badge';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  copilotData?: CopilotResponse;
  voiceAudioUrl?: string | null;
  language?: string;
}

interface ChatThreadProps {
  messages: ChatMessage[];
  busy: boolean;
  speechSupported: boolean;
  speakingMessageKey: string | null;
  onSpeak: (text: string, messageKey: string, audioUrl?: string | null, language?: string) => void;
  onSelectSop: (suggestion: SopSuggestion, language: string, originalQuery: string) => void;
}

export function ChatThread({ messages, busy, onSpeak, onSelectSop, speakingMessageKey, speechSupported }: ChatThreadProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  return (
    <div ref={scrollContainerRef} className="h-full min-h-0 overflow-y-auto" role="log" aria-live="polite" aria-busy={busy}>
      <div className="mx-auto flex min-h-full max-w-4xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
        {messages.map((message, messageIndex) => {
          const assistant = message.sender === 'assistant';
          const isSpeaking = speakingMessageKey === message.id;
          const data = message.copilotData;
          const presentation = presentCopilotMessage(message.content, {
            spokenAnswer: data?.spoken_answer,
            sopDetails: data?.sop_details,
          });
          return (
            <article key={message.id} className={`flex gap-3 ${assistant ? 'items-start' : 'items-start justify-end'}`}>
              {assistant ? (
                <span className="mt-0.5 grid h-8 w-8 flex-none place-items-center rounded-xl bg-[#102a22] text-emerald-300 shadow-sm"><Bot className="h-4 w-4" aria-hidden="true" /></span>
              ) : null}
              <div className={`min-w-0 ${assistant ? 'max-w-[min(46rem,calc(100%-2.75rem))]' : 'max-w-[min(38rem,82%)]'}`}>
                <div className={`rounded-2xl px-4 py-3.5 text-[14px] leading-6 sm:px-5 ${assistant ? 'rounded-tl-md border border-border/80 bg-white text-foreground shadow-panel' : 'rounded-tr-md bg-[#123c30] text-white shadow-sm'}`}>
                  <p className="whitespace-pre-wrap break-words">{presentation.displayText}</p>

                  {assistant && data?.sop_suggestions?.length ? (
                    <div className="mt-4 grid gap-2" aria-label="Suggested verified SOPs">
                      {data.sop_suggestions.map((suggestion) => (
                        <button
                          key={suggestion.workflow_code}
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            const originalQuery = [...messages.slice(0, messageIndex)]
                              .reverse()
                              .find((candidate) => candidate.sender === 'user')?.content || '';
                            onSelectSop(suggestion, message.language || 'en', originalQuery);
                          }}
                          className="rounded-xl border border-emerald-200 bg-emerald-50/60 px-3 py-2.5 text-left transition hover:border-emerald-400 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          <span className="block text-xs font-semibold text-emerald-950">{suggestion.title}</span>
                          <span className="mt-0.5 block text-[11px] leading-4 text-emerald-900/70">{suggestion.description}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {assistant && data?.citations?.length ? (
                    <details className="group mt-4 border-t border-border/70 pt-3">
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[11px] font-semibold text-muted-foreground transition hover:text-foreground">
                        <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-emerald-700" />{data.citations.length} verified {data.citations.length === 1 ? 'source' : 'sources'}</span>
                        <ChevronDown className="h-3.5 w-3.5 transition group-open:rotate-180" />
                      </summary>
                      <ul className="mt-3 space-y-2">
                        {data.citations.map((citation) => (
                          <li key={citation.chunk_id} className="rounded-xl bg-muted/70 p-3">
                            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                              <span className="font-semibold text-foreground">{citation.document_title}</span>
                              <span className="text-muted-foreground">v{citation.version_number}</span>
                              {citation.step_number ? <span className="text-muted-foreground">· state {citation.step_number}</span> : null}
                            </div>
                            {citation.excerpt ? <p className="mt-1.5 line-clamp-2 text-[10px] leading-4 text-muted-foreground">{citation.excerpt}</p> : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}

                  {assistant && presentation.sopDetails ? (
                    <div className="mt-3 border-t border-border/70 pt-3 text-[10px] leading-4 text-muted-foreground">
                      <span className="font-semibold text-foreground/80">SOP details</span>
                      <span className="ml-1.5">{presentation.sopDetails}</span>
                    </div>
                  ) : null}
                </div>

                {assistant ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2 px-1">
                    {data ? (
                      <>
                        <Badge variant={data.is_grounded ? 'default' : 'warning'}>
                          {data.is_grounded ? <ShieldCheck className="h-3 w-3" /> : <CircleAlert className="h-3 w-3" />}
                          {data.is_grounded ? 'Grounded' : 'Needs review'}
                        </Badge>
                        <Badge variant="neutral">{Math.round(data.confidence_score * 100)}% confidence</Badge>
                        {data.requires_escalation ? <Badge variant="danger"><CircleAlert className="h-3 w-3" />Escalated</Badge> : null}
                      </>
                    ) : null}
                    {speechSupported ? (
                      <button type="button" onClick={() => onSpeak(presentation.spokenText, message.id, message.voiceAudioUrl, message.language)} aria-label={isSpeaking ? 'Stop reading this response' : 'Listen to this response'} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground">
                        {isSpeaking ? <Square className="h-3 w-3" /> : <Volume2 className="h-3.5 w-3.5" />}
                        {isSpeaking ? 'Stop' : 'Listen'}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {!assistant ? <span className="mt-0.5 grid h-8 w-8 flex-none place-items-center rounded-xl border bg-white text-muted-foreground"><UserRound className="h-4 w-4" aria-hidden="true" /></span> : null}
            </article>
          );
        })}

        {busy ? (
          <div className="flex items-start gap-3" aria-label="WorkMate is preparing a response">
            <span className="grid h-8 w-8 flex-none place-items-center rounded-xl bg-[#102a22] text-emerald-300"><Sparkles className="h-4 w-4" /></span>
            <div className="flex items-center gap-1 rounded-2xl rounded-tl-md border bg-white px-4 py-4 shadow-panel">
              {[0, 1, 2].map((dot) => <span key={dot} className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-600" style={{ animationDelay: `${dot * 160}ms` }} />)}
              <span className="ml-2 text-xs text-muted-foreground">Checking verified guidance…</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
