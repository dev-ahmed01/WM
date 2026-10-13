'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';

type Surface = 'reference' | 'workflow' | 'voice';
type Issue = 'incorrect_guidance' | 'missing_evidence' | 'unsafe_step' | 'voice_transcript' | 'other';
const ISSUE_LABELS: Record<Issue, string> = {
  incorrect_guidance: 'Guidance incorrect',
  missing_evidence: 'Missing citation',
  unsafe_step: 'Unsafe instruction',
  voice_transcript: 'Voice transcription',
  other: 'Other issue',
};

export function PilotFeedback({ messageId, surface }: { messageId: string; surface: Surface }) {
  const [open, setOpen] = useState(false);
  const [issue, setIssue] = useState<Issue>('incorrect_guidance');
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setOpen(false);
    setBusy(false);
    setComplete(false);
    setError('');
    setIssue('incorrect_guidance');
  }, [messageId]);

  const submit = async (verdict: 'helpful' | 'needs_review') => {
    if (busy || complete) return;
    setBusy(true);
    setError('');
    try {
      await apiClient('/pilot/feedback', {
        method: 'POST',
        body: JSON.stringify({
          surface,
          verdict,
          issue: verdict === 'helpful' ? 'none' : issue,
        }),
      });
      setComplete(true);
      setOpen(false);
    } catch {
      setError('Feedback could not be saved. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside aria-label="Pilot feedback" className="border-t border-emerald-100 bg-emerald-50/40 px-4 py-2.5 text-xs sm:px-6">
      {complete ? (
        <p role="status" className="font-medium text-emerald-800">Feedback saved. Thank you for reviewing the guidance.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-slate-600">Pilot · Was this guidance useful?</span>
          <button type="button" disabled={busy} onClick={() => void submit('helpful')}
            className="rounded-lg border border-emerald-200 bg-white px-2.5 py-1.5 font-semibold text-emerald-800 hover:bg-emerald-50 disabled:opacity-50">
            Helpful
          </button>
          <button type="button" disabled={busy} onClick={() => setOpen(value => !value)}
            aria-expanded={open}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            Needs review
          </button>
          {open ? (
            <div className="flex w-full flex-wrap items-center gap-2">
              <label htmlFor="pilot-issue" className="text-slate-600">Issue</label>
              <select id="pilot-issue" value={issue} onChange={event => setIssue(event.target.value as Issue)}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1.5">
                {(Object.keys(ISSUE_LABELS) as Issue[]).map(key =>
                  <option key={key} value={key}>{ISSUE_LABELS[key]}</option>
                )}
              </select>
              <button type="button" disabled={busy} onClick={() => void submit('needs_review')}
                className="rounded-lg bg-emerald-800 px-3 py-1.5 font-semibold text-white disabled:opacity-50">
                Submit review
              </button>
            </div>
          ) : null}
          {error ? <span role="alert" className="text-red-700">{error}</span> : null}
          <p className="w-full text-[11px] text-slate-500">Only your rating and issue category are saved. No message, transcript or answer text is included.</p>
        </div>
      )}
    </aside>
  );
}
