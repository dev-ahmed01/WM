import React from 'react';
import { CopilotResponse } from '@/lib/api-client';

interface ChatThreadProps {
  messages: Array<{
    sender: 'user' | 'assistant';
    content: string;
    copilotData?: CopilotResponse;
  }>;
}

export const ChatThread: React.FC<ChatThreadProps> = ({ messages }) => {
  return (
    <div className="flex flex-col space-y-4 p-4 overflow-y-auto max-h-[70vh]">
      {messages.map((msg, index) => (
        <div
          key={index}
          className={`flex flex-col max-w-2xl ${
            msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'
          }`}
        >
          {/* Step Indicator */}
          {msg.copilotData?.active_sop_id && (
            <div className="mb-1 text-xs font-semibold px-2.5 py-1 rounded bg-blue-100 text-blue-800 border border-blue-200">
              SOP Step {msg.copilotData.active_step_number}: {msg.copilotData.active_step_title}
            </div>
          )}

          {msg.copilotData?.active_decision_options && msg.copilotData.active_decision_options.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5" aria-label="Available workflow decisions">
              {msg.copilotData.active_decision_options.map((option) => (
                <span key={option.option_code} className="text-xs px-2 py-1 rounded border border-indigo-200 bg-indigo-50 text-indigo-800">
                  {option.option_label} ({option.option_code})
                </span>
              ))}
            </div>
          )}

          {/* Message Bubble */}
          <div
            className={`p-4 rounded-lg shadow-sm text-sm ${
              msg.sender === 'user'
                ? 'bg-blue-600 text-white rounded-br-none'
                : 'bg-gray-100 text-gray-800 rounded-bl-none border border-gray-200'
            }`}
          >
            {msg.content}

            {/* Citations section */}
            {msg.copilotData?.citations && msg.copilotData.citations.length > 0 && (
              <div className="mt-3 pt-2 border-t border-gray-300 text-xs text-gray-700">
                <span className="font-semibold block mb-1">Sources & Citations:</span>
                <ul className="list-disc pl-4 space-y-1">
                  {msg.copilotData.citations.map((cite, i) => (
                    <li key={i}>
                      <span className="font-semibold">{cite.document_title}</span> (v{cite.version_number}): &quot;{cite.excerpt}&quot;
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

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
      ))}
    </div>
  );
};
