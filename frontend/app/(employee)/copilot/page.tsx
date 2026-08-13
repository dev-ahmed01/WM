'use client';

import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Radio, Sparkles } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiBlob, apiClient, type CopilotConversationDetail, type CopilotResponse, type SopSuggestion, type VoiceCopilotResponse, type VoiceLanguage, type VoiceSynthesisResponse, type WorkflowAdvanceResponse } from '@/lib/api-client';
import { ChatThread, type ChatMessage } from '@/components/chat/ChatThread';
import { ChatComposer } from '@/components/chat/ChatComposer';
import { WorkflowRail } from '@/components/chat/WorkflowRail';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { LoadingState } from '@/components/shared/LoadingState';
import { Badge } from '@/components/ui/badge';
import { useSpeechSynthesis } from '@/hooks/useWebSpeech';
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder';
import { presentCopilotMessage } from '@/lib/copilot-presentation';

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function CopilotContent() {
  const { user, loading } = useRequireRole(['employee', 'admin', 'manager']);
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session');

  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>(sessionId || undefined);
  const [workflowSessionId, setWorkflowSessionId] = useState<string | undefined>();
  const [workflowSessionStatus, setWorkflowSessionStatus] = useState<CopilotResponse['active_session_status']>();
  const [workflowDecisionOptions, setWorkflowDecisionOptions] = useState<NonNullable<CopilotResponse['active_decision_options']>>([]);
  const [activeStepNumber, setActiveStepNumber] = useState<number | undefined>();
  const [activeStepTitle, setActiveStepTitle] = useState<string | undefined>();
  const [isSending, setIsSending] = useState(false);
  const [abandonOpen, setAbandonOpen] = useState(false);
  const [abandonReason, setAbandonReason] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguage>('auto');
  const [detectedLanguage, setDetectedLanguage] = useState<string>();
  const [transcriptPreview, setTranscriptPreview] = useState<string>();
  const [isVoiceProcessing, setIsVoiceProcessing] = useState(false);
  const [voiceSpeakingKey, setVoiceSpeakingKey] = useState<string | null>(null);
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceObjectUrlRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      content: sessionId
        ? 'Restoring this session and its active operational context…'
        : 'Tell me what you are working on. I’ll find the verified SOP, keep you on the current step, and explain any rule that applies.',
    },
  ]);

  const speechSynthesis = useSpeechSynthesis();

  const stopVoiceAudio = useCallback(() => {
    voiceAudioRef.current?.pause();
    voiceAudioRef.current = null;
    if (voiceObjectUrlRef.current) URL.revokeObjectURL(voiceObjectUrlRef.current);
    voiceObjectUrlRef.current = null;
    setVoiceSpeakingKey(null);
  }, []);

  useEffect(() => stopVoiceAudio, [stopVoiceAudio]);

  const handleSpeak = useCallback(async (
    text: string,
    messageKey: string,
    audioUrl?: string | null,
    language?: string,
  ) => {
    if (!audioUrl) {
      stopVoiceAudio();
      speechSynthesis.speak(text, messageKey, language);
      return;
    }
    if (voiceSpeakingKey === messageKey) {
      stopVoiceAudio();
      return;
    }
    speechSynthesis.stop();
    stopVoiceAudio();
    try {
      const blob = await apiBlob(audioUrl);
      const objectUrl = URL.createObjectURL(blob);
      const player = new Audio(objectUrl);
      voiceAudioRef.current = player;
      voiceObjectUrlRef.current = objectUrl;
      player.onended = stopVoiceAudio;
      player.onerror = stopVoiceAudio;
      setVoiceSpeakingKey(messageKey);
      await player.play();
    } catch {
      stopVoiceAudio();
      speechSynthesis.speak(text, messageKey, language);
    }
  }, [speechSynthesis, stopVoiceAudio, voiceSpeakingKey]);

  useEffect(() => {
    async function resumeSession() {
      if (!sessionId || loading) return;
      try {
        const history = await apiClient<CopilotConversationDetail>(`/copilot/history/${sessionId}`);
        setConversationId(sessionId);
        setWorkflowSessionId(history.active_session_id ?? undefined);
        setWorkflowSessionStatus(history.active_session_status ?? undefined);
        setWorkflowDecisionOptions(history.active_decision_options || []);
        setActiveStepNumber(history.active_step_number ?? undefined);
        setActiveStepTitle(history.active_step_title ?? undefined);
        setMessages(history.messages.map((message) => ({
          id: message.id,
          sender: message.sender === 'employee' ? 'user' : 'assistant',
          content: message.content,
        })));
      } catch (error) {
        setMessages([{ id: 'resume-error', sender: 'assistant', content: getErrorMessage(error, 'Unable to load the conversation.') }]);
      }
    }
    resumeSession();
  }, [sessionId, loading]);

  const submitMessage = useCallback(async (message: string, speakReply = false) => {
    const userMessage = message.trim();
    if (!userMessage || isSending) return;
    setInput('');
    setIsSending(true);
    setMessages((current) => [...current, { id: createMessageId('user'), sender: 'user', content: userMessage }]);

    try {
      const response = await apiClient<CopilotResponse>('/copilot/message', {
        method: 'POST',
        body: JSON.stringify({ message: userMessage, conversation_id: conversationId }),
      });
      setConversationId(response.conversation_id || conversationId);
      setWorkflowSessionId(response.active_session_id ?? undefined);
      setWorkflowSessionStatus(response.active_session_status ?? undefined);
      setWorkflowDecisionOptions(response.active_decision_options || []);
      setActiveStepNumber(response.active_step_number ?? undefined);
      setActiveStepTitle(response.active_step_title ?? undefined);
      const assistantMessageId = response.message_id || createMessageId('assistant');
      setMessages((current) => [...current, { id: assistantMessageId, sender: 'assistant', content: response.answer, copilotData: response }]);
      if (speakReply) {
        const spokenText = presentCopilotMessage(response.answer, {
          spokenAnswer: response.spoken_answer,
          sopDetails: response.sop_details,
        }).spokenText;
        speechSynthesis.speak(spokenText, assistantMessageId);
      }
    } catch (error) {
      const errorMessage = getErrorMessage(error, 'WorkMate could not reach the Copilot service. Please try again.');
      const errorMessageId = createMessageId('error');
      setMessages((current) => [...current, { id: errorMessageId, sender: 'assistant', content: errorMessage }]);
      if (speakReply) speechSynthesis.speak(errorMessage, errorMessageId);
    } finally {
      setIsSending(false);
    }
  }, [conversationId, isSending, speechSynthesis.speak]);

  const handleSelectSop = useCallback((suggestion: SopSuggestion) => {
    void submitMessage(`Start ${suggestion.title}`);
  }, [submitMessage]);

  const submitVoice = useCallback(async (audio: Blob) => {
    if (isSending) return;
    setIsSending(true);
    setIsVoiceProcessing(true);
    setTranscriptPreview(undefined);
    setDetectedLanguage(undefined);
    try {
      const extension = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm';
      const form = new FormData();
      form.append('audio', audio, `workmate-voice.${extension}`);
      form.append('language', voiceLanguage);
      form.append('synthesize', 'false');
      if (conversationId) form.append('conversation_id', conversationId);
      const voice = await apiClient<VoiceCopilotResponse>('/copilot/voice', {
        method: 'POST',
        body: form,
      });
      const response = voice.copilot;
      setConversationId(response.conversation_id || conversationId);
      setWorkflowSessionId(response.active_session_id ?? undefined);
      setWorkflowSessionStatus(response.active_session_status ?? undefined);
      setWorkflowDecisionOptions(response.active_decision_options || []);
      setActiveStepNumber(response.active_step_number ?? undefined);
      setActiveStepTitle(response.active_step_title ?? undefined);
      setDetectedLanguage(voice.language);
      if (voiceLanguage === 'auto') setVoiceLanguage(voice.language);
      setTranscriptPreview(voice.transcript);
      const assistantMessageId = response.message_id || createMessageId('assistant');
      setMessages((current) => [
        ...current,
        { id: createMessageId('voice-user'), sender: 'user', content: voice.transcript, language: voice.language },
        {
          id: assistantMessageId,
          sender: 'assistant',
          content: voice.response_text,
          copilotData: response,
          voiceAudioUrl: voice.audio_url,
          language: voice.language,
        },
      ]);
      const spokenText = presentCopilotMessage(voice.response_text, {
        spokenAnswer: response.spoken_answer,
        sopDetails: response.sop_details,
      }).spokenText;
      // Text is rendered immediately. Piper runs in a second request so audio
      // generation never blocks the visible Copilot response.
      void apiClient<VoiceSynthesisResponse>('/copilot/voice/speech', {
        method: 'POST',
        body: JSON.stringify({ response_message_id: assistantMessageId }),
      }).then((speech) => {
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId
            ? { ...message, voiceAudioUrl: speech.audio_url }
            : message
        )));
        return handleSpeak(spokenText, assistantMessageId, speech.audio_url, voice.language);
      }).catch(() => {
        // The grounded text remains usable; browser speech is the safe fallback.
        speechSynthesis.speak(spokenText, assistantMessageId, voice.language);
      });
    } catch (error) {
      const errorMessage = getErrorMessage(error, 'WorkMate could not process that recording. Please try again.');
      setMessages((current) => [...current, {
        id: createMessageId('voice-error'), sender: 'assistant', content: errorMessage,
      }]);
    } finally {
      setIsVoiceProcessing(false);
      setIsSending(false);
    }
  }, [conversationId, handleSpeak, isSending, speechSynthesis, voiceLanguage]);

  const voiceRecorder = useVoiceRecorder(submitVoice);

  const handleSend = () => {
    voiceRecorder.stopListening();
    void submitMessage(input);
  };

  if (loading) return <LoadingState label="Loading Copilot workspace" />;

  const handleWorkflowAction = async (
    action: 'pause' | 'resume' | 'advance' | 'abandon',
    decisionOption?: string,
    reason?: string,
  ) => {
    if (!workflowSessionId || isSending) return;
    const selectedDecisionLabel = decisionOption
      ? workflowDecisionOptions.find((option) => option.option_code === decisionOption)?.option_label
      : undefined;
    let body: string | undefined;
    if (action === 'abandon') {
      if (!reason?.trim()) return;
      body = JSON.stringify({ reason: reason.trim() });
    } else if (action === 'advance') {
      body = JSON.stringify({ decision_option: decisionOption, rule_results: {}, values: {}, use_fallback: false });
    }

    if (selectedDecisionLabel) {
      setMessages((current) => [...current, { id: createMessageId('decision'), sender: 'user', content: `Observed outcome: ${selectedDecisionLabel}` }]);
    }
    setIsSending(true);
    try {
      const updated = await apiClient<WorkflowAdvanceResponse>(`/copilot/session/${workflowSessionId}/${action}`, { method: 'POST', body });
      setWorkflowSessionStatus(updated.status);
      let statusMessage = `Workflow ${updated.status}.`;
      if (action === 'advance') {
        setWorkflowDecisionOptions(updated.active_decision_options || []);
        setActiveStepNumber(updated.active_step_number ?? undefined);
        setActiveStepTitle(updated.active_step_title ?? undefined);
        const outcomePrefix = selectedDecisionLabel ? `Outcome recorded: ${selectedDecisionLabel}. ` : '';
        statusMessage = updated.status === 'completed'
          ? `${outcomePrefix}Workflow completed.`
          : updated.active_decision_options?.length
            ? 'Step complete. Select the verified outcome you observed.'
            : updated.active_step_title
              ? `${outcomePrefix}Next step: ${updated.active_step_title}`
              : 'Step complete.';
      }
      setMessages((current) => [...current, { id: createMessageId('workflow'), sender: 'assistant', content: statusMessage }]);
      if (action === 'abandon') {
        setAbandonOpen(false);
        setAbandonReason('');
      }
    } catch (error) {
      setMessages((current) => [...current, { id: createMessageId('action-error'), sender: 'assistant', content: getErrorMessage(error, `Unable to ${action} the workflow.`) }]);
    } finally {
      setIsSending(false);
    }
  };

  const composerPlaceholder = isSending
    ? 'Checking published guidance…'
    : activeStepNumber != null
      ? 'Ask about this step or type “done”…'
      : workflowDecisionOptions.length > 0
        ? 'Ask about the decision or select an outcome…'
        : 'Describe the task, issue, or SOP you need…';

  return (
    <div className="flex h-[calc(100dvh-4rem)] min-h-[38rem] flex-col overflow-hidden bg-white">
      <header className="flex flex-none items-center justify-between gap-4 border-b border-border/80 bg-white px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-base font-semibold tracking-tight text-foreground sm:text-lg">Operational Copilot</h1>
            <Badge className="hidden sm:inline-flex"><Radio className="h-3 w-3" />Live</Badge>
          </div>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">Verified, step-by-step guidance for {user?.department_id || 'your department'}</p>
        </div>
        <div className="flex flex-none items-center gap-2">
          {conversationId ? <span className="hidden max-w-44 truncate rounded-lg bg-muted px-2.5 py-1.5 font-mono text-[10px] text-muted-foreground md:block">{conversationId}</span> : null}
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-emerald-50 text-emerald-700" title="Grounded reasoning enabled"><Sparkles className="h-4 w-4" /></span>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_21rem] lg:grid-rows-1">
        <section className="order-2 flex min-h-0 flex-col lg:order-1" aria-label="Copilot conversation">
          <main className="min-h-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_50%_0%,rgba(209,250,229,0.22),transparent_28rem)]">
            <ChatThread
              messages={messages}
              busy={isSending}
              onSpeak={handleSpeak}
              speakingMessageKey={voiceSpeakingKey || speechSynthesis.speakingKey}
              speechSupported={speechSynthesis.isSupported || voiceRecorder.isSupported}
              onSelectSop={handleSelectSop}
            />
          </main>
          <ChatComposer
            value={input}
            placeholder={composerPlaceholder}
            busy={isSending}
            listening={voiceRecorder.isListening}
            voiceProcessing={isVoiceProcessing}
            voiceInputLevel={voiceRecorder.inputLevel}
            voiceRecordingSeconds={voiceRecorder.recordingSeconds}
            microphonePermission={voiceRecorder.permissionState}
            speechSupported={voiceRecorder.isSupported}
            speechError={voiceRecorder.error}
            voiceLanguage={voiceLanguage}
            detectedLanguage={detectedLanguage}
            transcriptPreview={transcriptPreview}
            onChange={setInput}
            onSend={() => void handleSend()}
            onToggleListening={voiceRecorder.toggleListening}
            onVoiceLanguageChange={setVoiceLanguage}
          />
        </section>
        <div className="order-1 max-h-[18rem] min-h-0 overflow-hidden lg:order-2 lg:max-h-none">
          <WorkflowRail
            sessionId={workflowSessionId}
            status={workflowSessionStatus}
            stepNumber={activeStepNumber}
            stepTitle={activeStepTitle}
            decisionOptions={workflowDecisionOptions}
            busy={isSending}
            onAdvance={(decisionOption) => handleWorkflowAction('advance', decisionOption)}
            onPause={() => handleWorkflowAction('pause')}
            onResume={() => handleWorkflowAction('resume')}
            onAbandon={() => setAbandonOpen(true)}
          />
        </div>
      </div>

      <ConfirmDialog
        open={abandonOpen}
        title="Abandon this workflow?"
        description="The current session will be closed and cannot be resumed. Add a short reason for the operational record."
        confirmLabel="Abandon workflow"
        busy={isSending}
        value={abandonReason}
        valueLabel="Reason"
        valuePlaceholder="Why is this workflow being abandoned?"
        onValueChange={setAbandonReason}
        onConfirm={() => handleWorkflowAction('abandon', undefined, abandonReason)}
        onClose={() => !isSending && setAbandonOpen(false)}
      />
    </div>
  );
}

export default function CopilotPage() {
  return <Suspense fallback={<LoadingState label="Loading Copilot" />}><CopilotContent /></Suspense>;
}
