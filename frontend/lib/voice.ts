import type { Language } from '@/lib/language';

const BASE = '/api/backend';

export class VoiceApiError extends Error {
  constructor(message: string, public code: string, public status: number) {
    super(message);
  }
}

async function failure(response: Response): Promise<VoiceApiError> {
  try {
    const json = await response.json();
    const payload = json?.detail ?? json;
    return new VoiceApiError(payload?.message || 'Voice is unavailable right now.', payload?.error_code || 'VOICE_ERROR', response.status);
  } catch {
    return new VoiceApiError('Voice is unavailable right now. You can still type your question.', 'VOICE_ERROR', response.status);
  }
}

/** Send a recording for transcription. The text is only returned: nothing is saved or sent to the assistant. */
export async function transcribe(audio: Blob, language: Language | 'auto'): Promise<{ text: string; language: string }> {
  const form = new FormData();
  const extension = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm';
  form.append('audio', audio, `recording.${extension}`);
  form.append('language', language);
  const response = await fetch(`${BASE}/voice/transcribe`, { method: 'POST', body: form, credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) throw await failure(response);
  return response.json();
}

export async function synthesize(text: string, language: Language): Promise<Blob> {
  const response = await fetch(`${BASE}/voice/speak`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language }),
  });
  if (!response.ok) throw await failure(response);
  return response.blob();
}

export async function translateToHindi(text: string): Promise<string> {
  const response = await fetch(`${BASE}/voice/translate`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, target: 'hi' }),
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()).text as string;
}
