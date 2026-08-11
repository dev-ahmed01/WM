import React, { useEffect, useRef } from 'react';
import { Square, Volume2 } from 'lucide-react';
import { CopilotResponse } from '@/lib/api-client';

interface ChatThreadProps {
  messages: Array<{
    sender: 'user' | 'assistant';
    content: string;
    copilotData?: CopilotResponse;
  }>;
  speechSupported: boolean;
  speakingMessageKey: string | null;
  onSpeak: (text: string, messageKey: string) => void;
}

export const ChatThread: React.FC<ChatThreadProps> = ({
  messages,
  onSpeak,
  speakingMessageKey,
  speechSupported,
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  return (
    <div
      ref={scrollContainerRef}
      className="flex h-full min-h-0 flex-col space-y-4 overflow-y-auto p-4"
      aria-live="polite"
    >
      {messages.map((msg, index) => {
        const messageKey = `assistant-${index}`;
        const isSpeaking = speakingMessageKey === messageKey;
        return (
          <div
            key={index}
            className={`flex flex-col max-w-2xl ${
              msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'
            }`}
          >
          {/* Message Bubble */}
          <div
            className={`whitespace-pre-wrap break-words p-4 rounded-lg shadow-sm text-sm ${
              msg.sender === 'user'
                ? 'bg-blue-600 text-white rounded-br-none'
                : 'bg-gray-100 text-gray-800 rounded-bl-none border border-gray-200'
            }`}
          >
            {msg.content}

            {/* Citations section */}
            {msg.copilotData?.citations && msg.copilotData.citations.length > 0 && (
              <div className="mt-3 pt-2 border-t border-gray-300 text-xs text-gray-700">
                <span className="font-semibold block mb-1">Verified source:</span>
                <ul className="list-disc pl-4 space-y-1">
                  {msg.copilotData.citations.map((cite, i) => (
                    <li key={i}>
                      <span className="font-semibold">{cite.document_title}</span>
                      {' '}· version {cite.version_number}
                      {cite.step_number ? ` · workflow state ${cite.step_number}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {msg.sender === 'assistant' && speechSupported && (
            <button
              type="button"
              onClick={() => onSpeak(msg.content, messageKey)}
              aria-label={isSpeaking ? 'Stop reading this response' : 'Listen to this response'}
              className="mt-1 inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-blue-700"
            >
              {isSpeaking ? <Square aria-hidden="true" size={13} /> : <Volume2 aria-hidden="true" size={14} />}
              {isSpeaking ? 'Stop' : 'Listen'}
            </button>
          )}

          {/* Confidence / Escalation Badge */}
          {msg.copilotData && (
            <div className="mt-1 flex items-center space-x-2 text-xs">
              <span
                className={`px-2 py-0.5 rounded-full font-medium ${
                  msg.copilotData.confidence_score >= 0.70
                    ? 'bg-green-100 text-green-800'
                    : 'bg-yellow-100 text-yellow-800'
                }`}
              >
                Confidence: {(msg.copilotData.confidence_score * 100).toFixed(0)}%
              </span>
              {msg.copilotData.requires_escalation && (
                <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-semibold border border-red-200">
                  Escalation Triggered
                </span>
              )}
            </div>
          )}
          </div>
        );
      })}
    </div>
  );
};
