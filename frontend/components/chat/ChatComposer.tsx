import React from 'react';
import { ArrowUp, Mic, MicOff } from 'lucide-react';
import type { VoiceLanguage } from '@/lib/api-client';

const VOICE_LANGUAGES: Array<{ value: VoiceLanguage; label: string }> = [
  { value: 'auto', label: 'Auto Detect' },
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'हिन्दी · Hindi' },
  { value: 'kn', label: 'ಕನ್ನಡ · Kannada' },
  { value: 'ta', label: 'தமிழ் · Tamil' },
  { value: 'te', label: 'తెలుగు · Telugu' },
  { value: 'ml', label: 'മലയാളം · Malayalam' },
];

interface ChatComposerProps {
  value: string;
  placeholder: string;
  busy: boolean;
  listening: boolean;
  speechSupported: boolean;
  speechError: string | null;
  voiceLanguage: VoiceLanguage;
  detectedLanguage?: string;
  transcriptPreview?: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onToggleListening: () => void;
  onVoiceLanguageChange: (language: VoiceLanguage) => void;
}

export function ChatComposer({
  value, placeholder, busy, listening, speechSupported, speechError,
  voiceLanguage, detectedLanguage, transcriptPreview, onChange, onSend,
  onToggleListening, onVoiceLanguageChange,
}: ChatComposerProps) {
  return (
    <footer className="border-t border-border/80 bg-white/95 p-3 backdrop-blur-xl sm:p-4">
      <div className="mx-auto max-w-4xl">
        <div className="rounded-2xl border border-input bg-white p-2 shadow-[0_12px_34px_rgba(15,23,42,0.08)] transition focus-within:border-emerald-400 focus-within:ring-4 focus-within:ring-emerald-100/70">
          <textarea
            rows={2}
            value={value}
            disabled={busy}
            placeholder={placeholder}
            aria-describedby="composer-help voice-input-status"
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
            <div className="flex min-w-0 items-center gap-2">
              <button
                type="button"
                onClick={onToggleListening}
                disabled={busy || !speechSupported}
                aria-label={!speechSupported ? 'Voice input is not supported in this browser' : listening ? 'Stop voice input' : 'Start voice input'}
                aria-pressed={listening}
                className={`grid h-9 w-9 flex-none place-items-center rounded-xl transition disabled:cursor-not-allowed disabled:opacity-35 ${listening ? 'bg-red-50 text-red-700 ring-1 ring-red-200' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
              >
                {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <label>
                <span className="sr-only">Voice language</span>
                <select
                  value={voiceLanguage}
                  disabled={busy || listening}
                  onChange={(event) => onVoiceLanguageChange(event.target.value as VoiceLanguage)}
                  className="h-9 max-w-40 rounded-xl border border-border bg-muted/50 px-2 text-[11px] font-medium text-foreground outline-none transition focus:border-emerald-500 disabled:opacity-50"
                >
                  {VOICE_LANGUAGES.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </label>
              <span id="composer-help" className="hidden text-[10px] text-muted-foreground sm:block">Enter to send · Shift + Enter for a new line</span>
            </div>
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
        <div id="voice-input-status" aria-live="polite" className={`min-h-5 px-2 pt-1.5 text-[10px] ${speechError ? 'text-red-600' : 'text-muted-foreground'}`}>
          {speechError || (listening
            ? 'Recording securely… select the microphone again when you finish.'
            : transcriptPreview
              ? `Transcript preview${detectedLanguage ? ` · ${detectedLanguage.toUpperCase()}` : ''}: ${transcriptPreview}`
              : 'Voice questions are transcribed locally and receive grounded spoken replies.')}
        </div>
      </div>
    </footer>
  );
}
