'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type PlayerState = 'idle' | 'loading' | 'playing';

/** One spoken answer at a time. Starting another stops the first; leaving the page stops it and frees the audio. */
export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const tokenRef = useRef(0);
  const [state, setState] = useState<PlayerState>('idle');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const release = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    tokenRef.current += 1; // cancels a request that is still being prepared
    release();
    setState('idle');
    setActiveId(null);
  }, [release]);

  const play = useCallback(async (id: string, load: () => Promise<Blob>) => {
    stop();
    const token = tokenRef.current;
    setError(null);
    setActiveId(id);
    setState('loading');
    try {
      const blob = await load();
      if (token !== tokenRef.current) return;
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => { if (token === tokenRef.current) stop(); };
      audio.onerror = () => { if (token === tokenRef.current) { setError('This browser could not play the audio.'); stop(); } };
      await audio.play(); // may reject if the browser blocks autoplay; the Listen button always works (it is a user gesture)
      if (token === tokenRef.current) setState('playing');
    } catch (cause) {
      if (token !== tokenRef.current) return;
      const blocked = cause instanceof DOMException && cause.name === 'NotAllowedError';
      setError(blocked ? 'Tap Listen to hear the answer (your browser blocks automatic sound).'
        : cause instanceof Error ? cause.message : 'Could not play the audio.');
      release();
      setState('idle');
      setActiveId(null);
    }
  }, [release, stop]);

  useEffect(() => () => { tokenRef.current += 1; release(); }, [release]);

  return { state, activeId, error, play, stop, clearError: () => setError(null) };
}
