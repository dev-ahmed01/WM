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
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [inputLevel, setInputLevel] = useState(0);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [permissionState, setPermissionState] = useState<PermissionState | 'unknown'>('unknown');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { handlerRef.current = onRecording; }, [onRecording]);

  const releaseStream = useCallback(() => {
    if (animationFrameRef.current != null) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    setIsSupported(
      'mediaDevices' in navigator
      && 'getUserMedia' in navigator.mediaDevices
      && 'MediaRecorder' in window
    );
    let permissionStatus: PermissionStatus | undefined;
    if ('permissions' in navigator) {
      void navigator.permissions.query({ name: 'microphone' as PermissionName })
        .then((status) => {
          permissionStatus = status;
          setPermissionState(status.state);
          status.onchange = () => setPermissionState(status.state);
        })
        .catch(() => setPermissionState('unknown'));
    }
    return () => {
      if (permissionStatus) permissionStatus.onchange = null;
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
      setInputLevel(0);
      setRecordingSeconds(0);
      discardRef.current = false;
      chunksRef.current = [];
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      setPermissionState('granted');
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

      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const recordingStartedAt = performance.now();
      let speechStarted = false;
      let lastSpeechAt = recordingStartedAt;
      let lastUiUpdateAt = 0;

      const monitorSilence = () => {
        if (recorder.state !== 'recording') return;
        analyser.getByteTimeDomainData(samples);
        let squaredTotal = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          squaredTotal += normalized * normalized;
        }
        const volume = Math.sqrt(squaredTotal / samples.length);
        const now = performance.now();
        if (now - lastUiUpdateAt >= 100) {
          setInputLevel(Math.min(1, volume * 10));
          setRecordingSeconds((now - recordingStartedAt) / 1000);
          lastUiUpdateAt = now;
        }
        if (volume >= 0.012) {
          speechStarted = true;
          lastSpeechAt = now;
        }
        if (speechStarted && now - lastSpeechAt >= 1400) {
          recorder.stop();
          return;
        }
        if (!speechStarted && now - recordingStartedAt >= 8000) {
          discardRef.current = true;
          setError('No speech was detected. Check your microphone and try again.');
          recorder.stop();
          return;
        }
        if (now - recordingStartedAt >= 15000) {
          recorder.stop();
          return;
        }
        animationFrameRef.current = requestAnimationFrame(monitorSilence);
      };
      animationFrameRef.current = requestAnimationFrame(monitorSilence);
    } catch (cause) {
      releaseStream();
      setIsListening(false);
      const denied = cause instanceof DOMException && cause.name === 'NotAllowedError';
      if (denied) setPermissionState('denied');
      setError(denied
        ? 'Microphone access was denied. Allow microphone access and try again.'
        : 'No working microphone could be opened.');
    }
  }, [releaseStream]);

  const toggleListening = useCallback(() => {
    if (isListening) stopListening();
    else void startListening();
  }, [isListening, startListening, stopListening]);

  return {
    error,
    inputLevel,
    isListening,
    isSupported,
    permissionState,
    recordingSeconds,
    stopListening,
    toggleListening,
  };
}
