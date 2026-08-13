'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

function preferredMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  return ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
    .find((type) => MediaRecorder.isTypeSupported(type));
}

export function useVoiceRecorder(onRecording: (audio: Blob) => void) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const handlerRef = useRef(onRecording);
  const discardRef = useRef(false);
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { handlerRef.current = onRecording; }, [onRecording]);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    setIsSupported(
      'mediaDevices' in navigator
      && 'getUserMedia' in navigator.mediaDevices
      && 'MediaRecorder' in window
    );
    return () => {
      discardRef.current = true;
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
      recorderRef.current = null;
      releaseStream();
    };
  }, [releaseStream]);

  const stopListening = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  }, []);

  const startListening = useCallback(async () => {
    if (
      !('mediaDevices' in navigator)
      || !('getUserMedia' in navigator.mediaDevices)
      || !('MediaRecorder' in window)
    ) {
      setError('Voice recording is not supported in this browser.');
      return;
    }
    try {
      setError(null);
      discardRef.current = false;
      chunksRef.current = [];
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      const mimeType = preferredMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setError('Voice recording stopped unexpectedly. Please try again.');
        setIsListening(false);
        releaseStream();
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];
        recorderRef.current = null;
        setIsListening(false);
        releaseStream();
        if (blob.size && !discardRef.current) handlerRef.current(blob);
      };
      recorder.start(250);
      setIsListening(true);
    } catch (cause) {
      releaseStream();
      setIsListening(false);
      const denied = cause instanceof DOMException && cause.name === 'NotAllowedError';
      setError(denied
        ? 'Microphone access was denied. Allow microphone access and try again.'
        : 'No working microphone could be opened.');
    }
  }, [releaseStream]);

  const toggleListening = useCallback(() => {
    if (isListening) stopListening();
    else void startListening();
  }, [isListening, startListening, stopListening]);

  return { error, isListening, isSupported, stopListening, toggleListening };
}
