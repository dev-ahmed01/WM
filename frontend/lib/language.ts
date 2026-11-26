'use client';

import { useCallback, useEffect, useState } from 'react';

export type Language = 'en' | 'hi';
const KEY = 'wm_language';
const EVENT = 'wm-language-change';

function read(): Language {
  try {
    return window.localStorage.getItem(KEY) === 'hi' ? 'hi' : 'en';
  } catch {
    return 'en';
  }
}

/** The employee's preferred language for speaking, listening and translated answers. Stored on this device only. */
export function useLanguage(): [Language, (next: Language) => void] {
  const [language, setLanguage] = useState<Language>('en');

  useEffect(() => {
    setLanguage(read());
    const sync = () => setLanguage(read());
    window.addEventListener(EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const update = useCallback((next: Language) => {
    try { window.localStorage.setItem(KEY, next); } catch { /* private mode: keep it for this session only */ }
    setLanguage(next);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return [language, update];
}

export const LANGUAGE_LABEL: Record<Language, string> = { en: 'English', hi: 'हिन्दी' };
