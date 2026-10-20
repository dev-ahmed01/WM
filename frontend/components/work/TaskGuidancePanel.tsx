'use client';

import { useEffect, useRef, useState } from 'react';
import { BookOpenText, ChevronDown, Mic, MicOff, MessageSquareText, Send, ShieldAlert, X } from 'lucide-react';
import { apiClient, type VoiceLanguage, type VoiceTranscriptPreview } from '@/lib/api-client';
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder';

type Answer = {
  answer: string; status: string; read_only: boolean; requires_supervisor: boolean;
  reference_grounded?: boolean; workflow_version_id: string | null;
  citations: Array<{
    source_type: 'published_sop' | 'approved_reference';
    workflow_version_id?: string; state_id?: string; step_id?: string;
    document_id?: string; document_title?: string; chunk_id?: string; excerpt: string;
  }>;
};
type Intent = 'current_step' | 'evidence' | 'exception' | 'ask';
type Props = {workId: string; status: string; workflowVersionId: string | null; stepId: string | null};

const actions: {intent: Intent; label: string}[] = [
  {intent: 'current_step', label: 'Explain this step'},
  {intent: 'evidence', label: 'What evidence is required?'},
  {intent: 'exception', label: 'Something is wrong'},
];
const VOICE_MAX_BYTES = 24 * 1024 * 1024; // Under the authenticated 26 MB proxy and the 25 MB API cap.

function audioFilename(blob: Blob): string {
  if (blob.type.includes('mp4')) return 'workmate-task.m4a';
  if (blob.type.includes('ogg')) return 'workmate-task.ogg';
  return 'workmate-task.webm';
}

export function TaskGuidancePanel({workId, status, workflowVersionId, stepId}: Props) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguage>('auto');
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [preview, setPreview] = useState<VoiceTranscriptPreview | null>(null);
  const [reviewText, setReviewText] = useState('');

  // Both requests are invalidated when the task, SOP, checkpoint or page changes.
  // This also protects against a late response from an earlier recording.
  const contextKey = [workId, workflowVersionId || '', stepId || '', status].join('|');
  const liveContext = useRef(contextKey);
  liveContext.current = contextKey;
  const panelOpen = useRef(open);
  panelOpen.current = open;
  const voiceSerial = useRef(0);
  const answerSerial = useRef(0);
  const voiceInFlight = useRef(false);
  const answerInFlight = useRef(false);
  const voiceAbort = useRef<AbortController | null>(null);

  async function transcribe(audio: Blob) {
    if (!panelOpen.current || voiceInFlight.current) return;
    const key = liveContext.current;
    const seq = ++voiceSerial.current;
    if (!audio.size || audio.size > VOICE_MAX_BYTES) {
      setError('Recording is empty or too large. Try a shorter question.');
      return;
    }
    voiceInFlight.current = true;
    setVoiceBusy(true);
    setPreview(null);
    setReviewText('');
    setError('');
    const controller = new AbortController();
    voiceAbort.current = controller;
    try {
      const form = new FormData();
      form.append('audio', audio, audioFilename(audio));
      form.append('language', voiceLanguage);
      // Only this read-only transcription endpoint; NEVER /copilot/voice or /copilot/message.
      const transcript = await apiClient<VoiceTranscriptPreview>('/copilot/voice/transcribe', {
        method: 'POST', body: form, signal: controller.signal,
      });
      if (seq !== voiceSerial.current || key !== liveContext.current || !panelOpen.current) return;
      if (!transcript.requires_confirmation || !transcript.suggested_text.trim()) {
        throw new Error('No usable transcription was returned. Please record again or type your question.');
      }
      setPreview(transcript);
      setReviewText(transcript.suggested_text);
    } catch (caught) {
      if (seq === voiceSerial.current && key === liveContext.current && !controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : 'Transcription failed. Please type your question.');
      }
    } finally {
      if (seq === voiceSerial.current) {
        voiceInFlight.current = false;
        voiceAbort.current = null;
        setVoiceBusy(false);
      }
    }
  }

  const recorder = useVoiceRecorder(transcribe);

  function discardVoice() {
    voiceSerial.current += 1;
    voiceAbort.current?.abort();
    voiceAbort.current = null;
    voiceInFlight.current = false;
    setVoiceBusy(false);
    setPreview(null);
    setReviewText('');
    recorder.cancelListening();
  }

  useEffect(() => {
    answerSerial.current += 1;
    answerInFlight.current = false;
    setBusy(false);
    setResult(null);
    setQuestion('');
    setError('');
    voiceSerial.current += 1;
    voiceAbort.current?.abort();
    voiceAbort.current = null;
    voiceInFlight.current = false;
    setVoiceBusy(false);
    setPreview(null);
    setReviewText('');
    recorder.cancelListening();
    return () => {
      answerSerial.current += 1;
      voiceSerial.current += 1;
      voiceAbort.current?.abort();
      recorder.cancelListening();
    };
  }, [contextKey, recorder.cancelListening]);

  async function ask(intent: Intent) {
    if (answerInFlight.current || (intent === 'ask' && question.trim().length < 4)) return;
    discardVoice(); // A text action must never also submit a recording.
    const key = liveContext.current;
    const seq = ++answerSerial.current;
    answerInFlight.current = true;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const response = await apiClient<Answer>('/work/guidance/' + encodeURIComponent(workId), {
        method: 'POST',
        body: JSON.stringify({intent, question: intent === 'ask' ? question.trim() : ''}),
      });
      if (seq !== answerSerial.current || key !== liveContext.current) return;
      if (response.workflow_version_id !== workflowVersionId) {
        throw new Error('The published procedure changed. Refresh this task before relying on guidance.');
      }
      setResult(response);
    } catch (caught) {
      if (seq === answerSerial.current && key === liveContext.current) {
        setError(caught instanceof Error ? caught.message : 'No source-grounded guidance could be retrieved.');
      }
    } finally {
      if (seq === answerSerial.current) {
        answerInFlight.current = false;
        setBusy(false);
      }
    }
  }

  function confirmTranscript() {
    const edited = reviewText.trim();
    if (!preview || edited.length < 4 || edited.length > 500) return;
    // A separate explicit Ask is still required. Voice never executes a step.
    setQuestion(edited);
    setPreview(null);
    setReviewText('');
    setError('');
  }

  function togglePanel() {
    if (open) discardVoice();
    setOpen(previous => !previous);
  }

  return <section className="overflow-hidden rounded-[1.4rem] border border-[#d5e5d7] bg-[#f6faf6]">
    <button type="button" aria-expanded={open} aria-controls={'task-guidance-' + workId}
      className="flex w-full items-center justify-between gap-3 p-4 text-left sm:p-5"
      onClick={togglePanel}>
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e5f2e7] text-emerald-900">
          <MessageSquareText className="h-5 w-5"/>
        </span>
        <div>
          <h3 className="text-sm font-semibold text-[#245036]">Ask about this task</h3>
          <p className="mt-0.5 text-[11px] text-[#657d6a]">Current SOP · approved sources · voice or text</p>
        </div>
      </div>
      <ChevronDown className={'h-4 w-4 text-[#61816b] transition-transform ' + (open ? 'rotate-180' : '')}/>
    </button>
    {open ? <div id={'task-guidance-' + workId} className="space-y-4 border-t border-[#e0ebdf] p-4 sm:p-5">
      <div className="flex flex-wrap gap-2">
        {actions.map(action => <button type="button" key={action.intent} disabled={busy}
          onClick={() => void ask(action.intent)}
          className="min-h-9 rounded-xl border border-[#cce0d0] bg-white px-3 text-[11px] font-semibold text-[#305b3b] disabled:opacity-50">{action.label}</button>)}
      </div>
      <form className="flex items-end gap-2" onSubmit={event => {event.preventDefault(); void ask('ask');}}>
        <div className="min-w-0 flex-1">
          <label htmlFor={'task-question-' + workId} className="wm-label">Question about this task</label>
          <textarea id={'task-question-' + workId} maxLength={500} rows={2}
            className="wm-input mt-1 min-h-16 bg-white" value={question}
            onChange={event => setQuestion(event.target.value)}
            placeholder="How should damaged cartons be documented?"/>
        </div>
        <button type="submit" aria-label="Ask task question" disabled={busy || question.trim().length < 4}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#155a40] text-white disabled:opacity-50">
          <Send className="h-4 w-4"/>
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-label={recorder.isListening ? 'Stop recording question' : 'Record task question'}
          aria-pressed={recorder.isListening} disabled={!recorder.isSupported || voiceBusy || busy}
          onClick={() => {
            if (!recorder.isListening) {
              setError('');
              setPreview(null);
              setReviewText('');
            }
            recorder.toggleListening();
          }}
          className={'flex min-h-10 items-center gap-2 rounded-xl border px-3 text-xs font-semibold disabled:opacity-50 ' +
            (recorder.isListening ? 'border-amber-400 bg-amber-50 text-amber-900' : 'border-[#cce0d0] bg-white text-[#245036]')}>
          {recorder.isListening ? <MicOff className="h-4 w-4"/> : <Mic className="h-4 w-4"/>}
          {recorder.isListening ? 'Stop recording' : 'Speak question'}
        </button>
        <label htmlFor={'task-voice-language-' + workId} className="text-xs text-[#54705c]">Language</label>
        <select id={'task-voice-language-' + workId} value={voiceLanguage}
          onChange={event => setVoiceLanguage(event.target.value as VoiceLanguage)}
          disabled={recorder.isListening || voiceBusy} aria-label="Voice language"
          className="min-h-10 rounded-xl border border-[#cce0d0] bg-white px-2 text-xs text-[#245036] disabled:opacity-50">
          <option value="auto">Auto · Hinglish</option>
          <option value="en">English</option>
          <option value="hi">हिन्दी</option>
        </select>
        {recorder.isListening ? <span role="status" className="text-xs text-amber-900">
          Listening · {Math.floor(recorder.recordingSeconds)}s · level {Math.round(recorder.inputLevel * 100)}%
        </span> : null}
        {voiceBusy ? <span role="status" className="text-xs text-[#51725a]">Transcribing · no question sent</span> : null}
      </div>
      {!recorder.isSupported ? <p className="text-xs text-[#667e6b]">Microphone unavailable. You can still type your question.</p> : null}
      {recorder.error ? <p role="alert" className="text-xs text-red-800">{recorder.error}</p> : null}
      {preview ? <div className="space-y-3 rounded-xl border border-[#cce0d0] bg-white p-3" aria-label="Voice transcript review">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-[#245036]">Review what was heard</p>
          <button type="button" onClick={discardVoice} aria-label="Discard voice transcript" className="rounded-lg p-1.5 text-[#53745b]"><X className="h-4 w-4"/></button>
        </div>
        <p className="text-[11px] text-[#6a806e]">Original · {preview.detected_language === 'hi' ? 'Hindi / mixed' : 'English / mixed'}</p>
        <p className="whitespace-pre-wrap break-words text-sm text-[#334e3b]">{preview.transcript}</p>
        <label htmlFor={'task-voice-review-' + workId} className="wm-label">Editable question · suggested English</label>
        <textarea id={'task-voice-review-' + workId} rows={2} maxLength={500}
          className="wm-input min-h-16 bg-white" value={reviewText}
          onChange={event => setReviewText(event.target.value)}/>
        {preview.confidence < 0.75 ? <p className="text-xs text-amber-800">Speech recognition is uncertain. Clarify the wording before using it.</p> : null}
        <p className="text-[11px] leading-5 text-[#6b7f6e]">Check negation, numbers, units, equipment codes and safety words. This is a transcription suggestion, not an instruction.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={confirmTranscript}
            disabled={reviewText.trim().length < 4 || reviewText.trim().length > 500}
            className="min-h-10 rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">
            Use this question
          </button>
          <button type="button" onClick={() => setReviewText(preview.transcript)}
            className="min-h-10 rounded-xl border border-[#cce0d0] px-3 text-xs text-[#245036]">Use original words</button>
        </div>
      </div> : null}

      {busy ? <p role="status" className="text-xs text-[#68806b]">Checking the current procedure and approved references…</p> : null}
      {error ? <p role="alert" className="rounded-xl bg-red-50 p-3 text-xs text-red-800">{error}</p> : null}
      {result ? <article aria-live="polite" className="rounded-xl border border-[#d3e5d6] bg-white p-4">
        <div className="flex items-center gap-2">
          {result.requires_supervisor ? <ShieldAlert className="h-4 w-4 text-amber-700"/> : <BookOpenText className="h-4 w-4 text-emerald-700"/>}
          <p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#52775d]">{result.requires_supervisor ? 'Supervisor guidance required' : 'Source-linked guidance'}</p>
        </div>
        <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-[#304a36]">{result.answer}</p>
        {result.citations.length ? <div className="mt-4 space-y-2 border-t border-[#edf2ec] pt-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#67826b]">Verified source</p>
          {result.citations.map((citation, index) => <div key={citation.chunk_id || citation.step_id || index}
            className="rounded-lg bg-[#f5f9f5] px-3 py-2">
            <p className="text-[11px] font-semibold text-[#316142]">{citation.source_type === 'published_sop'
              ? 'Current SOP · state ' + (citation.state_id || '') : citation.document_title}</p>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-[#67806d]">{citation.excerpt}</p>
          </div>)}
        </div> : null}
        <p className="mt-3 text-[11px] leading-5 text-[#788c79]">Read-only guidance. No step, evidence requirement, decision or approval was recorded.</p>
      </article> : null}
      <p className="text-[11px] leading-5 text-[#7b8d7d]">If anything is unsafe or unclear, stop and use the task’s reporting controls. Voice cannot skip steps or release a hold.</p>
    </div> : null}
  </section>;
}
