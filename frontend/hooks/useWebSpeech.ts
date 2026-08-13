'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionResultListLike {
  readonly length: number;
  [index: number]: SpeechRecognitionResultLike;
}

interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListLike;
}

interface SpeechRecognitionErrorEventLike extends Event {
  readonly error: string;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onstart: ((event: Event) => void) | null;
  onend: ((event: Event) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

function recognitionErrorMessage(error: string): string {
  switch (error) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'Microphone access was denied. Allow microphone access in your browser and try again.';
    case 'audio-capture':
      return 'No working microphone was found.';
    case 'no-speech':
      return 'No speech was detected. Please try again.';
    case 'network':
      return 'Speech recognition could not reach the browser speech service.';
    default:
      return 'Voice input stopped unexpectedly. Please try again.';
  }
}

export function useSpeechRecognition(
  onTranscriptChange: (transcript: string) => void,
  onFinalTranscript: (transcript: string) => void,
) {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const transcriptChangeHandlerRef = useRef(onTranscriptChange);
  const finalTranscriptHandlerRef = useRef(onFinalTranscript);
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    transcriptChangeHandlerRef.current = onTranscriptChange;
    finalTranscriptHandlerRef.current = onFinalTranscript;
  }, [onFinalTranscript, onTranscriptChange]);

  useEffect(() => {
    setIsSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
    return () => {
      const recognition = recognitionRef.current;
      if (!recognition) return;
      recognition.onstart = null;
      recognition.onend = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.abort();
      recognitionRef.current = null;
    };
  }, []);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  const startListening = useCallback(() => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setError('Voice input is not supported in this browser. Use a current Chrome or Edge browser.');
      return;
    }

    window.speechSynthesis?.cancel();
    recognitionRef.current?.abort();
    setError(null);

    const recognition = new Recognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || 'en-US';
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognition.onerror = (event) => {
      setIsListening(false);
      if (event.error !== 'aborted') {
        setError(recognitionErrorMessage(event.error));
      }
    };
    let finalSubmitted = false;
    recognition.onresult = (event) => {
      const finalParts: string[] = [];
      const interimParts: string[] = [];
      let hasFinalResult = false;
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal && result.length > 0) {
          finalParts.push(result[0].transcript);
          hasFinalResult = true;
        } else if (result.length > 0) {
          interimParts.push(result[0].transcript);
        }
      }
      const finalTranscript = finalParts.join(' ').trim();
      const visibleTranscript = [...finalParts, ...interimParts].join(' ').trim();
      if (visibleTranscript) transcriptChangeHandlerRef.current(visibleTranscript);
      if (hasFinalResult && interimParts.length === 0 && finalTranscript && !finalSubmitted) {
        finalSubmitted = true;
        finalTranscriptHandlerRef.current(finalTranscript);
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setIsListening(false);
      setError('Voice input is already active. Please stop it before trying again.');
    }
  }, []);

  const toggleListening = useCallback(() => {
    if (isListening) stopListening();
    else startListening();
  }, [isListening, startListening, stopListening]);

  return {
    error,
    isListening,
    isSupported,
    stopListening,
    toggleListening,
  };
}

export function useSpeechSynthesis() {
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const [isSupported, setIsSupported] = useState(false);
  const [speakingKey, setSpeakingKey] = useState<string | null>(null);

  useEffect(() => {
    setIsSupported('speechSynthesis' in window && 'SpeechSynthesisUtterance' in window);
    return () => {
      if (utteranceRef.current) {
        utteranceRef.current.onend = null;
        utteranceRef.current.onerror = null;
      }
      window.speechSynthesis?.cancel();
      utteranceRef.current = null;
    };
  }, []);

  const stop = useCallback(() => {
    if (utteranceRef.current) {
      utteranceRef.current.onend = null;
      utteranceRef.current.onerror = null;
    }
    window.speechSynthesis?.cancel();
    utteranceRef.current = null;
    setSpeakingKey(null);
  }, []);

  const speak = useCallback((text: string, messageKey: string, language?: string) => {
    if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) return;
    if (speakingKey === messageKey) {
      stop();
      return;
    }

    window.speechSynthesis.cancel();
    if (utteranceRef.current) {
      utteranceRef.current.onend = null;
      utteranceRef.current.onerror = null;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    const speechLocales: Record<string, string> = {
      en: 'en-IN', hi: 'hi-IN', kn: 'kn-IN', ta: 'ta-IN', te: 'te-IN', ml: 'ml-IN',
    };
    utterance.lang = speechLocales[language || ''] || document.documentElement.lang || navigator.language || 'en-US';
    utterance.rate = 1;
    utterance.onend = () => {
      utteranceRef.current = null;
      setSpeakingKey(null);
    };
    utterance.onerror = () => {
      utteranceRef.current = null;
      setSpeakingKey(null);
    };
    utteranceRef.current = utterance;
    setSpeakingKey(messageKey);
    window.speechSynthesis.speak(utterance);
  }, [speakingKey, stop]);

  return { isSupported, speak, speakingKey, stop };
}
