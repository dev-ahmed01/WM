'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, Loader2, Mic, Square, X } from 'lucide-react';
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder';
import { transcribe, VoiceApiError } from '@/lib/voice';
import { LANGUAGE_LABEL, type Language } from '@/lib/language';
import { cn } from '@/lib/utils';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: (viaVoice: boolean) => void;
  busy: boolean;
  language: Language;
  onLanguageChange: (language: Language) => void;
  placeholder?: string;
}

const BARS = 28;

function Waveform({ level, active }: { level: number; active: boolean }) {
  const [history, setHistory] = useState<number[]>(() => Array(BARS).fill(0.08));
  useEffect(() => {
    if (!active) return;
    setHistory((h) => [...h.slice(1), Math.max(0.08, Math.min(1, level * 3))]);
  }, [level, active]);
  return (
    <div className="flex h-8 flex-1 items-center gap-[3px]" aria-hidden="true">
      {history.map((h, i) => (
        <span key={i} className="w-[3px] rounded-full bg-primary/70 transition-[height] duration-100" style={{ height: `${Math.round(h * 100)}%` }} />
      ))}
    </div>
  );
}

function micGuidance(permission: PermissionState | 'unknown', supported: boolean, secure: boolean): string | null {
  if (!secure) return 'Voice needs a secure page. Open WorkMate with https:// (or at localhost) and try again.';
  if (!supported) return 'This browser cannot record audio. Try Chrome or Edge, or type your question.';
  if (permission === 'denied') return 'Microphone access is blocked. Click the lock icon in the address bar, allow the microphone, then try again.';
  return null;
}

export function AssistantComposer({ value, onChange, onSend, busy, language, onLanguageChange, placeholder }: Props) {
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [heard, setHeard] = useState(false);
  const viaVoiceRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [secure, setSecure] = useState(true);
  useEffect(() => { setSecure(window.isSecureContext); }, []);

  const handleRecording = useCallback(async (blob: Blob) => {
    setTranscribing(true);
    setVoiceError(null);
    try {
      const result = await transcribe(blob, language);
      onChange(result.text);
      viaVoiceRef.current = true;
      setHeard(true);
      requestAnimationFrame(() => textareaRef.current?.focus());
    } catch (cause) {
      setVoiceError(cause instanceof VoiceApiError ? cause.message : 'Could not reach the voice service. You can type your question instead.');
    } finally {
      setTranscribing(false);
    }
  }, [language, onChange]);

  const voice = useVoiceRecorder(handleRecording);
  const guidance = micGuidance(voice.permissionState, voice.isSupported, secure);
  const recording = voice.isListening;
  const canSend = !busy && !transcribing && !recording && value.trim().length > 0;

  const send = () => {
    if (!canSend) return;
    const spoken = viaVoiceRef.current;
    viaVoiceRef.current = false;
    setHeard(false);
    onSend(spoken);
  };

  const error = voiceError || voice.error;

  return (
    <div className="border-t border-border bg-card px-3 pb-3 pt-3 sm:px-6">
      <div className="mx-auto max-w-3xl">
        {error ? <p role="alert" className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}
        {!error && guidance && !recording ? <p className="mb-2 text-xs text-muted-foreground">{guidance}</p> : null}
        {heard && !recording && !transcribing ? <p role="status" className="mb-2 text-xs text-muted-foreground">Check what I heard, fix anything that is wrong, then send.</p> : null}

        <div className={cn('flex items-end gap-2 rounded-2xl border bg-card p-2 transition focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15', recording && 'border-primary')}>
          {recording ? (
            <div className="flex min-h-12 flex-1 items-center gap-3 px-2" role="status" aria-live="polite">
              <span className="h-2.5 w-2.5 flex-none animate-pulse rounded-full bg-red-500" aria-hidden="true" />
              <span className="text-sm font-medium tabular-nums">{Math.floor(voice.recordingSeconds / 60)}:{String(voice.recordingSeconds % 60).padStart(2, '0')}</span>
              <Waveform level={voice.inputLevel} active />
              <span className="hidden text-xs text-muted-foreground sm:inline">Listening… tap stop when you finish</span>
            </div>
          ) : transcribing ? (
            <div className="flex min-h-12 flex-1 items-center gap-2 px-3 text-sm text-muted-foreground" role="status" aria-live="polite">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Turning your voice into text…
            </div>
          ) : (
            <textarea
              ref={textareaRef}
              value={value}
              rows={1}
              aria-label="Message WorkMate"
              placeholder={placeholder ?? 'Ask about your work or a procedure…'}
              onChange={(e) => { onChange(e.target.value); setHeard(false); }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-[15px] text-foreground outline-none placeholder:text-muted-foreground"
              style={{ fieldSizing: 'content' } as React.CSSProperties}
            />
          )}

          {recording ? (
            <>
              <button type="button" onClick={voice.cancelListening} aria-label="Cancel recording"
                className="grid h-11 w-11 flex-none place-items-center rounded-full text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <X className="h-5 w-5" />
              </button>
              <button type="button" onClick={voice.stopListening} aria-label="Stop recording"
                className="grid h-11 w-11 flex-none place-items-center rounded-full bg-red-600 text-white hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                <Square className="h-4 w-4 fill-current" />
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => { setVoiceError(null); voice.toggleListening(); }}
                disabled={busy || transcribing || !secure || !voice.isSupported}
                aria-label={`Speak your question in ${LANGUAGE_LABEL[language]}`} title={guidance ?? `Speak in ${LANGUAGE_LABEL[language]}`}
                className="grid h-11 w-11 flex-none place-items-center rounded-full text-primary hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:text-muted-foreground/60 disabled:hover:bg-transparent">
                <Mic className="h-5 w-5" />
              </button>
              <button type="button" onClick={send} disabled={!canSend} aria-label="Send message"
                className="grid h-11 w-11 flex-none place-items-center rounded-full bg-primary text-primary-foreground transition hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:bg-muted disabled:text-muted-foreground">
                <ArrowUp className="h-5 w-5" />
              </button>
            </>
          )}
        </div>

        <div className="mt-2 flex items-center justify-between gap-3 px-1">
          <div role="group" aria-label="Language" className="inline-flex rounded-full border border-border p-0.5 text-xs">
            {(['en', 'hi'] as Language[]).map((code) => (
              <button key={code} type="button" aria-pressed={language === code} onClick={() => onLanguageChange(code)}
                className={cn('rounded-full px-3 py-1 font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  language === code ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {LANGUAGE_LABEL[code]}
              </button>
            ))}
          </div>
          <p className="hidden text-[11px] text-muted-foreground sm:block">Answers come only from your company’s approved procedures.</p>
        </div>
      </div>
    </div>
  );
}
